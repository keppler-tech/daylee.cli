"""Tests for the hook-target dispatch and per-session aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daylee import forward, paths


@pytest.fixture(autouse=True)
def _no_flusher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent forward_one_event from spawning a real flusher process in tests."""
    monkeypatch.setattr(forward, "_spawn_flusher_if_needed", lambda: None)


@pytest.fixture(autouse=True)
def _no_git_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that don't care about git context shouldn't shell out to git."""
    monkeypatch.setattr(forward, "_resolve_git_context", lambda cwd: (None, None, None))
    monkeypatch.setattr(forward, "_resolve_git_head_sha", lambda cwd: None)
    monkeypatch.setattr(forward, "_commit_subjects_since", lambda cwd, sha: [])


def _payload(hook_event_name: str, *, session_id: str = "ccs-test", **extra) -> str:
    base = {"hook_event_name": hook_event_name, "session_id": session_id, "cwd": "/tmp"}
    base.update(extra)
    return json.dumps(base)


def _read_log(cc_session_id: str) -> list[dict]:
    log = paths.session_log_path(cc_session_id)
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def _read_queue() -> list[dict]:
    qpath = paths.queue_file()
    if not qpath.exists():
        return []
    return [json.loads(line) for line in qpath.read_text().splitlines() if line.strip()]


class TestSessionStart:
    def test_creates_log_and_queues_event(self, isolated_config_dir: Path):
        forward.forward_one_event(_payload("SessionStart"))

        entries = _read_log("ccs-test")
        assert any(e["kind"] == "start" for e in entries)

        queued = _read_queue()
        assert len(queued) == 1
        assert queued[0]["kind"] == "session_start"
        assert queued[0]["cc_session_id"] == "ccs-test"
        assert queued[0]["event_count"] == 1


class TestPostToolUse:
    def test_appends_tool_entry_with_files(self, isolated_config_dir: Path):
        forward.forward_one_event(_payload("SessionStart"))
        forward.forward_one_event(
            _payload(
                "PostToolUse",
                tool_name="Edit",
                tool_input={"file_path": "/repo/a.py"},
            )
        )
        forward.forward_one_event(
            _payload(
                "PostToolUse",
                tool_name="Bash",
                tool_input={"command": "ls"},
            )
        )

        tools = [e for e in _read_log("ccs-test") if e["kind"] == "tool"]
        assert [t["name"] for t in tools] == ["Edit", "Bash"]
        assert tools[0]["files"] == ["/repo/a.py"]
        assert tools[1]["files"] == []  # Bash has no file path

    def test_skipped_when_no_session_log(self, isolated_config_dir: Path):
        # No SessionStart fired — PostToolUse should be a no-op (likely a session
        # whose repo was filtered out by allow/deny lists).
        forward.forward_one_event(
            _payload(
                "PostToolUse",
                tool_name="Edit",
                tool_input={"file_path": "/repo/a.py"},
            )
        )
        assert not paths.session_log_path("ccs-test").exists()


class TestUserPromptSubmit:
    def test_logs_without_preview_by_default(self, isolated_config_dir: Path):
        forward.forward_one_event(_payload("SessionStart"))
        forward.forward_one_event(_payload("UserPromptSubmit", prompt="fix the bug"))

        prompts = [e for e in _read_log("ccs-test") if e["kind"] == "prompt"]
        assert len(prompts) == 1
        assert "preview" not in prompts[0]

    def test_logs_redacted_preview_when_send_raw_prompts(
        self, isolated_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from daylee import config as config_mod

        cfg = config_mod.Config(send_raw_prompts=True)
        monkeypatch.setattr(forward, "load_config", lambda: cfg)

        forward.forward_one_event(_payload("SessionStart"))
        forward.forward_one_event(
            _payload("UserPromptSubmit", prompt="fix the auth bug AKIAABCDEFGHIJKLMNOP")
        )

        prompts = [e for e in _read_log("ccs-test") if e["kind"] == "prompt"]
        assert len(prompts) == 1
        assert "fix the auth bug" in prompts[0]["preview"]
        assert "AKIAABCDEFGHIJKLMNOP" not in prompts[0]["preview"]


class TestSessionEnd:
    def test_aggregates_counts_files_and_clears_log(self, isolated_config_dir: Path):
        forward.forward_one_event(_payload("SessionStart"))
        forward.forward_one_event(
            _payload("PostToolUse", tool_name="Edit", tool_input={"file_path": "/repo/a.py"})
        )
        forward.forward_one_event(
            _payload("PostToolUse", tool_name="Edit", tool_input={"file_path": "/repo/b.py"})
        )
        forward.forward_one_event(
            _payload("PostToolUse", tool_name="Read", tool_input={"file_path": "/repo/a.py"})
        )
        forward.forward_one_event(_payload("UserPromptSubmit", prompt="hi"))
        forward.forward_one_event(_payload("SessionEnd"))

        # Log file is cleaned up.
        assert not paths.session_log_path("ccs-test").exists()

        queued = _read_queue()
        ends = [e for e in queued if e["kind"] == "session_end"]
        assert len(ends) == 1
        end = ends[0]
        assert end["tool_use_counts"] == {"Edit": 2, "Read": 1}
        assert end["files_touched"] == ["/repo/a.py", "/repo/b.py"]  # deduped
        assert end["event_count"] == 5  # start + 3 tool + 1 prompt
        assert end["duration_seconds"] >= 0

    def test_includes_summary_when_send_raw_prompts(
        self, isolated_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from daylee import config as config_mod

        cfg = config_mod.Config(send_raw_prompts=True)
        monkeypatch.setattr(forward, "load_config", lambda: cfg)

        forward.forward_one_event(_payload("SessionStart"))
        forward.forward_one_event(
            _payload("UserPromptSubmit", prompt="Implement the V1 of the Claude Code integration")
        )
        forward.forward_one_event(_payload("UserPromptSubmit", prompt="add tests too"))
        forward.forward_one_event(_payload("SessionEnd"))

        ends = [e for e in _read_queue() if e["kind"] == "session_end"]
        assert len(ends) == 1
        end = ends[0]
        assert "Implement the V1" in end["summary"]
        assert "add tests too" in end["prompt_digest"]

    def test_summary_from_commits_even_without_raw_prompts(
        self, isolated_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(forward, "_resolve_git_head_sha", lambda cwd: "abc123")
        monkeypatch.setattr(
            forward,
            "_commit_subjects_since",
            lambda cwd, sha: ["Fix auth bug", "Add regression test"],
        )

        forward.forward_one_event(_payload("SessionStart"))
        forward.forward_one_event(_payload("UserPromptSubmit", prompt="please fix it"))
        forward.forward_one_event(_payload("SessionEnd"))

        ends = [e for e in _read_queue() if e["kind"] == "session_end"]
        assert len(ends) == 1
        end = ends[0]
        assert end["summary"] == "Fix auth bug; Add regression test"
        # Raw prompts disabled by default, so no digest is sent.
        assert "prompt_digest" not in end

    def test_commit_summary_wins_over_prompt_summary_when_raw_prompts_on(
        self, isolated_config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from daylee import config as config_mod

        cfg = config_mod.Config(send_raw_prompts=True)
        monkeypatch.setattr(forward, "load_config", lambda: cfg)
        monkeypatch.setattr(forward, "_resolve_git_head_sha", lambda cwd: "abc123")
        monkeypatch.setattr(
            forward, "_commit_subjects_since", lambda cwd, sha: ["Ship the V1"]
        )

        forward.forward_one_event(_payload("SessionStart"))
        forward.forward_one_event(_payload("UserPromptSubmit", prompt="draft the design"))
        forward.forward_one_event(_payload("SessionEnd"))

        ends = [e for e in _read_queue() if e["kind"] == "session_end"]
        assert ends[0]["summary"] == "Ship the V1"
        # Digest still populated from prompts for server-side context.
        assert "draft the design" in ends[0]["prompt_digest"]

    def test_skipped_when_no_log(self, isolated_config_dir: Path):
        forward.forward_one_event(_payload("SessionEnd"))
        assert _read_queue() == []

    def test_stop_event_treated_as_session_end(self, isolated_config_dir: Path):
        forward.forward_one_event(_payload("SessionStart"))
        forward.forward_one_event(
            _payload("PostToolUse", tool_name="Edit", tool_input={"file_path": "/repo/a.py"})
        )
        forward.forward_one_event(_payload("Stop"))

        ends = [e for e in _read_queue() if e["kind"] == "session_end"]
        assert len(ends) == 1
        assert ends[0]["tool_use_counts"] == {"Edit": 1}
