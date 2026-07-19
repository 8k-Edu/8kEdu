"""Ask endpoint: selected transcript + user intent → widget spec.

Usage: uv run serve.py [--backend mlx|openai] [--port 8756]
POST /api/widget {"text": "...", "time": 1234.5, "ask": "let me play with the matrix"}
→ concept spec JSON (same shape the offline pipeline emits)
"""

import argparse
import hashlib
import json
import os
import time
from collections import OrderedDict
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analyze import BACKEND_CHOICES, compose_system, detect_genre, extract_json, make_backend, openrouter_backend, valid

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA = Path("data")
DEFAULT_VIDEO = "42L1q1Z4Ojc"  # has keyframes on disk → live-ask never 404s on the fallback
PROMPT_VERSION = "v1"  # bump when SYSTEM/prompt changes → new cache keys, no stale serves
WIDGET_MAX_PX = int(os.environ.get("KEDU_MAX_PX", "768"))
_frames_cache: dict[str, list] = {}
backend = None  # set in main()
info = {"backend": "?", "model": "?", "mode": "?"}

# R4 — frame-level cache. Identical (video, frame, genre, ask) across users → no VLM call.
try:
    from agent import db as _db
    _db.load_env()  # AGENT_HANDLE must be set before the first request logs an event
except Exception:
    _db = None


def _handle() -> str:
    return os.environ.get("AGENT_HANDLE", "demo")


def _fire_event(payload: dict) -> None:
    if not _db:
        return
    _db.enqueue_widget_event(payload)


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
                 genre: str | None = None) -> str:
    box = f"{x:.2f},{y:.2f},{w:.2f},{h:.2f}"  # what's in the box drives the result, not the words
    g = f"|g={genre}" if genre and genre != "general" else ""
    key = f"{PROMPT_VERSION}|region|{info.get('model','?')}|{video}|{frame}|{box}{g}"
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
    handle: str = ""        # learner identity (for credits); falls back to AGENT_HANDLE
    cloud: bool = False     # use a cloud model (OpenRouter) instead of the free local one
    model: str = ""         # optional cloud model override (else OPENROUTER_MODEL)


def frames_for(video: str) -> list[dict]:
    if video not in _frames_cache:
        _frames_cache[video] = json.loads((DATA / video / "frames.json").read_text())
    return _frames_cache[video]


def nearest_frame(video: str, t: float) -> dict:
    return min(frames_for(video), key=lambda f: abs(f["time"] - t))


SS_MAX_ROWS, SS_MAX_COLS = 5, 4


def _clamp_spreadsheet(spec: dict) -> dict:
    """Small local models ignore the prompt's 'at most 4x5' hint, so enforce it here:
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


class CloudUnavailable(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _cloud_ctx(handle: str, model: str):
    """Resolve a cloud (OpenRouter) backend for this learner.
    Returns (backend, metered, model_name). BYOK key → unmetered; else platform key + credits.
    Raises CloudUnavailable when the learner can't pay (no key, no credits, billing offline)."""
    if not _db:
        raise CloudUnavailable("billing offline")
    mdl = model or os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    try:
        key = _db.own_key(handle)
    except Exception:
        key = None
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
def make_widget(req: Ask):
    t_start = time.perf_counter()
    fr = nearest_frame(req.video, req.time)
    context = (
        f'Teacher is saying: "{req.text[:1200]}"\n\n'
        f'The student selected that passage and asked for an interactive widget'
        + (f': "{req.ask[:300]}"' if req.ask else ".")
        + "\nHonor the student's request if it maps to an available widget type."
        + "\nEmit the concept spec JSON."
    )
    handle = req.handle or _handle()
    use, metered, model_name = backend, False, info.get("model")
    if req.cloud:
        try:
            use, metered, model_name = _cloud_ctx(handle, req.model)
        except CloudUnavailable as e:
            bill = _db.user_billing(handle) if _db else {"credits": 0, "has_own_key": False}
            return {"error": e.reason, "need_credits": True, "cloud": True, **bill}

    ev = {"handle": handle, "video_id": req.video, "t_s": req.time,
          "frame_file": fr["file"], "kind": "widget", "model": model_name}

    genre = _genre_for(req.video, req.text)
    t0 = time.perf_counter()
    h = _prompt_hash(req.video, fr["file"], context, genre, model_name)
    cands = [h] if genre == "general" else [h, _prompt_hash(req.video, fr["file"], context, None, model_name)]
    cached = _cache_get_first(cands)
    ev["t_cache_lookup_ms"] = _ms(t0)

    if cached is not None:
        ev.update(cache_hit=True, spec_valid=("widget" in cached),
                  widget_kind=cached.get("widget", "answer"),
                  t_backend_ask_ms=0, t_parse_validate_ms=0,
                  t_total_ms=_ms(t_start))
        _fire_event(ev)
        # cache hit = no cloud call = no charge; still surface the learner's balance
        bal = _db.user_billing(handle)["credits"] if (req.cloud and metered and _db) else None
        return _with_billing({**cached, "cached": True}, req.cloud, model_name, bal)

    t0 = time.perf_counter()
    try:
        raw = use.ask(DATA / req.video / "frames" / fr["file"], context,
                      max_px=WIDGET_MAX_PX, system=compose_system(genre))
    except Exception as e:
        ev.update(cache_hit=False, spec_valid=False, error=str(e)[:200],
                  t_backend_ask_ms=_ms(t0), t_total_ms=_ms(t_start))
        _fire_event(ev)
        raise
    ev["t_backend_ask_ms"] = _ms(t0)
    # a real cloud call happened → debit one credit (BYOK is unmetered)
    credits_left = _db.spend_credit(handle, model_name, 1) if (req.cloud and metered and _db) else None

    t0 = time.perf_counter()
    spec = extract_json(raw)
    is_valid = valid(spec)
    ev["t_parse_validate_ms"] = _ms(t0)
    ev["cache_hit"] = False

    if not is_valid:
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
    spec = _clamp_spreadsheet(spec)
    spec["time"] = req.time
    spec["frame"] = fr["file"]
    spec["user_made"] = True
    _cache_put(h, req.video, spec)
    ev.update(spec_valid=True, widget_kind=spec.get("widget"), t_total_ms=_ms(t_start))
    _fire_event(ev)
    return _with_billing(spec, req.cloud, model_name, credits_left)


class RegionAsk(BaseModel):
    text: str = ""
    time: float
    x: float  # region in normalized [0,1] video coords
    y: float
    w: float
    h: float
    ask: str = ""
    video: str = DEFAULT_VIDEO


@app.post("/api/region")
def make_region_widget(req: RegionAsk):
    """Click-the-whiteboard: crop what the student pointed at, make THAT alive."""
    from PIL import Image

    t_start = time.perf_counter()
    fr = nearest_frame(req.video, req.time)
    ev = {"handle": _handle(), "video_id": req.video, "t_s": req.time,
          "frame_file": fr["file"], "kind": "region", "model": info.get("model")}

    genre = _genre_for(req.video, req.text)
    t0 = time.perf_counter()
    h = _region_hash(req.video, fr["file"], req.x, req.y, req.w, req.h, genre)
    cands = [h] if genre == "general" else [
        h, _region_hash(req.video, fr["file"], req.x, req.y, req.w, req.h)]
    cached = _cache_get_first(cands)
    ev["t_cache_lookup_ms"] = _ms(t0)
    if cached is not None:
        cached["cached"] = True
        ev.update(cache_hit=True, spec_valid=("widget" in cached),
                  widget_kind=cached.get("widget", "answer"),
                  t_backend_ask_ms=0, t_parse_validate_ms=0, t_total_ms=_ms(t_start))
        _fire_event(ev)
        return cached
    ev["cache_hit"] = False

    src = DATA / req.video / "frames" / fr["file"]
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
    t0 = time.perf_counter()
    try:
        raw = backend.ask(path, context, system=compose_system(genre))
    except Exception as e:
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
            return out
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
    return spec


@app.get("/api/info")
def get_info():
    return info


class KeyReq(BaseModel):
    handle: str = ""
    key: str = ""


@app.get("/api/billing")
def billing(handle: str = ""):
    """Credit balance + whether cloud is available for this learner."""
    if not _db:
        return {"credits": 0, "has_own_key": False, "cloud_available": False}
    b = _db.user_billing(handle or _handle())
    b["cloud_available"] = b["has_own_key"] or bool(os.environ.get("OPENROUTER_API_KEY"))
    b["model"] = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    return b


@app.post("/api/openrouter-key")
def set_openrouter_key(req: KeyReq):
    """Store/clear a learner's own OpenRouter key (BYOK → unmetered cloud). Key never leaves the server."""
    if not _db:
        return {"ok": False, "error": "billing offline"}
    h = req.handle or _handle()
    _db.set_openrouter_key(h, req.key.strip())
    return {"ok": True, **_db.user_billing(h)}


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
