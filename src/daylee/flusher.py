"""Background flusher: drain the local queue into the Daylee backend."""

from __future__ import annotations

import os
import time
from pathlib import Path

from . import api, queue as queue_mod
from .config import load_config, load_credentials
from .paths import flusher_pid_file


_BATCH_SIZE = 50
_IDLE_EXIT_SECONDS = 60.0
_BACKOFF_INITIAL = 2.0
_BACKOFF_MAX = 15 * 60.0


def run() -> int:
    pid_path = flusher_pid_file()
    pid_path.write_text(str(os.getpid()))

    config = load_config()
    creds = load_credentials()
    if not creds:
        _cleanup_pid(pid_path)
        return 1

    backoff = _BACKOFF_INITIAL
    last_activity = time.time()

    try:
        while True:
            batch = queue_mod.read_batch(_BATCH_SIZE)
            if not batch:
                if time.time() - last_activity > _IDLE_EXIT_SECONDS:
                    return 0
                time.sleep(2)
                continue

            try:
                api.post_events(
                    config.server_url,
                    creds.device_token,
                    creds.device_id,
                    batch,
                )
                queue_mod.consume_batch(len(batch))
                last_activity = time.time()
                backoff = _BACKOFF_INITIAL
            except (api.DeviceUnknown, api.WorkspaceRemoved):
                # Permanent failure for this device — drop the queue and exit.
                queue_mod.consume_batch(len(batch))
                return 2
            except api.ApiError:
                time.sleep(min(backoff, _BACKOFF_MAX))
                backoff = min(backoff * 2, _BACKOFF_MAX)
            except Exception:
                time.sleep(min(backoff, _BACKOFF_MAX))
                backoff = min(backoff * 2, _BACKOFF_MAX)
    finally:
        _cleanup_pid(pid_path)


def _cleanup_pid(pid_path: Path) -> None:
    try:
        if pid_path.exists():
            pid_path.unlink()
    except OSError:
        pass
