"""Durable home for the widgets a learner generates in the player.

Disk-backed today: one `data/<video>/user_concepts.json` array per video, deliberately
separate from the pipeline's `concepts.json` (analyze.py rewrites that file wholesale) and
from the `concepts` table (agent/db.py upsert_concepts deletes and re-inserts it from disk).

The module-level lock is only enough because serve.py runs a single uvicorn process with no
`--workers`. A second worker or a second replica needs a Postgres-backed implementation of
`load`/`save` instead — that is the trigger to swap, and nothing outside this module has to
change when it happens.
"""
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from agent import flags

DATA = Path("data")
FILENAME = "user_concepts.json"
CORRUPT_FILENAME = "user_concepts.corrupt.json"
GUEST_OWNER = "guest"  # everyone signed out shares one owner, so team widgets stay theirs
MAX_PER_OWNER = 50
MAX_PER_VIDEO = 300

_VIDEO_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_lock = threading.Lock()


class StoreUnavailable(Exception):
    """The store could not be read — bad id, unreadable file, or content we won't trust."""


class BadVideoId(StoreUnavailable):
    """A client error rather than a storage one — callers can map it to a 4xx."""


class SaveRejected(Exception):
    """The store is fine; policy says this spec doesn't get persisted."""


def _switch(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default) != "0"


def _dir(video: str) -> Path:
    if not _VIDEO_RE.match(video or ""):
        raise BadVideoId(f"unusable video id: {video!r}")
    return DATA / video


def _path(video: str) -> Path:
    return _dir(video) / FILENAME


def load(video: str) -> list[dict]:
    """Every saved widget for this video, oldest timestamp first.

    Raises rather than returning [] on damaged content: an empty list here would let the
    next save atomically replace a recoverable file with a single entry."""
    try:
        raw = _path(video).read_text()
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as e:
        raise StoreUnavailable(str(e)) from e
    return _parse(raw, video)


def _parse(raw: str, video: str) -> list[dict]:
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as e:
        raise StoreUnavailable(f"{video}/{FILENAME} is not valid JSON: {e}") from e
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise StoreUnavailable(f"{video}/{FILENAME} is not an array of specs")
    return rows


def spec_id(video: str, spec: dict) -> str:
    """Content-addressed, so re-generating the same widget replaces instead of duplicating.

    Deliberately not the inference-cache key: that one rotates with PROMPT_VERSION and the
    model name, and _region_hash rounds the box to two decimals (see serve.py)."""
    key = json.dumps(
        [video, round(float(spec.get("time") or 0), 2), spec.get("widget"),
         spec.get("title"), spec.get("params")],
        sort_keys=True, default=str)
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def save(video: str, spec: dict, owner: str, replaces: str = "",
         replaces_key: str = "") -> dict:
    if not _switch("KEDU_SAVE_WIDGETS"):
        raise SaveRejected("saving generated widgets is switched off")
    if not owner:
        raise SaveRejected("no owner to save this widget under")
    if owner == GUEST_OWNER and not flags.load()["guest_saves"]:
        raise SaveRejected("guest widgets aren't being kept — sign in to save this")
    widget = spec.get("widget")
    if not widget:
        raise SaveRejected("only widget specs are saved, not answers")
    # Off by default: a notebook's cells are executed on render (see Notebook in widgets.jsx),
    # so a persisted one runs for every later visitor. Opt in only once those cells are
    # confined to a worker with no DOM, storage or network reach.
    if widget == "notebook" and not _switch("KEDU_SAVE_NOTEBOOKS", "0"):
        raise SaveRejected("notebook widgets aren't shared — they execute on open")

    entry = {**spec, "id": spec_id(video, spec), "owner": owner,
             "created_at": datetime.now(timezone.utc).isoformat()}
    if replaces_key:
        entry["replaces_key"] = replaces_key

    with _lock:
        rows = _read_for_write(video)
        # Ids are content-addressed, so two people can generate byte-identical specs. The
        # first one to save it keeps it — otherwise a guest replaying a cached team widget
        # would quietly take it over, and with it the right to replace it.
        twin = next((r for r in rows if r.get("id") == entry["id"]), None)
        if twin is not None and twin.get("owner") != owner:
            return twin
        rows = [r for r in rows if not _superseded_by(r, entry, owner, replaces)]
        _check_caps(rows, owner)
        rows.append(entry)
        rows.sort(key=lambda r: r.get("time") or 0)
        _write(video, rows)
    return entry


def _read_for_write(video: str) -> list[dict]:
    """Quarantine damaged content before it can be overwritten, and refuse this write —
    the next one starts from a clean file, and the bad bytes stay around to look at."""
    path = _path(video)
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as e:
        raise StoreUnavailable(str(e)) from e
    try:
        return _parse(raw, video)
    except StoreUnavailable:
        try:
            path.replace(_dir(video) / CORRUPT_FILENAME)
        except OSError:
            pass  # a failed quarantine still must not overwrite the bad bytes
        raise


def _superseded_by(row: dict, entry: dict, owner: str, replaces: str) -> bool:
    if row.get("id") == entry["id"]:
        return row.get("owner") == owner
    return bool(replaces) and row.get("id") == replaces and row.get("owner") == owner


def _check_caps(rows: list[dict], owner: str) -> None:
    if len(rows) >= MAX_PER_VIDEO:
        raise SaveRejected(f"this video already holds {MAX_PER_VIDEO} saved widgets")
    if sum(1 for r in rows if r.get("owner") == owner) >= MAX_PER_OWNER:
        raise SaveRejected(f"you already saved {MAX_PER_OWNER} widgets on this video")


def _write(video: str, rows: list[dict]) -> None:
    directory = _dir(video)
    tmp = directory / f"{FILENAME}.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(rows, indent=1))
        os.replace(tmp, _path(video))
    except OSError as e:
        raise StoreUnavailable(f"could not write {video}/{FILENAME}: {e}") from e
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
