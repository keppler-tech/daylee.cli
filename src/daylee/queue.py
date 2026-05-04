"""Crash-safe local queue of pending events.

Each `daylee forward` invocation appends one JSONL line. The flusher
reads up to a batch, POSTs to the backend, and on success rewrites the
file via rename-replace, leaving either the old or the new content but
never a partial state.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .paths import queue_file


_MAX_QUEUE_BYTES = 5 * 1024 * 1024  # 5 MB


def append_event(event: dict, *, queue_path: Path | None = None) -> None:
    path = queue_path or queue_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and path.stat().st_size >= _MAX_QUEUE_BYTES:
        _drop_oldest(path)

    line = json.dumps(event, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def read_batch(limit: int = 50, *, queue_path: Path | None = None) -> list[dict]:
    path = queue_path or queue_file()
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(out) >= limit:
                break
    return out


def consume_batch(consumed: int, *, queue_path: Path | None = None) -> None:
    """Drop the first ``consumed`` events from the queue, atomically."""
    path = queue_path or queue_file()
    if not path.exists() or consumed <= 0:
        return

    remaining: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        skipped = 0
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if skipped < consumed:
                skipped += 1
                continue
            remaining.append(line if line.endswith("\n") else line + "\n")

    _atomic_replace(path, "".join(remaining))


def queue_size(*, queue_path: Path | None = None) -> int:
    path = queue_path or queue_file()
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _drop_oldest(path: Path) -> None:
    """Drop the oldest half of the queue when over the size cap."""
    with path.open("r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    if not lines:
        return
    keep = lines[len(lines) // 2 :]
    _atomic_replace(path, "".join(keep))


def _atomic_replace(path: Path, new_content: str) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(new_content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
