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
# What a damaged or unreadable file falls back to. Never DEFAULTS: guest_saves is a switch a
# team member turns *off*, and corruption must not quietly turn it back on.
FAIL_CLOSED = {"guest_saves": False}

_lock = threading.Lock()


def _path() -> Path:
    return DATA / FILENAME


def load() -> dict:
    """Defaults overlaid with whatever is on disk. Never raises — a flag store must not be
    able to take the app down — but only a genuinely absent file gets the permissive
    defaults; anything unreadable falls back closed."""
    try:
        stored = json.loads(_path().read_text())
    except FileNotFoundError:
        return dict(DEFAULTS)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {**DEFAULTS, **FAIL_CLOSED}
    if not isinstance(stored, dict):
        return {**DEFAULTS, **FAIL_CLOSED}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def update(changes: dict) -> dict:
    known = {k: bool(v) for k, v in changes.items() if k in DEFAULTS}
    if not known:
        raise KeyError(f"no known flags in {sorted(changes)}")
    with _lock:
        merged = {**load(), **known}
        tmp = DATA / f"{FILENAME}.tmp"
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(merged, indent=1))
            os.replace(tmp, _path())
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    return merged
