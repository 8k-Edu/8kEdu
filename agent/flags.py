"""Runtime switches a signed-in team member can flip from the app, without a redeploy.

Distinct from the KEDU_* env switches in agent/widget_store.py: those are the operator's
kill switches, read from the process environment and fixed for the life of the server.
"""
import json
import os
import threading
from pathlib import Path

DATA = Path("data")
FILENAME = "flags.json"
DEFAULTS = {"guest_saves": True}

_lock = threading.Lock()


def _path() -> Path:
    return DATA / FILENAME


def load() -> dict:
    """Defaults overlaid with whatever is on disk. A damaged file falls back to the
    defaults rather than raising — a flag store must never take the app down."""
    try:
        stored = json.loads(_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    if not isinstance(stored, dict):
        return dict(DEFAULTS)
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def update(changes: dict) -> dict:
    known = {k: bool(v) for k, v in changes.items() if k in DEFAULTS}
    if not known:
        raise KeyError(f"no known flags in {sorted(changes)}")
    with _lock:
        merged = {**load(), **known}
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = DATA / f"{FILENAME}.tmp"
        try:
            tmp.write_text(json.dumps(merged, indent=1))
            os.replace(tmp, _path())
        finally:
            tmp.unlink(missing_ok=True)
    return merged
