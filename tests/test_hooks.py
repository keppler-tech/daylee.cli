import json
from pathlib import Path

from daylee import hooks


def test_install_creates_file_with_daylee_marker(isolated_claude_settings: Path):
    hooks.install()
    assert isolated_claude_settings.exists()

    data = json.loads(isolated_claude_settings.read_text())
    assert "hooks" in data
    for hook_name in ("SessionStart", "SessionEnd", "PostToolUse", "UserPromptSubmit"):
        assert hook_name in data["hooks"]

    entry = data["hooks"]["SessionStart"][0]
    assert entry["matcher"] == "*"
    assert entry["hooks"][0]["_daylee"] is True
    assert entry["hooks"][0]["command"] == "daylee forward"


def test_install_is_idempotent(isolated_claude_settings: Path):
    hooks.install()
    hooks.install()
    hooks.install()

    data = json.loads(isolated_claude_settings.read_text())
    # Each hook should still have exactly one Daylee entry.
    for hook_name in ("SessionStart", "SessionEnd", "PostToolUse", "UserPromptSubmit"):
        bucket = data["hooks"][hook_name]
        daylee_entries = [e for e in bucket if e.get("hooks", [{}])[0].get("_daylee")]
        assert len(daylee_entries) == 1


def test_install_preserves_user_authored_hooks(isolated_claude_settings: Path):
    user_settings = {
        "hooks": {
            "SessionStart": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "/usr/local/bin/my-hook"}]}
            ],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo ran"}]}
            ],
        }
    }
    isolated_claude_settings.write_text(json.dumps(user_settings))

    hooks.install()

    data = json.loads(isolated_claude_settings.read_text())
    # User hooks preserved
    bucket = data["hooks"]["SessionStart"]
    assert any(
        e["hooks"][0].get("command") == "/usr/local/bin/my-hook"
        for e in bucket
        if e.get("hooks")
    )
    # Daylee hook also added
    assert any(e["hooks"][0].get("_daylee") for e in bucket if e.get("hooks"))
    # PreToolUse untouched
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo ran"


def test_uninstall_removes_only_daylee_entries(isolated_claude_settings: Path):
    user_settings = {
        "hooks": {
            "SessionStart": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "user-hook-a"}]}
            ],
        }
    }
    isolated_claude_settings.write_text(json.dumps(user_settings))

    hooks.install()
    hooks.uninstall()

    data = json.loads(isolated_claude_settings.read_text())
    # User hook should still be there; Daylee entry removed.
    bucket = data["hooks"]["SessionStart"]
    assert len(bucket) == 1
    assert bucket[0]["hooks"][0]["command"] == "user-hook-a"


def test_is_installed_reflects_state(isolated_claude_settings: Path):
    assert not hooks.is_installed()
    hooks.install()
    assert hooks.is_installed()
    hooks.uninstall()
    assert not hooks.is_installed()


def test_install_creates_backup_once(isolated_claude_settings: Path):
    isolated_claude_settings.write_text(json.dumps({"existing": True}))
    hooks.install()
    backup = isolated_claude_settings.with_suffix(isolated_claude_settings.suffix + ".daylee-bak")
    assert backup.exists()
    backup_content = json.loads(backup.read_text())
    assert backup_content == {"existing": True}
