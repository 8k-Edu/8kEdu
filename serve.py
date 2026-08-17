"""Ask endpoint: selected transcript + user intent → widget spec.

Usage: uv run serve.py [--backend mlx|openai] [--port 8756]
POST /api/widget {"text": "...", "time": 1234.5, "ask": "let me play with the matrix"}
→ concept spec JSON (same shape the offline pipeline emits)
"""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from urllib.request import Request, urlopen

import uvicorn
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent import flags, widget_store

from analyze import (BACKEND_CHOICES, compose_system, detect_genre, extract_json, make_backend,
                     openrouter_backend, resolve_frame, valid)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA = Path("data")
DEFAULT_VIDEO = "42L1q1Z4Ojc"  # metadata only — its keyframes are neither on disk nor backfilled
PROMPT_VERSION = "v2"  # bump when SYSTEM/prompt changes → new cache keys, no stale serves
WIDGET_MAX_PX = int(os.environ.get("KEDU_MAX_PX", "768"))
_frames_cache: dict[str, list] = {}
backend = None  # set in main()
info = {"backend": "?", "model": "?", "mode": "?"}
_byok_keys: dict[str, str] = {}
_byok_lock = threading.Lock()
_auth_cache: dict[str, dict] = {}
_auth_lock = threading.Lock()
_AUTH_TTL_MAX = 300  # recheck with Supabase at least this often, whatever the JWT claims

# R4 — frame-level cache. Identical (video, frame, genre, ask) across users → no VLM call.
try:
    from agent import db as _db
    _db.load_env()  # AGENT_HANDLE must be set before the first request logs an event
except Exception:
    _db = None


def _handle() -> str:
    return os.environ.get("AGENT_HANDLE", "demo")


def _token_expiry(token: str) -> float:
    """`exp` out of the JWT payload, capped so a long-lived token still gets rechecked.
    No signature check needed — Supabase already vouched for the token; this only bounds
    how long we trust our own cache after a sign-out or a deleted account."""
    ceiling = time.time() + _AUTH_TTL_MAX
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return min(float(claims["exp"]), ceiling)
    except Exception:
        return ceiling


def _identify(authorization: str | None) -> dict:
    """{handle, email} for a verified Supabase session. Raises CloudUnavailable otherwise."""
    if not authorization or not authorization.startswith("Bearer "):
        raise CloudUnavailable("cloud requires signing in")
    token = authorization.removeprefix("Bearer ").strip()
    with _auth_lock:
        cached = _auth_cache.get(token)
    if cached and cached["expires_at"] > time.time():
        return cached
    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    publishable_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    if not base_url or not publishable_key:
        raise CloudUnavailable("cloud identity is not configured")
    request = Request(
        f"{base_url}/auth/v1/user",
        headers={"apikey": publishable_key, "Authorization": f"Bearer {token}"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            user = json.loads(response.read())
    except Exception as error:
        with _auth_lock:
            _auth_cache.pop(token, None)
        raise CloudUnavailable("session expired — sign in again") from error
    identity = {"handle": f"auth-{user['id']}", "email": (user.get("email") or "").lower(),
                "expires_at": _token_expiry(token)}
    with _auth_lock:
        _auth_cache[token] = identity
    return identity


def _authenticated_handle(authorization: str | None) -> str:
    return _identify(authorization)["handle"]


def _fire_event(payload: dict) -> None:
    if not _db:
        return
    _db.enqueue_widget_event(payload)


def _owner_for(authorization: str | None) -> str:
    """Who a saved widget belongs to — see agent/widget_store.py.
    Unlike the cloud path this runs on every request, including handlers called directly in
    tests, where `authorization` is still FastAPI's unresolved Header default."""
    if not isinstance(authorization, str):
        return widget_store.GUEST_OWNER
    try:
        return _authenticated_handle(authorization)
    except CloudUnavailable:
        return widget_store.GUEST_OWNER


def _team() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("KEDU_TEAM", "").split(",") if e.strip()}


def _on_the_team(email: str) -> bool:
    """An entry is either a whole address or a domain written `@example.com`."""
    email = email.lower()
    if not email:
        return False
    return any(email == entry or (entry.startswith("@") and email.endswith(entry))
               for entry in _team())


def _team_member(authorization: str | None) -> str | None:
    """A signed-in stranger is not a teammate. Supabase sign-up is open, so authentication
    alone can't gate a privileged action — the allowlist is the server's own, out of KEDU_TEAM,
    and an unset one means nobody qualifies."""
    try:
        identity = _identify(authorization)
    except CloudUnavailable:
        return None
    return identity["handle"] if _on_the_team(identity["email"]) else None


def _persisted(spec: dict, video: str, owner: str | None, ev: dict,
               replaces: str = "", replaces_key: str = "") -> dict:
    """The generated spec plus whether it made it into the store the timeline reloads.
    Answers carry no widget, so they stay ephemeral like they always were."""
    if not spec.get("widget"):
        return spec
    try:
        entry = widget_store.save(video, spec, owner or "", replaces=replaces,
                                  replaces_key=replaces_key)
    except widget_store.SaveRejected as e:
        return {**spec, "saved": False, "save_error": str(e)}
    except (widget_store.StoreUnavailable, OSError) as e:
        # Losing the save must never cost the learner the generation they just waited for.
        _fire_event({**ev, "kind": "save", "error": str(e)[:200]})
        return {**spec, "saved": False, "save_error": "this widget couldn't be saved"}
    return {**spec, "id": entry["id"], "saved": True}


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


# The genre segment is appended only for a real lens (not None/"general"), so the legacy call
# (genre omitted) reproduces the pre-genre key byte-for-byte — existing cached widgets still hit.
def _prompt_hash(video: str, frame: str, context: str, genre: str | None = None,
                 model: str | None = None) -> str:
    g = f"|g={genre}" if genre and genre != "general" else ""
    key = f"{PROMPT_VERSION}|{model or info.get('model','?')}|{video}|{frame}|{context}{g}"
    return hashlib.sha256(key.encode()).hexdigest()


def _region_hash(video: str, frame: str, x: float, y: float, w: float, h: float,
                 genre: str | None = None, model: str | None = None) -> str:
    box = f"{x:.2f},{y:.2f},{w:.2f},{h:.2f}"  # what's in the box drives the result, not the words
    g = f"|g={genre}" if genre and genre != "general" else ""
    key = f"{PROMPT_VERSION}|region|{model or info.get('model','?')}|{video}|{frame}|{box}{g}"
    return hashlib.sha256(key.encode()).hexdigest()


_lru: "OrderedDict[str, dict]" = OrderedDict()
_LRU_MAX = 256


def _cache_get(h: str):
    hit = _lru.get(h)
    if hit is not None:
        _lru.move_to_end(h)
        return hit
    if not _db:
        return None
    try:
        result = _db.cache_get(h)
    except Exception:
        return None
    if result is not None:
        _lru_put(h, result)
    return result


def _lru_put(h: str, result: dict):
    _lru[h] = result
    _lru.move_to_end(h)
    while len(_lru) > _LRU_MAX:
        _lru.popitem(last=False)


def _cache_put(h: str, video: str, result: dict):
    _lru_put(h, result)
    if not _db:
        return
    try:
        _db.cache_put(h, video, info.get("model", "?"), result)
    except Exception:
        pass


def _cache_get_first(hashes: list[str]):
    """Try candidate hashes in order (new genre-keyed first, legacy second) and serve the first
    hit — so pre-genre widgets keep serving untouched; only a full miss generates + writes new."""
    for h in hashes:
        r = _cache_get(h)
        if r is not None:
            return r
    return None


_genre_cache: dict[str, str] = {}


def _genre_for(video: str, text: str) -> str:
    """Genre lens for this video: curator-assigned (db) if known, else detected from the passage,
    else 'general' (base prompt → legacy cache key). Resolved once per video, then in-process."""
    g = _genre_cache.get(video)
    if g is not None:
        return g
    g = None
    if _db:
        try:
            g = _db.video_genre(video)
        except Exception:
            g = None
    g = g or detect_genre([{"text": text or "", "start": 0.0}])
    _genre_cache[video] = g
    return g


class Ask(BaseModel):
    text: str
    time: float
    ask: str = ""
    video: str = DEFAULT_VIDEO
    cloud: bool = False
    replaces: str = ""       # id of the saved widget this refinement supersedes
    replaces_key: str = ""   # pipeline concepts carry no id — see mergeConcepts in timeline.js
    current_spec: dict | None = None


def frames_for(video: str) -> list[dict]:
    """frames.json when it's local, else the frames table — the manifest is only git-tracked
    for some videos, and a bare read_text() here 500s before any frame handling runs."""
    if video in _frames_cache:
        return _frames_cache[video]
    try:
        manifest = json.loads((DATA / video / "frames.json").read_text())
    except OSError:
        try:
            manifest = _db.frames_manifest(video) if _db else []
        except Exception:
            manifest = []
    if manifest:  # an empty result may just be a DB blip — don't pin it for the process
        _frames_cache[video] = manifest
    return manifest


def nearest_frame(video: str, t: float) -> dict | None:
    """None when the video has no manifest anywhere — callers turn that into the same
    keyframes-missing answer a frameless video already gets, not a 500 out of min()."""
    frames = frames_for(video)
    return min(frames, key=lambda f: abs(f["time"] - t)) if frames else None


def _no_manifest(video: str, t: float, kind: str) -> dict:
    """Fire an event so widget_events records these misses too; every other error path in
    the handlers does the same. Otherwise 'no manifest anywhere' is invisible to /agent/perf."""
    _fire_event({"video_id": video, "t_s": t, "kind": kind, "spec_valid": False,
                 "error": "no manifest"})
    return {"error": "this video hasn't been processed yet — no keyframe manifest on disk or in Supabase"}


def _no_keyframes(kind: str) -> dict:
    return {"error": f"this video's keyframes aren't on disk — reprocess it (⚡ Process this video) to enable {kind} asks"}


_recovering: dict[tuple[str, str], threading.Lock] = {}
_recovering_lock = threading.Lock()


def _fetch_one_frame(video: str, t_s: float, frame_file: str, frames_dir: Path) -> Path | None:
    """Imported lazily so analyze.py stays importable in the contained image, which has
    neither agent/ nor yt-dlp."""
    from ingest import fetch_one_frame
    return fetch_one_frame(video, t_s, frame_file, frames_dir,
                           timeout=int(os.environ.get("KEDU_RECOVER_TIMEOUT", "60")))


def _publish_recovered(video: str, t_s: float, path: Path) -> None:
    """So the next machine reads it out of the bucket instead of downloading it again."""
    from agent import db, storage
    if storage.enabled():
        db.upsert_frames(video, [(t_s, storage.upload_frame(video, path))])


def _recover_frame(video: str, fr: dict, src: Path) -> tuple[Path, str, int]:
    """Last resort for a frame on no disk and in no bucket: pull that one moment from YouTube.
    Never raises — on failure it returns `src` untouched, so the caller's not-on-disk handling
    fires. Single-flighted per (video, frame): scrubbing must not spawn a yt-dlp per click."""
    if os.environ.get("KEDU_RECOVER_FRAMES", "1") == "0":
        return src, "off", 0
    with _recovering_lock:
        lock = _recovering.setdefault((video, fr["file"]), threading.Lock())
    t0 = time.perf_counter()
    with lock:
        if src.exists():  # another thread recovered it while we waited
            return src, "recovered", _ms(t0)
        try:
            got = _fetch_one_frame(video, fr["time"], fr["file"], src.parent)
        except Exception:
            return src, "miss", _ms(t0)
        if got is None:
            return src, "miss", _ms(t0)
        try:
            _publish_recovered(video, fr["time"], got)
        except Exception:
            pass  # the learner still gets their widget; the next machine just re-recovers
        return got, "recovered", _ms(t0)


def _frame_path(ev: dict, video: str, fr: dict) -> Path:
    """Local jpg, else Supabase Storage, else that one frame pulled from YouTube. Only reached
    on a cache miss, so a cached widget never triggers a download. A miss at every tier returns
    the absent path so the caller's own not-on-disk handling fires unchanged."""
    src, frame_source, t_fetch = resolve_frame(DATA / video / "frames" / fr["file"], video)
    if frame_source == "miss":
        src, frame_source, t_recover = _recover_frame(video, fr, src)
        t_fetch += t_recover
    ev.update(frame_source=frame_source, t_frame_fetch_ms=t_fetch)
    return src


SS_MAX_ROWS, SS_MAX_COLS = 5, 8


def _clamp_spreadsheet(spec: dict) -> dict:
    """Small local models ignore the prompt's 'at most 8x5' hint, so enforce it here:
    trim the grid to SS_MAX_ROWS x SS_MAX_COLS and drop an out-of-range highlight."""
    if spec.get("widget") != "spreadsheet":
        return spec
    p = spec.get("params")
    if not isinstance(p, dict) or not isinstance(p.get("cells"), list):
        return spec
    p["cells"] = [row[:SS_MAX_COLS] for row in p["cells"][:SS_MAX_ROWS] if isinstance(row, list)]
    hi = p.get("highlight")
    if isinstance(hi, dict) and (hi.get("row", 0) >= len(p["cells"]) or hi.get("col", 0) >= SS_MAX_COLS):
        p["highlight"] = None
    return spec


REFINEMENT_SOURCE_MAX_CHARS = 12000


def _source_size(spec: dict) -> int:
    return len(json.dumps(spec, ensure_ascii=False, separators=(",", ":")))


def _bounded_refinement_source(source: dict) -> tuple[dict | None, str | None]:
    try:
        spec = json.loads(json.dumps(source))
    except (TypeError, ValueError):
        return None, "the current widget could not be serialized"
    params = spec.get("params")
    if not isinstance(params, dict):
        return None, "the current widget has no editable parameters"
    widget = spec.get("widget")
    cells = params.get("cells")
    if widget in {"notebook", "spreadsheet"} and not isinstance(cells, list):
        return None, "the current widget has invalid editable parameters"
    editable_cells = cells if widget in {"notebook", "spreadsheet"} else []
    for cell in editable_cells:
        if widget == "notebook" and not isinstance(cell, str):
            return None, "the current notebook has an invalid cell"
        if widget == "spreadsheet" and not isinstance(cell, list):
            return None, "the current spreadsheet has an invalid row"
    if _source_size(spec) > REFINEMENT_SOURCE_MAX_CHARS:
        return None, "the current widget is too large to refine"
    return spec, None


def _refinement_context(req: Ask, source: dict) -> str:
    return (
        f'Teacher is saying: "{req.text[:1200]}"\n\n'
        f'The learner wants this edit: "{req.ask[:300]}"\n\n'
        "Edit this authoritative current widget spec and return a complete replacement spec. "
        "Make the smallest change that fulfills the edit. Keep the widget type unchanged — a "
        "different type means starting a new widget, not refining this one. Preserve every unrelated "
        "field. For notebooks, repair the supplied cells "
        "when needed instead of replacing them with an unrelated example. For spreadsheets, preserve existing "
        "rows and columns except for the requested rename or addition.\n\n"
        f"CURRENT WIDGET SPEC:\n{json.dumps(source, ensure_ascii=False, separators=(',', ':'))}\n\n"
        "Emit the complete replacement concept spec JSON."
    )


def _refinement_widget_type_error(source: dict | None, spec: dict) -> str | None:
    """Refining never converts: a different widget type means building a new widget instead."""
    source_widget = source.get("widget") if source else None
    if source_widget and spec.get("widget") != source_widget:
        return "the refinement changed widget type; your current widget was unchanged"
    return None


class CloudUnavailable(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _cloud_ctx(handle: str):
    """Resolve a cloud (OpenRouter) backend for this learner.
    Returns (backend, metered, model_name). BYOK key → unmetered; else platform key + credits.
    Raises CloudUnavailable when the learner can't pay (no key, no credits, billing offline)."""
    if not _db:
        raise CloudUnavailable("billing offline")
    mdl = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    with _byok_lock:
        key = _byok_keys.get(handle)
    if key:
        return openrouter_backend(key, mdl), False, mdl
    platform = os.environ.get("OPENROUTER_API_KEY")
    if not platform:
        raise CloudUnavailable("cloud not configured (no OPENROUTER_API_KEY)")
    if _db.user_billing(handle)["credits"] <= 0:
        raise CloudUnavailable("out of credits — add your own OpenRouter key or use the local model")
    return openrouter_backend(platform, mdl), True, mdl


def _with_billing(obj: dict, cloud: bool, model: str, credits_left):
    """Return a copy annotated with cloud/model/credits — never mutate the cached spec."""
    if not cloud:
        return obj
    out = {**obj, "cloud": True, "model": model}
    if credits_left is not None:
        out["credits"] = credits_left
    return out


@app.post("/api/widget")
def make_widget(req: Ask, authorization: str | None = Header(default=None)):
    t_start = time.perf_counter()
    fr = nearest_frame(req.video, req.time)
    if fr is None:
        return _no_manifest(req.video, req.time, "widget")
    source = None
    if req.current_spec is not None:
        source, source_error = _bounded_refinement_source(req.current_spec)
        if source_error:
            return {"error": source_error}
        context = _refinement_context(req, source)
    else:
        context = (
            f'Teacher is saying: "{req.text[:1200]}"\n\n'
            f'The student selected that passage and asked for an interactive widget'
            + (f': "{req.ask[:300]}"' if req.ask else ".")
            + "\nHonor the student's request if it maps to an available widget type."
            + "\nEmit the concept spec JSON."
        )
    handle = _handle()
    use, metered, model_name = backend, False, info.get("model")
    if req.cloud:
        try:
            handle = _authenticated_handle(authorization)
            use, metered, model_name = _cloud_ctx(handle)
        except CloudUnavailable as e:
            bill = _db.user_billing(handle) if (_db and handle != _handle()) else {"credits": 0, "has_own_key": False}
            return {"error": e.reason, "need_credits": True, "cloud": True, **bill}

    ev = {"handle": handle, "video_id": req.video, "t_s": req.time,
          "frame_file": fr["file"], "kind": "widget", "model": model_name}
    owner = _owner_for(authorization)

    genre = _genre_for(req.video, req.text)
    t0 = time.perf_counter()
    h = _prompt_hash(req.video, fr["file"], context, genre, model_name)
    cands = [h] if genre == "general" else [h, _prompt_hash(req.video, fr["file"], context, None, model_name)]
    cached = _cache_get_first(cands)
    ev["t_cache_lookup_ms"] = _ms(t0)

    if cached is not None and cached.get("widget") and not valid(cached):
        cached = None

    if cached is not None:
        refinement_error = _refinement_widget_type_error(source, cached)
        if refinement_error:
            ev.update(cache_hit=True, spec_valid=False, widget_kind=cached.get("widget", "answer"),
                      error=refinement_error, t_total_ms=_ms(t_start))
            _fire_event(ev)
            return {"error": refinement_error}
        ev.update(cache_hit=True, spec_valid=("widget" in cached),
                  widget_kind=cached.get("widget", "answer"),
                  t_backend_ask_ms=0, t_parse_validate_ms=0,
                  t_total_ms=_ms(t_start))
        _fire_event(ev)
        bal = _db.user_billing(handle)["credits"] if (req.cloud and metered and _db) else None
        # A hit returns before the tail below, so persisting only there would never save a
        # widget for a box someone already generated once.
        out = _persisted(cached, req.video, owner, ev, req.replaces, req.replaces_key)
        return _with_billing({**out, "cached": True}, req.cloud, model_name, bal)

    # Before spend_credit: a pull from Supabase Storage can fail, and a credit spent on a
    # request that never reaches the model is a credit lost.
    src = _frame_path(ev, req.video, fr)

    credits_left = None
    if req.cloud and metered and _db:
        credits_left = _db.spend_credit(handle, model_name, 1)
        if credits_left is None:
            return {"error": "out of credits — add your own OpenRouter key or use the local model",
                    "need_credits": True, "cloud": True, **_db.user_billing(handle)}

    t0 = time.perf_counter()
    try:
        raw = use.ask(src, context, max_px=WIDGET_MAX_PX, system=compose_system(genre))
    except FileNotFoundError:
        # frame jpgs pruned from disk (concepts stay cached) — degrade, don't 500
        if req.cloud and metered and _db and credits_left is not None:
            _db.refund_credit(handle, model_name, 1)
        ev.update(cache_hit=False, spec_valid=False, error="frames missing on disk",
                  t_backend_ask_ms=_ms(t0), t_total_ms=_ms(t_start))
        _fire_event(ev)
        return _no_keyframes("live")
    except Exception as e:
        if req.cloud and metered and _db and credits_left is not None:
            _db.refund_credit(handle, model_name, 1)
        ev.update(cache_hit=False, spec_valid=False, error=str(e)[:200],
                  t_backend_ask_ms=_ms(t0), t_total_ms=_ms(t_start))
        _fire_event(ev)
        raise
    ev["t_backend_ask_ms"] = _ms(t0)

    t0 = time.perf_counter()
    spec = extract_json(raw)
    is_valid = valid(spec)
    ev["t_parse_validate_ms"] = _ms(t0)
    ev["cache_hit"] = False

    if not is_valid:
        if source is not None:
            ev.update(spec_valid=False, widget_kind=(spec or {}).get("widget", "none"),
                      error="invalid widget refinement", t_total_ms=_ms(t_start))
            _fire_event(ev)
            return {"error": "the refinement returned an invalid widget; your current widget was unchanged"}
        # not manipulable — still be useful: return the model's explanation as an answer card
        answer = (spec or {}).get("explanation") or raw.strip()[:600]
        if answer:
            out = {"answer": answer, "time": req.time, "frame": fr["file"]}
            _cache_put(h, req.video, out)
            ev.update(spec_valid=False, widget_kind="answer", t_total_ms=_ms(t_start))
            _fire_event(ev)
            return _with_billing(out, req.cloud, model_name, credits_left)
        ev.update(spec_valid=False, widget_kind="none",
                  error="no widget found for this moment", t_total_ms=_ms(t_start))
        _fire_event(ev)
        return {"error": "no widget found for this moment", "raw": raw[:400]}
    # The grid ceiling exists to keep a freshly generated sheet small. A refinement starts from
    # a sheet the learner already has, so clamping there would silently delete their rows.
    if source is None:
        spec = _clamp_spreadsheet(spec)
    if not valid(spec):
        ev.update(spec_valid=False, widget_kind=spec.get("widget", "none"),
                  error="invalid normalized widget", t_total_ms=_ms(t_start))
        _fire_event(ev)
        return {"error": "the widget could not be validated"}
    refinement_error = _refinement_widget_type_error(source, spec)
    if refinement_error:
        ev.update(spec_valid=False, widget_kind=spec.get("widget", "none"),
                  error=refinement_error, t_total_ms=_ms(t_start))
        _fire_event(ev)
        return {"error": refinement_error}
    spec["time"] = req.time
    spec["frame"] = fr["file"]
    spec["user_made"] = True
    _cache_put(h, req.video, spec)
    ev.update(spec_valid=True, widget_kind=spec.get("widget"), t_total_ms=_ms(t_start))
    _fire_event(ev)
    out = _persisted(spec, req.video, owner, ev, req.replaces, req.replaces_key)
    return _with_billing(out, req.cloud, model_name, credits_left)


class RegionAsk(BaseModel):
    text: str = ""
    time: float
    x: float  # region in normalized [0,1] video coords
    y: float
    w: float
    h: float
    ask: str = ""
    video: str = DEFAULT_VIDEO
    cloud: bool = False


@app.post("/api/region")
def make_region_widget(req: RegionAsk, authorization: str | None = Header(default=None)):
    """Click-the-whiteboard: crop what the student pointed at, make THAT alive."""
    from PIL import Image

    t_start = time.perf_counter()
    fr = nearest_frame(req.video, req.time)
    if fr is None:
        return _no_manifest(req.video, req.time, "region")
    handle = _handle()
    use, metered, model_name = backend, False, info.get("model")
    if req.cloud:
        try:
            handle = _authenticated_handle(authorization)
            use, metered, model_name = _cloud_ctx(handle)
        except CloudUnavailable as e:
            return {"error": e.reason, "need_credits": True, "cloud": True}
    ev = {"handle": handle, "video_id": req.video, "t_s": req.time,
          "frame_file": fr["file"], "kind": "region", "model": model_name}
    owner = _owner_for(authorization)

    genre = _genre_for(req.video, req.text)
    t0 = time.perf_counter()
    h = _region_hash(req.video, fr["file"], req.x, req.y, req.w, req.h, genre, model_name)
    cands = [h] if genre == "general" else [
        h, _region_hash(req.video, fr["file"], req.x, req.y, req.w, req.h, None, model_name)]
    cached = _cache_get_first(cands)
    ev["t_cache_lookup_ms"] = _ms(t0)
    if cached is not None:
        ev.update(cache_hit=True, spec_valid=("widget" in cached),
                  widget_kind=cached.get("widget", "answer"),
                  t_backend_ask_ms=0, t_parse_validate_ms=0, t_total_ms=_ms(t_start))
        _fire_event(ev)
        balance = _db.user_billing(handle)["credits"] if (req.cloud and metered and _db) else None
        out = _persisted(cached, req.video, owner, ev)
        return _with_billing({**out, "cached": True}, req.cloud, model_name, balance)
    ev["cache_hit"] = False

    src = _frame_path(ev, req.video, fr)
    if not src.exists():
        ev.update(spec_valid=False, error="frames missing on disk", t_total_ms=_ms(t_start))
        _fire_event(ev)
        return _no_keyframes("region")
    img = Image.open(src)
    W, H = img.size
    pad = 0.12  # a little context around the selection
    x0 = max(0, (req.x - pad * req.w) * W)
    y0 = max(0, (req.y - pad * req.h) * H)
    x1 = min(W, (req.x + req.w * (1 + pad)) * W)
    y1 = min(H, (req.y + req.h * (1 + pad)) * H)
    crop = img.crop((int(x0), int(y0), int(x1), int(y1)))
    if crop.width < 480:  # upscale tiny selections so the VLM can read them
        s = 480 / crop.width
        crop = crop.resize((480, int(crop.height * s)))
    crops = DATA / req.video / "crops"
    crops.mkdir(exist_ok=True)
    path = crops / f"c_{int(req.time)}_{int(req.x * 100)}_{int(req.y * 100)}.jpg"
    crop.convert("RGB").save(path, quality=88)

    context = (
        f'Teacher is saying: "{req.text[:1000]}"\n\n'
        "The image is the EXACT region of the screen the student just circled — "
        "they want THIS drawing/figure/equation to come alive as a widget."
        + (f' They added: "{req.ask[:200]}"' if req.ask else "")
        + "\nEmit the concept spec JSON for what is in this region."
    )
    credits_left = None
    if req.cloud and metered and _db:
        credits_left = _db.spend_credit(handle, model_name, 1)
        if credits_left is None:
            return {"error": "out of credits — add your own OpenRouter key or use the local model",
                    "need_credits": True, "cloud": True, **_db.user_billing(handle)}
    t0 = time.perf_counter()
    try:
        raw = use.ask(path, context, system=compose_system(genre))
    except Exception as e:
        if req.cloud and metered and _db and credits_left is not None:
            _db.refund_credit(handle, model_name, 1)
        ev.update(spec_valid=False, error=str(e)[:200],
                  t_backend_ask_ms=_ms(t0), t_total_ms=_ms(t_start))
        _fire_event(ev)
        raise
    ev["t_backend_ask_ms"] = _ms(t0)

    t0 = time.perf_counter()
    spec = extract_json(raw)
    is_valid = valid(spec)
    ev["t_parse_validate_ms"] = _ms(t0)

    if not is_valid:
        answer = (spec or {}).get("explanation") or ""
        if answer:
            out = {"answer": answer, "time": req.time}
            _cache_put(h, req.video, out)
            ev.update(spec_valid=False, widget_kind="answer", t_total_ms=_ms(t_start))
            _fire_event(ev)
            return _with_billing(out, req.cloud, model_name, credits_left)
        ev.update(spec_valid=False, widget_kind="none",
                  error="couldn't read that region", t_total_ms=_ms(t_start))
        _fire_event(ev)
        return {"error": "couldn't read that region", "raw": raw[:300]}
    spec = _clamp_spreadsheet(spec)
    spec["time"] = req.time
    spec["frame"] = fr["file"]
    spec["user_made"] = True
    _cache_put(h, req.video, spec)
    ev.update(spec_valid=True, widget_kind=spec.get("widget"), t_total_ms=_ms(t_start))
    _fire_event(ev)
    out = _persisted(spec, req.video, owner, ev)
    return _with_billing(out, req.cloud, model_name, credits_left)


@app.get("/api/saved-widgets")
def saved_widgets(video: str = DEFAULT_VIDEO):
    """Everything generated for this video, for the timeline to merge with concepts.json.
    Public, so it carries only what the widget kit renders — never who saved it."""
    try:
        return [{k: v for k, v in row.items() if k != "owner"}
                for row in widget_store.load(video)]
    except widget_store.BadVideoId as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except widget_store.StoreUnavailable as e:
        return JSONResponse(status_code=503, content={"error": str(e)})


class FlagUpdate(BaseModel):
    guest_saves: bool | None = None


@app.get("/api/flags")
def get_flags():
    return flags.load()


@app.post("/api/flags")
def set_flags(req: FlagUpdate, authorization: str | None = Header(default=None)):
    """Team members only — a guest flipping the guest-saves flag would defeat the point."""
    if not _team_member(authorization):
        return JSONResponse(status_code=403,
                            content={"error": "only the team can change this"})
    changes = req.model_dump(exclude_none=True)
    if not changes:
        return flags.load()
    try:
        return flags.update(changes)
    except OSError as e:
        return JSONResponse(status_code=503, content={"error": f"could not save flags: {e}"})


@app.get("/api/info")
def get_info():
    return info


# ---------- live ingest: drop a YouTube URL → ingest + analyze → widgets ----------
ROOT = Path(__file__).resolve().parent
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _extract_id(v: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", v)
    return m.group(1) if m else v.strip()


def _set_job(vid: str, **kw):
    with _jobs_lock:
        _jobs.setdefault(vid, {}).update(**kw)


def _needs_download(vd: Path) -> bool:
    """A committed frames.json with no jpgs beside it still needs the video — analyze.py would
    error on every frame and SystemExit into the job as a bare failure."""
    return not (vd / "frames.json").exists() or not any((vd / "frames").glob("*.jpg"))


def _run_ingest(vid: str, url: str, limit: int, backend: str):
    py = sys.executable
    # cloud (OpenRouter) batches frames concurrently → a live drop finishes in ~30-60s,
    # vs. a sequential local reasoning model taking minutes. Fan out when on cloud.
    env = {**os.environ}
    if backend == "openrouter":
        env["KEDU_CONCURRENCY"] = env.get("KEDU_CONCURRENCY", "6")
    try:
        vd = ROOT / "data" / vid
        if _needs_download(vd):
            _set_job(vid, step="downloading video + transcript + keyframes")
            subprocess.run([py, "ingest.py", url], cwd=ROOT, check=True, timeout=900, env=env)
        # Download stays host-side (YouTube CDN can't be allowlisted); the reasoning over
        # untrusted frames is the part worth containing. KEDU_CONTAINED=1 runs analyze.py
        # inside the Docker egress-allowlist sandbox (deploy/containment/) — cloud analog of
        # the OpenShell/scoutclaw demo. Off by default → the plain host path.
        contained = os.environ.get("KEDU_CONTAINED") == "1"
        _set_job(vid, step="analyzing frames → widgets" + (" (contained)" if contained else ""),
                 contained=contained)
        if contained:
            subprocess.run(["bash", "deploy/containment/analyze-contained.sh", vid, str(limit)],
                           cwd=ROOT, check=True, timeout=2400, env=env)
        else:
            subprocess.run([py, "analyze.py", "--backend", backend, f"--video={vid}", "--limit", str(limit)],
                           cwd=ROOT, check=True, timeout=2400, env=env)
        n = len(json.loads((vd / "concepts.json").read_text())) if (vd / "concepts.json").exists() else 0
        _set_job(vid, state="done", step="done", widgets=n)
    except subprocess.TimeoutExpired:
        _set_job(vid, state="error", error="timed out")
    except Exception as e:
        _set_job(vid, state="error", error=str(e)[:200])


class IngestReq(BaseModel):
    video: str          # 11-char id or a full YouTube URL
    limit: int = 12


@app.post("/api/ingest")
def ingest(req: IngestReq):
    """Kick off ingest + analyze for a video in the background; poll /api/ingest/status."""
    vid = _extract_id(req.video)
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        return {"state": "error", "error": "not a YouTube URL or 11-char id"}
    url = req.video if req.video.startswith("http") else f"https://www.youtube.com/watch?v={vid}"
    with _jobs_lock:
        if _jobs.get(vid, {}).get("state") == "running":
            return {"video": vid, **_jobs[vid]}
        _jobs[vid] = {"state": "running", "step": "starting", "widgets": 0}
    # prefer cloud for live ingest (fast, concurrent); fall back to whatever's configured locally
    backend = (os.environ.get("KEDU_INGEST_BACKEND")
               or ("openrouter" if os.environ.get("OPENROUTER_API_KEY") else (os.environ.get("KEDU_BACKEND") or "vllm")))
    threading.Thread(target=_run_ingest, args=(vid, url, req.limit, backend), daemon=True).start()
    return {"video": vid, "state": "running", "step": "starting"}


@app.get("/api/ingest/status")
def ingest_status(video: str):
    vid = _extract_id(video)
    with _jobs_lock:
        return {"video": vid, **(_jobs.get(vid) or {"state": "idle"})}


class KeyReq(BaseModel):
    key: str = ""


@app.get("/api/billing")
def billing(authorization: str | None = Header(default=None)):
    """Credit balance + whether cloud is available for this learner."""
    if not _db:
        return {"credits": 0, "has_own_key": False, "cloud_available": False}
    try:
        h = _authenticated_handle(authorization)
    except CloudUnavailable as error:
        return {"credits": 0, "has_own_key": False, "cloud_available": False,
                "authenticated": False, "error": error.reason}
    b = _db.user_billing(h)
    with _byok_lock:
        b["has_own_key"] = bool(_byok_keys.get(h))
    b["cloud_available"] = b["has_own_key"] or bool(os.environ.get("OPENROUTER_API_KEY"))
    b["authenticated"] = True
    b["model"] = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    return b


@app.post("/api/openrouter-key")
def set_openrouter_key(req: KeyReq, authorization: str | None = Header(default=None)):
    """Hold/clear a BYOK key in process memory. It is never persisted or returned."""
    if not _db:
        return {"ok": False, "error": "billing offline"}
    try:
        h = _authenticated_handle(authorization)
    except CloudUnavailable as error:
        return {"ok": False, "error": error.reason}
    key = req.key.strip()
    if key and not key.startswith("sk-or-"):
        return {"ok": False, "error": "OpenRouter keys start with sk-or-"}
    with _byok_lock:
        if key:
            _byok_keys[h] = key
        else:
            _byok_keys.pop(h, None)
    result = _db.user_billing(h)
    result["has_own_key"] = bool(key)
    return {"ok": True, **result}


def main() -> None:
    global backend
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=BACKEND_CHOICES, default="mlx")
    ap.add_argument("--port", type=int, default=8756)
    args = ap.parse_args()
    print(f"loading {args.backend} backend…")
    backend = make_backend(args.backend)
    info.update(
        backend=args.backend,
        model=getattr(backend, "model_name", "?"),
        mode="local" if args.backend in ("mlx", "lmstudio", "vllm") else "byok",
        cloud=args.backend not in ("mlx", "lmstudio", "vllm"),
    )
    print(f"ready: {info}")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
