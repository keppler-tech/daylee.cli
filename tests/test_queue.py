from pathlib import Path

from daylee import queue as queue_mod


def test_append_and_read(isolated_config_dir: Path):
    queue_mod.append_event({"a": 1})
    queue_mod.append_event({"a": 2})
    queue_mod.append_event({"a": 3})

    batch = queue_mod.read_batch(limit=10)
    assert [e["a"] for e in batch] == [1, 2, 3]


def test_consume_batch_drops_only_consumed(isolated_config_dir: Path):
    for i in range(5):
        queue_mod.append_event({"i": i})

    batch = queue_mod.read_batch(limit=3)
    assert [e["i"] for e in batch] == [0, 1, 2]
    queue_mod.consume_batch(3)

    remaining = queue_mod.read_batch(limit=10)
    assert [e["i"] for e in remaining] == [3, 4]


def test_queue_size(isolated_config_dir: Path):
    assert queue_mod.queue_size() == 0
    queue_mod.append_event({"x": 1})
    queue_mod.append_event({"x": 2})
    assert queue_mod.queue_size() == 2


def test_skips_corrupt_lines(isolated_config_dir: Path):
    queue_mod.append_event({"ok": 1})
    # Append a malformed line directly:
    queue_path = isolated_config_dir / "queue.jsonl"
    with queue_path.open("a") as f:
        f.write("not-json\n")
    queue_mod.append_event({"ok": 2})

    batch = queue_mod.read_batch(limit=10)
    assert [e["ok"] for e in batch] == [1, 2]


def test_consume_empty_is_safe(isolated_config_dir: Path):
    queue_mod.consume_batch(5)  # No file yet — must not raise.


def test_atomic_replace_on_consume(isolated_config_dir: Path):
    """After consume, the file holds only the remaining lines, not partial state."""
    for i in range(4):
        queue_mod.append_event({"i": i})
    queue_mod.consume_batch(2)

    queue_path = isolated_config_dir / "queue.jsonl"
    text = queue_path.read_text()
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 2
    # No partial JSON
    import json
    for line in lines:
        json.loads(line)
