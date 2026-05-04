"""Filesystem layout for the daylee CLI."""

from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    """Resolve the config directory, honoring DAYLEE_CONFIG_DIR for tests."""
    override = os.environ.get("DAYLEE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "daylee"


def claude_settings_path() -> Path:
    override = os.environ.get("DAYLEE_CLAUDE_SETTINGS")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "settings.json"


def config_file() -> Path:
    return config_dir() / "config.toml"


def credentials_file() -> Path:
    return config_dir() / "credentials.json"


def queue_file() -> Path:
    return config_dir() / "queue.jsonl"


def flusher_pid_file() -> Path:
    return config_dir() / "flusher.pid"


def sessions_dir() -> Path:
    return config_dir() / "sessions"


def session_log_path(cc_session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cc_session_id)
    return sessions_dir() / f"{safe}.jsonl"


def log_file() -> Path:
    return config_dir() / "log"


def ensure_config_dir() -> Path:
    p = config_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p
