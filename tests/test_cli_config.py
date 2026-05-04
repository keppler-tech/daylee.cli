"""Tests for the `daylee config` subcommand's allowlist/denylist editing."""

from pathlib import Path

from click.testing import CliRunner

from daylee.cli import main
from daylee.config import load_config


def test_add_denylist_pattern(isolated_config_dir: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["config", "--add-denylist", "github.com/oleg/personal"])
    assert result.exit_code == 0, result.output

    cfg = load_config()
    assert cfg.repo_denylist == ["github.com/oleg/personal"]


def test_add_multiple_patterns_at_once(isolated_config_dir: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "config",
            "--add-denylist", "github.com/oleg/",
            "--add-denylist", "gitlab.com/me/",
            "--add-allowlist", "github.com/acme/",
        ],
    )
    assert result.exit_code == 0, result.output

    cfg = load_config()
    assert cfg.repo_denylist == ["github.com/oleg/", "gitlab.com/me/"]
    assert cfg.repo_allowlist == ["github.com/acme/"]


def test_add_is_idempotent(isolated_config_dir: Path):
    runner = CliRunner()
    runner.invoke(main, ["config", "--add-denylist", "github.com/oleg/"])
    runner.invoke(main, ["config", "--add-denylist", "github.com/oleg/"])

    cfg = load_config()
    assert cfg.repo_denylist == ["github.com/oleg/"]


def test_remove_denylist_pattern(isolated_config_dir: Path):
    runner = CliRunner()
    runner.invoke(
        main,
        [
            "config",
            "--add-denylist", "github.com/a/",
            "--add-denylist", "github.com/b/",
        ],
    )
    result = runner.invoke(main, ["config", "--remove-denylist", "github.com/a/"])
    assert result.exit_code == 0, result.output

    cfg = load_config()
    assert cfg.repo_denylist == ["github.com/b/"]


def test_remove_unknown_is_safe(isolated_config_dir: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["config", "--remove-denylist", "no-such-pattern"])
    assert result.exit_code == 0, result.output


def test_show_only_when_no_flags(isolated_config_dir: Path):
    """`daylee config` with no flags prints current values without writing."""
    runner = CliRunner()
    result = runner.invoke(main, ["config"])
    assert result.exit_code == 0
    assert "repo_denylist    = []" in result.output
    assert "repo_allowlist   = []" in result.output
    # No "Wrote" line because nothing changed
    assert "Wrote" not in result.output
