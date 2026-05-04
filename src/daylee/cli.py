"""Entry point for the daylee CLI."""

from __future__ import annotations

import socket
import sys
import time

import click
import httpx

from . import api, flusher, forward, hooks, queue as queue_mod
from .config import (
    Credentials,
    DEFAULT_SERVER_URL,
    load_config,
    load_credentials,
    save_config,
    save_credentials,
)
from .paths import (
    config_dir,
    config_file,
    ensure_config_dir,
    flusher_pid_file,
)


@click.group()
@click.version_option()
def main() -> None:
    """daylee — bridges Claude Code sessions into your team's Daylee standups."""


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
            click.echo("Run `daylee install-hooks` next to start capturing sessions.")
            return

        time.sleep(2)
        click.echo(".", nl=False)

    click.echo()
    raise click.ClickException("Timed out waiting for link.")


@main.command("install-hooks")
def install_hooks() -> None:
    """Register Claude Code hooks (~/.claude/settings.json)."""
    path = hooks.install()
    click.echo(f"Installed daylee hooks into {path}")


@main.command("uninstall-hooks")
def uninstall_hooks() -> None:
    """Remove Daylee-tagged Claude Code hooks."""
    path = hooks.uninstall()
    if path is None:
        click.echo("No Claude Code settings file found; nothing to remove.")
    else:
        click.echo(f"Removed daylee hooks from {path}")


@main.command()
def status() -> None:
    """Show CLI status: linked user, queued events, hook health."""
    config = load_config()
    creds = load_credentials()
    queued = queue_mod.queue_size()
    pid_path = flusher_pid_file()

    click.echo(f"Server:        {config.server_url}")
    click.echo(f"Config dir:    {config_dir()}")
    if creds:
        click.echo(f"Linked user:   {creds.platform_user_id} ({creds.platform_workspace_id})")
        click.echo(f"Device id:     {creds.device_id}")
    else:
        click.echo("Linked user:   (none — run `daylee login`)")
    click.echo(f"Hooks:         {'installed' if hooks.is_installed() else 'not installed'}")
    click.echo(f"Queued events: {queued}")
    if pid_path.exists():
        click.echo(f"Flusher pid:   {pid_path.read_text().strip()}")


@main.command()
@click.option("--server", default=None, help="Set the Daylee API URL.")
@click.option("--send-raw-prompts/--no-send-raw-prompts", default=None)
@click.option("--add-allowlist", "add_allowlist", multiple=True, metavar="PATTERN",
              help="Add a substring to repo_allowlist (repeatable).")
@click.option("--remove-allowlist", "remove_allowlist", multiple=True, metavar="PATTERN",
              help="Remove a substring from repo_allowlist (repeatable).")
@click.option("--add-denylist", "add_denylist", multiple=True, metavar="PATTERN",
              help="Add a substring to repo_denylist (repeatable).")
@click.option("--remove-denylist", "remove_denylist", multiple=True, metavar="PATTERN",
              help="Remove a substring from repo_denylist (repeatable).")
def config(
    server: str | None,
    send_raw_prompts: bool | None,
    add_allowlist: tuple[str, ...],
    remove_allowlist: tuple[str, ...],
    add_denylist: tuple[str, ...],
    remove_denylist: tuple[str, ...],
) -> None:
    """Show or update CLI config."""
    cfg = load_config()
    changed = False
    if server is not None:
        cfg.server_url = server
        changed = True
    if send_raw_prompts is not None:
        cfg.send_raw_prompts = send_raw_prompts
        changed = True

    cfg.repo_allowlist, allow_changed = _apply_list_edits(
        cfg.repo_allowlist, add_allowlist, remove_allowlist
    )
    cfg.repo_denylist, deny_changed = _apply_list_edits(
        cfg.repo_denylist, add_denylist, remove_denylist
    )
    changed = changed or allow_changed or deny_changed

    if changed:
        save_config(cfg)
        click.echo(f"Wrote {config_file()}")

    click.echo(f"server_url       = {cfg.server_url}")
    click.echo(f"send_raw_prompts = {cfg.send_raw_prompts}")
    click.echo(f"repo_allowlist   = {cfg.repo_allowlist}")
    click.echo(f"repo_denylist    = {cfg.repo_denylist}")


def _apply_list_edits(
    current: list[str], add: tuple[str, ...], remove: tuple[str, ...]
) -> tuple[list[str], bool]:
    """Add/remove patterns while preserving order and avoiding duplicates."""
    result = list(current)
    changed = False
    for pat in add:
        if pat and pat not in result:
            result.append(pat)
            changed = True
    for pat in remove:
        if pat in result:
            result.remove(pat)
            changed = True
    return result, changed


@main.command("forward", hidden=True)
def forward_cmd() -> None:
    """Internal: hook target. Reads JSON from stdin and queues an event."""
    sys.exit(forward.main_stdin())


@main.command("_flush", hidden=True)
def flush_cmd() -> None:
    """Internal: background flusher entry point."""
    sys.exit(flusher.run())


if __name__ == "__main__":
    main()
