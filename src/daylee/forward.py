"""Hook target: read a Claude Code hook event from stdin, redact, queue it."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import queue as queue_mod
from .config import load_config
from .paths import flusher_pid_file
from .redact import redact_text


# Map Claude Code hook names to our internal event kinds.
_HOOK_KINDS = {
    "SessionStart": "session_start",
    "SessionEnd": "session_end",
    "Stop": "session_end",  # Stop events terminate a turn; we treat as session_end fallback if SessionEnd is absent
}


def forward_one_event(raw_payload: str) -> int:
    """Process a single hook event read from stdin. Returns process exit code."""
    config = load_config()

    try:
        payload: dict[str, Any] = json.loads(raw_payload) if raw_payload else {}
    except json.JSONDecodeError:
        return 0  # Don't fail the hook on a malformed payload; just drop it.

    hook_name = payload.get("hook_event_name") or payload.get("hook") or ""
    kind = _HOOK_KINDS.get(hook_name)
    if not kind:
        return 0

    cc_session_id = payload.get("session_id") or payload.get("sessionId") or ""
    if not cc_session_id:
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    repo_url, repo_label, branch = _resolve_git_context(cwd)

    if not _repo_allowed(repo_url, config.repo_allowlist, config.repo_denylist):
        return 0

    event: dict[str, Any] = {
        "cc_session_id": cc_session_id,
        "kind": kind,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cwd": _normalize_path(cwd),
    }
    if repo_url:
        event["repo_url"] = repo_url
    if repo_label:
        event["repo_label"] = repo_label
    if branch:
        event["branch"] = branch

    if kind == "session_end":
        # MVP: we don't yet track per-tool counts or files_touched on the
        # device side. V1 will accumulate these from PostToolUse hooks.
        digest = payload.get("transcript") or payload.get("user_prompt")
        if digest and config.send_raw_prompts:
            event["prompt_digest"] = redact_text(str(digest))

    queue_mod.append_event(event)
    _spawn_flusher_if_needed()
    return 0


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
