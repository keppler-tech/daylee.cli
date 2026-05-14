"""Local config + credentials for the daylee CLI."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore

import tomli_w

from .paths import config_file, credentials_file, ensure_config_dir


DEFAULT_SERVER_URL = "https://daylee.work"


@dataclass
class Config:
    server_url: str = DEFAULT_SERVER_URL


@dataclass
class Credentials:
    device_id: str
    device_token: str
    platform_user_id: str
    platform_workspace_id: str


def load_config() -> Config:
    """Load config from ~/.config/daylee/config.toml, falling back to defaults."""
    path = config_file()
    if not path.exists():
        return Config(server_url=os.environ.get("DAYLEE_SERVER_URL", DEFAULT_SERVER_URL))
    with path.open("rb") as f:
        data = tomllib.load(f)
    return Config(
        server_url=os.environ.get("DAYLEE_SERVER_URL", data.get("server_url", DEFAULT_SERVER_URL)),
    )


def save_config(config: Config) -> Path:
    ensure_config_dir()
    path = config_file()
    payload = {"server_url": config.server_url}
    with path.open("wb") as f:
        tomli_w.dump(payload, f)
    return path


def load_credentials() -> Credentials | None:
    path = credentials_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not all(k in data for k in ("device_id", "device_token", "platform_user_id", "platform_workspace_id")):
        return None
    return Credentials(
        device_id=data["device_id"],
        device_token=data["device_token"],
        platform_user_id=data["platform_user_id"],
        platform_workspace_id=data["platform_workspace_id"],
    )


def save_credentials(creds: Credentials) -> Path:
    ensure_config_dir()
    path = credentials_file()
    path.write_text(
        json.dumps(
            {
                "device_id": creds.device_id,
                "device_token": creds.device_token,
                "platform_user_id": creds.platform_user_id,
                "platform_workspace_id": creds.platform_workspace_id,
            }
        )
    )
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover — Windows etc.
        pass
    return path
