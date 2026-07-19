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

from analyze import BACKEND_CHOICES, extract_json, make_backend, valid

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA = Path("data")
DEFAULT_VIDEO = "42L1q1Z4Ojc"  # has keyframes on disk → live-ask never 404s on the fallback
PROMPT_VERSION = "v1"  # bump when SYSTEM/prompt changes → new cache keys, no stale serves
WIDGET_MAX_PX = int(os.environ.get("TACTILE_MAX_PX", "768"))
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


def _prompt_hash(video: str, frame: str, context: str) -> str:
    key = f"{PROMPT_VERSION}|{info.get('model','?')}|{video}|{frame}|{context}"
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


class Ask(BaseModel):
    text: str
    time: float
    ask: str = ""
    video: str = DEFAULT_VIDEO


def frames_for(video: str) -> list[dict]:
    if video not in _frames_cache:
        _frames_cache[video] = json.loads((DATA / video / "frames.json").read_text())
    return _frames_cache[video]


def nearest_frame(video: str, t: float) -> dict:
    return min(frames_for(video), key=lambda f: abs(f["time"] - t))


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
    ev = {"handle": _handle(), "video_id": req.video, "t_s": req.time,
          "frame_file": fr["file"], "kind": "widget", "model": info.get("model")}

    t0 = time.perf_counter()
    h = _prompt_hash(req.video, fr["file"], context)
    cached = _cache_get(h)
    ev["t_cache_lookup_ms"] = _ms(t0)

    if cached is not None:
        cached["cached"] = True
        ev.update(cache_hit=True, spec_valid=("widget" in cached),
                  widget_kind=cached.get("widget", "answer"),
                  t_backend_ask_ms=0, t_parse_validate_ms=0,
                  t_total_ms=_ms(t_start))
        _fire_event(ev)
        return cached

    t0 = time.perf_counter()
    try:
        raw = backend.ask(DATA / req.video / "frames" / fr["file"], context, max_px=WIDGET_MAX_PX)
    except Exception as e:
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
        # not manipulable — still be useful: return the model's explanation as an answer card
        answer = (spec or {}).get("explanation") or raw.strip()[:600]
        if answer:
            out = {"answer": answer, "time": req.time, "frame": fr["file"]}
            _cache_put(h, req.video, out)
            ev.update(spec_valid=False, widget_kind="answer", t_total_ms=_ms(t_start))
            _fire_event(ev)
            return out
        ev.update(spec_valid=False, widget_kind="none",
                  error="no widget found for this moment", t_total_ms=_ms(t_start))
        _fire_event(ev)
        return {"error": "no widget found for this moment", "raw": raw[:400]}
    spec["time"] = req.time
    spec["frame"] = fr["file"]
    spec["user_made"] = True
    _cache_put(h, req.video, spec)
    ev.update(spec_valid=True, widget_kind=spec.get("widget"), t_total_ms=_ms(t_start))
    _fire_event(ev)
    return spec


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

    ev = {"handle": _handle(), "video_id": req.video, "t_s": req.time,
          "frame_file": fr["file"], "kind": "region", "model": info.get("model"),
          "cache_hit": False, "t_cache_lookup_ms": 0}

    context = (
        f'Teacher is saying: "{req.text[:1000]}"\n\n'
        "The image is the EXACT region of the screen the student just circled — "
        "they want THIS drawing/figure/equation to come alive as a widget."
        + (f' They added: "{req.ask[:200]}"' if req.ask else "")
        + "\nEmit the concept spec JSON for what is in this region."
    )
    t0 = time.perf_counter()
    try:
        raw = backend.ask(path, context)
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
            ev.update(spec_valid=False, widget_kind="answer", t_total_ms=_ms(t_start))
            _fire_event(ev)
            return {"answer": answer, "time": req.time}
        ev.update(spec_valid=False, widget_kind="none",
                  error="couldn't read that region", t_total_ms=_ms(t_start))
        _fire_event(ev)
        return {"error": "couldn't read that region", "raw": raw[:300]}
    spec["time"] = req.time
    spec["frame"] = fr["file"]
    spec["user_made"] = True
    ev.update(spec_valid=True, widget_kind=spec.get("widget"), t_total_ms=_ms(t_start))
    _fire_event(ev)
    return spec


@app.get("/api/info")
def get_info():
    return info


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
        mode="local" if args.backend in ("mlx", "lmstudio") else "byok",
        cloud=args.backend not in ("mlx", "lmstudio"),
    )
    print(f"ready: {info}")
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
