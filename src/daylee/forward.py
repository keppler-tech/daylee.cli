"""Hook target: read a Claude Code hook event from stdin, aggregate, queue."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import queue as queue_mod
from .config import Config, load_config
from .paths import flusher_pid_file, session_log_path
from .redact import redact_text


_KNOWN_HOOK_EVENTS = {
    "SessionStart",
    "SessionEnd",
    "Stop",
    "PostToolUse",
    "UserPromptSubmit",
}

_PROMPT_PREVIEW_BYTES = 500
_SUMMARY_MAX_CHARS = 200
_MAX_FILES_TOUCHED = 50
_FILE_INPUT_KEYS = ("file_path", "notebook_path", "path")


def forward_one_event(raw_payload: str) -> int:
    """Process a single hook event read from stdin. Returns process exit code."""
    config = load_config()

    try:
        payload: dict[str, Any] = json.loads(raw_payload) if raw_payload else {}
    except json.JSONDecodeError:
        return 0  # Don't fail the hook on a malformed payload; just drop it.

    hook_name = payload.get("hook_event_name") or payload.get("hook") or ""
    if hook_name not in _KNOWN_HOOK_EVENTS:
        return 0

    cc_session_id = payload.get("session_id") or payload.get("sessionId") or ""
    if not cc_session_id:
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    now = datetime.now(timezone.utc)

    if hook_name == "SessionStart":
        return _handle_session_start(cc_session_id, cwd, now, config)
    if hook_name in ("SessionEnd", "Stop"):
        return _handle_session_end(cc_session_id, cwd, now, config)
    if hook_name == "PostToolUse":
        return _handle_post_tool_use(cc_session_id, payload, now)
    if hook_name == "UserPromptSubmit":
        return _handle_user_prompt_submit(cc_session_id, payload, now, config)
    return 0


def _handle_session_start(cc_session_id: str, cwd: str, now: datetime, config: Config) -> int:
    repo_url, repo_label, branch = _resolve_git_context(cwd)
    if not _repo_allowed(repo_url, config.repo_allowlist, config.repo_denylist):
        return 0

    start_sha = _resolve_git_head_sha(cwd)

    log_path = session_log_path(cc_session_id)
    _append_session_log(
        log_path,
        {
            "kind": "start",
            "ts": now.isoformat(),
            "repo_url": repo_url,
            "repo_label": repo_label,
            "branch": branch,
            "cwd": _normalize_path(cwd),
            "start_sha": start_sha,
        },
    )

    event: dict[str, Any] = {
        "cc_session_id": cc_session_id,
        "kind": "session_start",
        "timestamp": now.isoformat(),
        "cwd": _normalize_path(cwd),
        "event_count": 1,
    }
    if repo_url:
        event["repo_url"] = repo_url
    if repo_label:
        event["repo_label"] = repo_label
    if branch:
        event["branch"] = branch

    queue_mod.append_event(event)
    _spawn_flusher_if_needed()
    return 0


def _handle_session_end(cc_session_id: str, cwd: str, now: datetime, config: Config) -> int:
    log_path = session_log_path(cc_session_id)
    if not log_path.exists():
        # SessionStart never landed for this session (or repo was filtered).
        # Nothing to update on the server.
        return 0

    entries = _read_session_log(log_path)
    started_at = _started_at(entries) or now
    duration_seconds = max(0, int((now - started_at).total_seconds()))
    start_sha = _start_sha(entries)

    tool_counts: Counter[str] = Counter()
    files: list[str] = []
    seen_files: set[str] = set()
    prompt_previews: list[str] = []

    for e in entries:
        kind = e.get("kind")
        if kind == "tool":
            name = str(e.get("name") or "")
            if name:
                tool_counts[name] += 1
            for f in e.get("files") or []:
                if isinstance(f, str) and f and f not in seen_files and len(files) < _MAX_FILES_TOUCHED:
                    seen_files.add(f)
                    files.append(f)
        elif kind == "prompt":
            preview = e.get("preview")
            if isinstance(preview, str) and preview:
                prompt_previews.append(preview)

    event: dict[str, Any] = {
        "cc_session_id": cc_session_id,
        "kind": "session_end",
        "timestamp": now.isoformat(),
        "cwd": _normalize_path(cwd),
        "duration_seconds": duration_seconds,
        "event_count": len(entries),
    }
    if tool_counts:
        event["tool_use_counts"] = dict(tool_counts)
    if files:
        event["files_touched"] = files

    commit_subjects = _commit_subjects_since(cwd, start_sha)
    summary = _summary_from_commits(commit_subjects)
    if summary:
        event["summary"] = summary

    if config.send_raw_prompts and prompt_previews:
        if "summary" not in event:
            prompt_summary = _summary_from_prompts(prompt_previews)
            if prompt_summary:
                event["summary"] = prompt_summary
        digest = _digest_from_prompts(prompt_previews)
        if digest:
            event["prompt_digest"] = digest

    queue_mod.append_event(event)
    _spawn_flusher_if_needed()

    try:
        log_path.unlink()
    except OSError:
        pass
    return 0


def _handle_post_tool_use(cc_session_id: str, payload: dict[str, Any], now: datetime) -> int:
    log_path = session_log_path(cc_session_id)
    if not log_path.exists():
        return 0
    tool_name = str(payload.get("tool_name") or "")
    files = _files_from_tool_input(payload.get("tool_input"))
    _append_session_log(
        log_path,
        {"kind": "tool", "name": tool_name, "files": files, "ts": now.isoformat()},
    )
    return 0


def _handle_user_prompt_submit(
    cc_session_id: str, payload: dict[str, Any], now: datetime, config: Config
) -> int:
    log_path = session_log_path(cc_session_id)
    if not log_path.exists():
        return 0
    entry: dict[str, Any] = {"kind": "prompt", "ts": now.isoformat()}
    if config.send_raw_prompts:
        prompt = payload.get("prompt") or payload.get("user_prompt") or ""
        if prompt:
            redacted = redact_text(str(prompt)) or ""
            if redacted:
                entry["preview"] = redacted[:_PROMPT_PREVIEW_BYTES]
    _append_session_log(log_path, entry)
    return 0


def _started_at(entries: list[dict]) -> datetime | None:
    for e in entries:
        if e.get("kind") == "start":
            ts = e.get("ts")
            try:
                return datetime.fromisoformat(str(ts))
            except (TypeError, ValueError):
                return None
    return None


def _start_sha(entries: list[dict]) -> str | None:
    for e in entries:
        if e.get("kind") == "start":
            sha = e.get("start_sha")
            return sha if isinstance(sha, str) and sha else None
    return None


def _files_from_tool_input(tool_input: object) -> list[str]:
    if not isinstance(tool_input, dict):
        return []
    out: list[str] = []
    for key in _FILE_INPUT_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            out.append(_normalize_path(value))
    return out


def _summary_from_prompts(prompts: list[str]) -> str | None:
    first = prompts[0].strip()
    if not first:
        return None
    if len(first) > _SUMMARY_MAX_CHARS:
        first = first[:_SUMMARY_MAX_CHARS].rstrip() + "…"
    return first


def _summary_from_commits(subjects: list[str]) -> str | None:
    cleaned = [s.strip() for s in subjects if s and s.strip()]
    if not cleaned:
        return None
    joined = "; ".join(cleaned)
    if len(joined) > _SUMMARY_MAX_CHARS:
        joined = joined[:_SUMMARY_MAX_CHARS].rstrip() + "…"
    return joined


def _commit_subjects_since(cwd: str, start_sha: str | None) -> list[str]:
    """Return commit subjects authored in `cwd` since `start_sha` (exclusive)."""
    if not start_sha:
        return []
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "log", "--pretty=%s", f"{start_sha}..HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _resolve_git_head_sha(cwd: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _digest_from_prompts(prompts: list[str]) -> str | None:
    joined = "\n\n".join(p.strip() for p in prompts if p.strip())
    if not joined:
        return None
    return redact_text(joined)


def _append_session_log(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def _read_session_log(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return out
    return out


def _resolve_git_context(cwd: str) -> tuple[str | None, str | None, str | None]:
    try:
        remote = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        branch_p = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, None, None

    repo_url = remote.stdout.strip() if remote.returncode == 0 else None
    branch = branch_p.stdout.strip() if branch_p.returncode == 0 else None
    repo_label = _label_from_url(repo_url) if repo_url else None
    return repo_url, repo_label, branch


def _label_from_url(url: str) -> str | None:
    """Extract owner/repo from a git remote URL."""
    cleaned = url.rstrip("/").removesuffix(".git")
    if cleaned.startswith("git@"):
        # git@github.com:acme/api
        _, _, path = cleaned.partition(":")
        return path or None
    if "://" in cleaned:
        # https://github.com/acme/api
        _, _, path = cleaned.partition("://")
        _, _, after_host = path.partition("/")
        return after_host or None
    return cleaned or None


def _repo_allowed(repo_url: str | None, allowlist: list[str], denylist: list[str]) -> bool:
    if repo_url is None:
        # MVP: allow local-only repos (no remote).
        return True
    if any(pat and pat in repo_url for pat in denylist):
        return False
    if allowlist:
        return any(pat in repo_url for pat in allowlist)
    return True


def _normalize_path(path: str) -> str:
    home = str(Path.home())
    if path.startswith(home):
        return "~" + path[len(home) :]
    return path


def _spawn_flusher_if_needed() -> None:
    pid_path = flusher_pid_file()
    if pid_path.exists():
        try:
            existing_pid = int(pid_path.read_text().strip())
            os.kill(existing_pid, 0)
            return  # Flusher already running.
        except (ValueError, OSError):
            try:
                pid_path.unlink()
            except OSError:
                pass

    # Detach via double-fork so the hook returns immediately.
    try:
        first = os.fork()
        if first > 0:
            return
    except OSError:
        return

    os.setsid()
    try:
        second = os.fork()
        if second > 0:
            os._exit(0)
    except OSError:
        os._exit(0)

    try:
        pid_path.write_text(str(os.getpid()))
        # Re-exec into a flusher process. We exec the same binary with the
        # internal `_flush` argv so it picks up its own working directory.
        os.execvp("daylee", ["daylee", "_flush"])
    except OSError:
        os._exit(0)


def main_stdin() -> int:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""

    # Detach via double-fork so Claude Code's hook returns immediately.
    # The git subprocess lookup, queue write, and flusher spawn all run
    # in the detached grandchild — keeping `/clear` and other hook-firing
    # commands out of our critical path.
    try:
        first = os.fork()
    except OSError:
        # Fork failed; fall back to inline so the event is not dropped.
        return forward_one_event(raw)
    if first > 0:
        return 0

    os.setsid()
    try:
        second = os.fork()
    except OSError:
        os._exit(0)
    if second > 0:
        os._exit(0)

    try:
        forward_one_event(raw)
    finally:
        os._exit(0)


# Exposed for tests
hostname = socket.gethostname
