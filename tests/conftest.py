from pathlib import Path

import pytest


@pytest.fixture
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point DAYLEE_CONFIG_DIR at a tmp dir for the test."""
    monkeypatch.setenv("DAYLEE_CONFIG_DIR", str(tmp_path))
    return tmp_path
