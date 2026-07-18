"""Ask endpoint: selected transcript + user intent → widget spec.

Usage: uv run serve.py [--backend mlx|openai] [--port 8756]
POST /api/widget {"text": "...", "time": 1234.5, "ask": "let me play with the matrix"}
→ concept spec JSON (same shape the offline pipeline emits)
"""

import argparse
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analyze import BACKEND_CHOICES, extract_json, make_backend, valid

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA = Path("data")
DEFAULT_VIDEO = "kCc8FmEb1nY"
_frames_cache: dict[str, list] = {}
backend = None  # set in main()
info = {"backend": "?", "model": "?", "mode": "?"}


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
    fr = nearest_frame(req.video, req.time)
    context = (
        f'Teacher is saying: "{req.text[:1200]}"\n\n'
        f'The student selected that passage and asked for an interactive widget'
        + (f': "{req.ask[:300]}"' if req.ask else ".")
        + "\nHonor the student's request if it maps to an available widget type."
        + "\nEmit the concept spec JSON."
    )
    raw = backend.ask(DATA / req.video / "frames" / fr["file"], context)
    spec = extract_json(raw)
    if not valid(spec):
        # not manipulable — still be useful: return the model's explanation as an answer card
        answer = (spec or {}).get("explanation") or raw.strip()[:600]
        if answer:
            return {"answer": answer, "time": req.time, "frame": fr["file"]}
        return {"error": "no widget found for this moment", "raw": raw[:400]}
    spec["time"] = req.time
    spec["frame"] = fr["file"]
    spec["user_made"] = True
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

    context = (
        f'Teacher is saying: "{req.text[:1000]}"\n\n'
        "The image is the EXACT region of the screen the student just circled — "
        "they want THIS drawing/figure/equation to come alive as a widget."
        + (f' They added: "{req.ask[:200]}"' if req.ask else "")
        + "\nEmit the concept spec JSON for what is in this region."
    )
    raw = backend.ask(path, context)
    spec = extract_json(raw)
    if not valid(spec):
        answer = (spec or {}).get("explanation") or ""
        if answer:
            return {"answer": answer, "time": req.time}
        return {"error": "couldn't read that region", "raw": raw[:300]}
    spec["time"] = req.time
    spec["frame"] = fr["file"]
    spec["user_made"] = True
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
