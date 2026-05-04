"""Idempotently merge daylee hook entries into Claude Code's settings.json.

Each Daylee-owned hook entry is tagged with `_daylee: true` so we can
detect and remove only our entries on uninstall, without disturbing
hooks the user has authored.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from .paths import claude_settings_path


DEFAULT_HOOKS: tuple[str, ...] = (
    "SessionStart",
    "SessionEnd",
    "PostToolUse",
    "UserPromptSubmit",
)

_BACKUP_SUFFIX = ".daylee-bak"
_DAYLEE_MARKER = "_daylee"


def install(
    hook_command: str = "daylee forward",
    hooks: Iterable[str] = DEFAULT_HOOKS,
    *,
    settings_path: Path | None = None,
) -> Path:
    """Add Daylee hook entries to ``~/.claude/settings.json``.

    Idempotent: re-running does not duplicate entries. Backs up the
    pre-existing settings.json once on first install.
    """
    path = settings_path or claude_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            backup = path.with_suffix(path.suffix + _BACKUP_SUFFIX)
            shutil.copy2(path, backup)
            existing = {}
        else:
            backup = path.with_suffix(path.suffix + _BACKUP_SUFFIX)
            if not backup.exists():
                shutil.copy2(path, backup)

    hooks_section = existing.setdefault("hooks", {})
    if not isinstance(hooks_section, dict):
        hooks_section = {}
        existing["hooks"] = hooks_section

    new_entry = {
        "matcher": "*",
        "hooks": [{"type": "command", "command": hook_command, _DAYLEE_MARKER: True}],
    }

    for hook_name in hooks:
        bucket = hooks_section.setdefault(hook_name, [])
        if not isinstance(bucket, list):
            continue
        already_installed = any(_is_daylee_entry(e) for e in bucket)
        if not already_installed:
            bucket.append(new_entry)

    path.write_text(json.dumps(existing, indent=2))
    return path


def uninstall(*, settings_path: Path | None = None) -> Path | None:
    """Remove only Daylee-tagged hook entries. Leaves user-authored hooks intact."""
    path = settings_path or claude_settings_path()
    if not path.exists():
        return None

    try:
        existing = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None

    hooks_section = existing.get("hooks")
    if not isinstance(hooks_section, dict):
        return path

    for hook_name, bucket in list(hooks_section.items()):
        if not isinstance(bucket, list):
            continue
        filtered = [e for e in bucket if not _is_daylee_entry(e)]
        if filtered:
            hooks_section[hook_name] = filtered
        else:
            del hooks_section[hook_name]

    if not hooks_section:
        existing.pop("hooks", None)

    path.write_text(json.dumps(existing, indent=2))
    return path


def is_installed(*, settings_path: Path | None = None) -> bool:
    path = settings_path or claude_settings_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return False
    hooks = data.get("hooks") or {}
    if not isinstance(hooks, dict):
        return False
    for bucket in hooks.values():
        if isinstance(bucket, list) and any(_is_daylee_entry(e) for e in bucket):
            return True
    return False


def _is_daylee_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    inner = entry.get("hooks")
    if isinstance(inner, list):
        for item in inner:
            if isinstance(item, dict) and item.get(_DAYLEE_MARKER):
                return True
    return False
