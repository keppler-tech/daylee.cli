from pathlib import Path

from daylee import config as config_mod


def test_load_default_when_no_file(isolated_config_dir: Path, monkeypatch):
    monkeypatch.delenv("DAYLEE_SERVER_URL", raising=False)
    cfg = config_mod.load_config()
    assert cfg.server_url == config_mod.DEFAULT_SERVER_URL


def test_round_trip_config(isolated_config_dir: Path):
    cfg = config_mod.Config(server_url="https://daylee.test")
    config_mod.save_config(cfg)

    loaded = config_mod.load_config()
    assert loaded.server_url == "https://daylee.test"


def test_credentials_round_trip(isolated_config_dir: Path):
    creds = config_mod.Credentials(
        device_id="d-1",
        device_token="tok-abc",  # noqa: S106
        platform_user_id="U1",
        platform_workspace_id="T1",
    )
    config_mod.save_credentials(creds)

    loaded = config_mod.load_credentials()
    assert loaded is not None
    assert loaded.device_id == "d-1"
    assert loaded.device_token == "tok-abc"  # noqa: S105
    assert loaded.platform_user_id == "U1"
    assert loaded.platform_workspace_id == "T1"


def test_load_credentials_missing(isolated_config_dir: Path):
    assert config_mod.load_credentials() is None


def test_credentials_file_is_chmod_600(isolated_config_dir: Path):
    import os
    import stat

    creds = config_mod.Credentials(
        device_id="d",
        device_token="t",  # noqa: S106
        platform_user_id="U",
        platform_workspace_id="W",
    )
    path = config_mod.save_credentials(creds)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
