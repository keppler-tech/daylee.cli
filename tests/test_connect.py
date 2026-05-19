"""Tests for ``daylee connect`` — the MCP-config printer."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from daylee import config as config_mod
from daylee.cli import main


def _link(server_url: str = "https://daylee.test") -> None:
    config_mod.save_config(config_mod.Config(server_url=server_url))
    config_mod.save_credentials(
        config_mod.Credentials(
            device_id="dev-1",
            device_token="tok-abc",  # noqa: S106
            platform_user_id="U1",
            platform_workspace_id="T1",
        )
    )


def test_connect_requires_login(isolated_config_dir: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["connect"])
    assert result.exit_code != 0
    assert "daylee login" in result.output


def test_connect_default_prints_all_agents(isolated_config_dir: Path):
    _link()
    runner = CliRunner()
    result = runner.invoke(main, ["connect"])
    assert result.exit_code == 0, result.output
    out = result.output
    # JSON snippet for Claude Code / Cursor
    assert '"daylee"' in out
    assert "https://daylee.test/api/mcp/" in out
    assert "Bearer tok-abc" in out
    # TOML snippet for Codex
    assert "[mcp_servers.daylee]" in out
    assert "Codex" in out


def test_connect_claude_code_outputs_json_snippet(
    isolated_config_dir: Path, isolated_claude_settings: Path
):
    _link()
    runner = CliRunner()
    result = runner.invoke(main, ["connect", "--agent", "claude-code"])
    assert result.exit_code == 0, result.output

    # MCP snippet — the LAST `{...}` block, after the settings-install header.
    mcp_start = result.output.index('{\n  "mcpServers"')
    mcp_end = result.output.rindex("}") + 1
    payload = json.loads(result.output[mcp_start:mcp_end])
    assert payload["mcpServers"]["daylee"]["type"] == "http"
    assert payload["mcpServers"]["daylee"]["url"] == "https://daylee.test/api/mcp/"
    assert payload["mcpServers"]["daylee"]["headers"]["Authorization"] == "Bearer tok-abc"


def test_connect_claude_code_enables_plugin_in_settings(
    isolated_config_dir: Path, isolated_claude_settings: Path
):
    _link()
    runner = CliRunner()
    result = runner.invoke(main, ["connect", "--agent", "claude-code"])
    assert result.exit_code == 0, result.output

    assert isolated_claude_settings.exists()
    settings = json.loads(isolated_claude_settings.read_text())
    assert settings["extraKnownMarketplaces"]["daylee"] == {
        "source": {"source": "github", "repo": "keppler-tech/daylee.cli"}
    }
    assert settings["enabledPlugins"]["daylee@daylee"] is True
    assert "Enabled /daylee:update" in result.output


def test_connect_claude_code_preserves_existing_settings(
    isolated_config_dir: Path, isolated_claude_settings: Path
):
    _link()
    isolated_claude_settings.parent.mkdir(parents=True, exist_ok=True)
    isolated_claude_settings.write_text(
        json.dumps(
            {
                "env": {"FOO": "bar"},
                "enabledPlugins": {"other@somewhere": True},
                "extraKnownMarketplaces": {
                    "somewhere": {"source": {"source": "github", "repo": "x/y"}}
                },
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["connect", "--agent", "claude-code"])
    assert result.exit_code == 0, result.output

    settings = json.loads(isolated_claude_settings.read_text())
    assert settings["env"] == {"FOO": "bar"}
    assert settings["enabledPlugins"]["other@somewhere"] is True
    assert settings["enabledPlugins"]["daylee@daylee"] is True
    assert settings["extraKnownMarketplaces"]["somewhere"] == {
        "source": {"source": "github", "repo": "x/y"}
    }
    assert settings["extraKnownMarketplaces"]["daylee"] == {
        "source": {"source": "github", "repo": "keppler-tech/daylee.cli"}
    }


def test_connect_claude_code_is_idempotent(
    isolated_config_dir: Path, isolated_claude_settings: Path
):
    _link()
    runner = CliRunner()

    first = runner.invoke(main, ["connect", "--agent", "claude-code"])
    assert first.exit_code == 0, first.output
    assert "Enabled /daylee:update" in first.output

    second = runner.invoke(main, ["connect", "--agent", "claude-code"])
    assert second.exit_code == 0, second.output
    assert "already enabled" in second.output


def test_connect_codex_outputs_toml_snippet(isolated_config_dir: Path):
    _link()
    runner = CliRunner()
    result = runner.invoke(main, ["connect", "--agent", "codex"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "[mcp_servers.daylee]" in out
    assert 'url = "https://daylee.test/api/mcp/"' in out
    assert 'Authorization = "Bearer tok-abc"' in out
    assert "~/.codex/config.toml" in out


def test_status_reports_linked_user(isolated_config_dir: Path):
    _link()
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0, result.output
    assert "Linked user:   U1 (T1)" in result.output


def test_status_reports_unlinked(isolated_config_dir: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0, result.output
    assert "(none" in result.output
