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


def config_file() -> Path:
    return config_dir() / "config.toml"


def credentials_file() -> Path:
    return config_dir() / "credentials.json"


def ensure_config_dir() -> Path:
    p = config_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def claude_settings_path() -> Path:
    """Resolve the Claude Code user-settings file, honoring an override for tests."""
    override = os.environ.get("DAYLEE_CLAUDE_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "settings.json"
