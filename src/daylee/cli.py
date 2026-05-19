"""Entry point for the daylee CLI."""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import click
import httpx

from . import api
from .config import (
    Credentials,
    DEFAULT_SERVER_URL,
    load_config,
    load_credentials,
    save_config,
    save_credentials,
)
from .paths import claude_settings_path, config_dir, config_file, ensure_config_dir


SUPPORTED_AGENTS = ("claude-code", "cursor", "codex", "print")

CLAUDE_MARKETPLACE_NAME = "daylee"
CLAUDE_PLUGIN_NAME = "daylee"
CLAUDE_MARKETPLACE_REPO = "keppler-tech/daylee.cli"


@click.group()
@click.version_option()
def main() -> None:
    """daylee — link your AI coding agent to your team's Daylee standups."""


@main.command()
@click.option("--server", default=None, help=f"Daylee API URL (default: {DEFAULT_SERVER_URL}).")
def login(server: str | None) -> None:
    """Link this device to your Slack user. Prints a code to paste into Slack."""
    ensure_config_dir()

    config = load_config()
    if server:
        config.server_url = server
        save_config(config)

    label = socket.gethostname()
    try:
        resp = api.request_device_code(config.server_url, device_label=label)
    except api.ApiError as e:
        raise click.ClickException(str(e))
    except httpx.HTTPError as e:
        raise click.ClickException(f"Could not reach {config.server_url}: {e}")

    code = resp["code"]
    polling_token = resp["polling_token"]
    expires_in = resp.get("expires_in", 600)

    click.echo()
    click.echo(click.style(f"  Code:  {code}", fg="cyan", bold=True))
    click.echo()
    click.echo("Paste it into Slack:")
    click.echo(click.style(f"    /daylee link {code}", fg="white", bold=True))
    click.echo()
    click.echo(f"Waiting for link ({expires_in // 60} min)…", nl=False)

    deadline = time.time() + expires_in
    while time.time() < deadline:
        try:
            poll = api.poll_device_code(config.server_url, polling_token)
        except api.CodeExpired:
            click.echo()
            raise click.ClickException("Code expired. Run `daylee login` again.")
        except (api.ApiError, httpx.HTTPError):
            time.sleep(2)
            click.echo(".", nl=False)
            continue

        if poll.get("status") == "linked":
            click.echo()
            creds = Credentials(
                device_id=poll["device_id"],
                device_token=poll["device_token"],
                platform_user_id=poll["platform_user_id"],
                platform_workspace_id=poll["platform_workspace_id"],
            )
            save_credentials(creds)
            click.echo(
                click.style(
                    f"Linked to {creds.platform_user_id} in workspace {creds.platform_workspace_id}.",
                    fg="green",
                )
            )
            click.echo("Run `daylee connect` next to wire Daylee into your coding agent.")
            return

        time.sleep(2)
        click.echo(".", nl=False)

    click.echo()
    raise click.ClickException("Timed out waiting for link.")


@main.command()
@click.option(
    "--agent",
    type=click.Choice(SUPPORTED_AGENTS),
    default="print",
    show_default=True,
    help="Which agent's MCP config snippet to render.",
)
def connect(agent: str) -> None:
    """Print MCP config you can paste into your coding agent.

    Daylee exposes a Model Context Protocol server. Once you've linked
    this device with ``daylee login``, this command prints a config
    snippet to add to your agent's MCP settings so it can call Daylee
    tools directly.
    """
    creds = load_credentials()
    if not creds:
        raise click.ClickException("Not linked yet. Run `daylee login` first.")

    config = load_config()
    mcp_url = f"{config.server_url.rstrip('/')}/api/mcp/"

    if agent == "codex":
        click.echo(_codex_snippet(mcp_url, creds.device_token))
        click.echo()
        click.echo("Append to ~/.codex/config.toml.")
        return

    if agent == "claude-code":
        settings_path, changed = _install_claude_code_plugin()
        if changed:
            click.echo(
                click.style(
                    f"Enabled /daylee:update in {settings_path}.",
                    fg="green",
                )
            )
            click.echo("Run /reload-plugins in Claude Code, or start a new session.")
        else:
            click.echo(f"/daylee:update already enabled in {settings_path}.")
        click.echo()
        click.echo("Add the Daylee MCP server to ~/.claude.json:")
        click.echo()
        snippet = _json_snippet(mcp_url, creds.device_token)
        click.echo(snippet)
        click.echo()
        click.echo("Paste the `daylee` entry under `mcpServers` in ~/.claude.json")
        click.echo("(or a project-local .mcp.json).")
        return

    if agent == "cursor":
        snippet = _json_snippet(mcp_url, creds.device_token)
        click.echo(snippet)
        click.echo()
        click.echo("Add the `daylee` entry under `mcpServers` in ~/.cursor/mcp.json.")
        return

    # Default "print" mode: show all three.
    click.echo("# Claude Code  (~/.claude.json — `mcpServers` key)")
    click.echo("# Cursor       (~/.cursor/mcp.json — `mcpServers` key)")
    click.echo(_json_snippet(mcp_url, creds.device_token))
    click.echo()
    click.echo("# Codex CLI    (~/.codex/config.toml)")
    click.echo(_codex_snippet(mcp_url, creds.device_token))


def _json_snippet(url: str, token: str) -> str:
    return json.dumps(
        {
            "mcpServers": {
                "daylee": {
                    "type": "http",
                    "url": url,
                    "headers": {"Authorization": f"Bearer {token}"},
                }
            }
        },
        indent=2,
    )


def _install_claude_code_plugin() -> tuple[Path, bool]:
    """Register the Daylee plugin in Claude Code's user settings.

    Adds entries to ``extraKnownMarketplaces`` and ``enabledPlugins`` in
    ``~/.claude/settings.json`` so Claude Code surfaces ``/daylee:update``
    on next session start. Returns ``(settings_path, changed)`` where
    ``changed`` is ``False`` when the plugin was already enabled and
    pointing at the same marketplace repo.
    """
    path = claude_settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise click.ClickException(
                f"Could not parse {path}: {exc}. Fix it manually and re-run."
            )
        if not isinstance(data, dict):
            raise click.ClickException(
                f"{path} is not a JSON object. Fix it manually and re-run."
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    marketplaces = data.setdefault("extraKnownMarketplaces", {})
    plugins = data.setdefault("enabledPlugins", {})
    plugin_key = f"{CLAUDE_PLUGIN_NAME}@{CLAUDE_MARKETPLACE_NAME}"

    desired_marketplace = {
        "source": {"source": "github", "repo": CLAUDE_MARKETPLACE_REPO}
    }
    if (
        marketplaces.get(CLAUDE_MARKETPLACE_NAME) == desired_marketplace
        and plugins.get(plugin_key) is True
    ):
        return path, False

    marketplaces[CLAUDE_MARKETPLACE_NAME] = desired_marketplace
    plugins[plugin_key] = True

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)
    return path, True


def _codex_snippet(url: str, token: str) -> str:
    return (
        "[mcp_servers.daylee]\n"
        f'url = "{url}"\n'
        "\n"
        "[mcp_servers.daylee.headers]\n"
        f'Authorization = "Bearer {token}"\n'
    )


@main.command()
def status() -> None:
    """Show CLI status: linked user, config location."""
    config = load_config()
    creds = load_credentials()

    click.echo(f"Server:        {config.server_url}")
    click.echo(f"Config dir:    {config_dir()}")
    if creds:
        click.echo(f"Linked user:   {creds.platform_user_id} ({creds.platform_workspace_id})")
        click.echo(f"Device id:     {creds.device_id}")
    else:
        click.echo("Linked user:   (none — run `daylee login`)")


@main.command()
@click.option("--server", default=None, help="Set the Daylee API URL.")
def config(server: str | None) -> None:
    """Show or update CLI config."""
    cfg = load_config()
    if server is not None:
        cfg.server_url = server
        save_config(cfg)
        click.echo(f"Wrote {config_file()}")
    click.echo(f"server_url = {cfg.server_url}")


if __name__ == "__main__":
    main()
