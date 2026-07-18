"""Analyze keyframes + transcript → interactive concept specs.

Usage:
  uv run analyze.py --backend mlx [--limit N]          # local, in-process (M4 Max)
  uv run analyze.py --backend openai [--limit N]       # vLLM pod / any OpenAI-compat server

Env (openai backend):
  TACTILE_BASE_URL  endpoint, e.g. http://<pod>:8000/v1
  TACTILE_MODEL     served model name
Outputs: <data>/concepts.json
"""

import argparse
import base64
import json
import os
import re
from pathlib import Path

MLX_MODEL = os.environ.get("TACTILE_MLX_MODEL", "mlx-community/Qwen2.5-VL-7B-Instruct-4bit")

CONCEPT_SCHEMA = {
    "type": "object",
    "properties": {
        "has_concept": {"type": "boolean"},
        "widget": {
            "type": "string",
            "enum": ["matrix_mul", "attention", "softmax", "function_plot", "notebook", "none"],
        },
        "title": {"type": "string"},
        "explanation": {"type": "string"},
        "params": {
            "type": "object",
            "properties": {
                "a": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "b": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "q": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "k": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "logits": {"type": "array", "items": {"type": "number"}},
                "temperature": {"type": "number"},
                "expr": {"type": "string"},
                "cells": {"type": "array", "items": {"type": "string"}},
                "sliders": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "min": {"type": "number"},
                            "max": {"type": "number"},
                            "value": {"type": "number"},
                        },
                        "required": ["name", "min", "max", "value"],
                    },
                },
            },
        },
    },
    "required": ["has_concept", "widget", "title", "explanation", "params"],
}

SYSTEM = """You turn lecture stills into interactive widget specs. You see one frame from a
technical lecture plus what the teacher said around that moment.

If the frame teaches a concept a student could MANIPULATE, emit a spec:
- matrix_mul: a matrix multiplication is shown/discussed → params {a, b} (2D number arrays)
- attention: queries/keys/attention weights → params {q, k} (2D arrays, same col count)
- softmax: logits→probabilities / sampling / temperature → params {logits} (numbers)
- function_plot: a plottable function/curve → params {expr (JS, in x + slider names), sliders}
- notebook: CODE is visible in the frame, or the concept needs real computation/simulation
  → params {cells: [python source strings], sliders}. Python runs in-browser with numpy and
  matplotlib (plt.show() to display). Translate the frame's code faithfully (torch → numpy).
  Slider names are injected as global variables (floats — wrap int(x) as needed).
  params.cells is REQUIRED for notebook — 1-3 python strings that actually compute and
  print/plot the result. A notebook spec without cells is INVALID and will be discarded.

Prefer notebook when the teacher is showing runnable code; prefer the simpler widgets when
the concept is a single manipulable object.

For ADVICE/FINANCE/TUTORIAL videos (real estate, investing, business): the manipulable
concept is the CALCULATION behind the claim. Emit a notebook calculator — sliders for the
numbers the viewer would change (price, down payment %, interest rate, rent, years, fees),
cells that compute the outcome (monthly payment, cash flow, compound growth) and plot it.
Ground every default in the numbers the speaker actually uses.
Use the ACTUAL numbers visible in the frame when readable; otherwise small didactic values
faithful to the moment (2x3 matrices, 4 logits). Matrices <= 4x4.
If the frame is just the speaker, prose slides, or code with no manipulable math:
has_concept=false, widget="none".
If the student asked a QUESTION that doesn't map to a manipulable widget, still set
widget="none" but put a direct, concrete answer to their question (grounded in the frame
and what the teacher said) in the "explanation" field.

Reply with ONLY a JSON object:
{"has_concept": bool, "widget": "matrix_mul|attention|softmax|function_plot|none",
 "title": str, "explanation": str (one sentence, why it matters), "params": {...}}"""

ALLOWED = {"matrix_mul", "attention", "softmax", "function_plot", "notebook"}

# S_g — genre-conditioned system prompts. The artifact equation:
#   A_i = M(S_g, m_i ⊕ {f_i..f_n} ⊕ Tr_i), cached on (video, i, g) and reused for every learner.
# Genre picks the lens the model reads the frame through (taxonomy grows toward 20-100 genres).
GENRE_PROMPTS = {
    "ai_stem": (
        "This is an AI/STEM lecture. Favor matrix_mul/attention/softmax for the linear-algebra "
        "moments, function_plot for curves, notebook whenever code is on screen. Reproduce the "
        "speaker's tensors and shapes exactly; translate torch to numpy faithfully."
    ),
    "finance": (
        "This is a finance/markets video. The manipulable concept is the CALCULATION behind each "
        "claim — emit notebook calculators with sliders for the numbers a viewer would change "
        "(principal, rate, years, fees, allocation) and cells that compute and plot the outcome "
        "(compound growth, cash flow, drawdown). Ground defaults in the speaker's actual numbers."
    ),
    "real_estate": (
        "This is a real-estate video. Every claim hides a calculator: mortgage payment, PMI, "
        "down-payment %, rent-vs-buy, appreciation vs opportunity cost, sell-vs-hold. Emit "
        "notebook calculators with sliders for those inputs, defaults from the speaker's numbers."
    ),
}
GENRE_KEYWORDS = {
    "ai_stem": ["matrix", "neural", "gradient", "attention", "token", "tensor", "model", "training"],
    "finance": ["invest", "stock", "market", "portfolio", "dollar", "inflation", "interest rate", "economy"],
    "real_estate": ["house", "mortgage", "down payment", "rent", "property", "real estate", "closing"],
}


def detect_genre(cues: list[dict]) -> str:
    """Cheap g = G(Tr) — keyword vote over the first ~10 minutes of transcript."""
    text = " ".join(c["text"] for c in cues[:600]).lower()
    scores = {g: sum(text.count(k) for k in kws) for g, kws in GENRE_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else "general"


def apply_genre(genre: str) -> str:
    """Compose SYSTEM = base ⊕ S_g. 'general' keeps the base prompt as-is."""
    global SYSTEM
    block = GENRE_PROMPTS.get(genre)
    if block:
        SYSTEM = SYSTEM.replace(
            "Reply with ONLY a JSON object:",
            f"GENRE LENS ({genre}): {block}\n\nReply with ONLY a JSON object:")
    return genre


def transcript_window(cues: list[dict], t: float, radius: float = 30.0) -> str:
    return " ".join(c["text"] for c in cues if t - radius <= c["start"] <= t + radius)[:1500]


def extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def valid(spec: dict | None) -> bool:
    if not spec or not spec.get("has_concept"):
        return False
    if spec.get("widget") not in ALLOWED:
        return False
    p = spec.get("params")
    if not (isinstance(p, dict) and len(p) > 0):
        return False
    def mat(x):
        return (isinstance(x, list) and x and all(
            isinstance(r, list) and r and all(isinstance(v, (int, float)) for v in r) for r in x))

    w = spec["widget"]
    if w == "notebook":
        cells = p.get("cells")
        return isinstance(cells, list) and len(cells) > 0 and all(isinstance(c, str) and c.strip() for c in cells)
    if w == "matrix_mul":
        return mat(p.get("a")) and mat(p.get("b")) and len(p["a"][0]) == len(p["b"])
    if w == "attention":
        return mat(p.get("q")) and mat(p.get("k")) and len(p["q"][0]) == len(p["k"][0])
    if w == "softmax":
        lg = p.get("logits")
        return isinstance(lg, list) and len(lg) >= 2 and all(isinstance(v, (int, float)) for v in lg)
    if w == "function_plot":
        return isinstance(p.get("expr"), str) and bool(p["expr"].strip())
    return True


# ---------- backends ----------

class MlxBackend:
    def __init__(self):
        from mlx_vlm import load, generate  # lazy: heavy import
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config
        self._generate = generate
        self._apply = apply_chat_template
        self.model, self.processor = load(MLX_MODEL)
        self.config = load_config(MLX_MODEL)
        self.model_name = MLX_MODEL

    def ask(self, frame: Path, context: str) -> str:
        prompt = self._apply(
            self.processor, self.config,
            f'{SYSTEM}\n\nTeacher is saying: "{context}"\n\nEmit the concept spec JSON.',
            num_images=1,
        )
        out = self._generate(
            self.model, self.processor, prompt, image=[str(frame)],
            max_tokens=800, temperature=0.1, verbose=False,
        )
        return out.text if hasattr(out, "text") else str(out)


class OpenAIBackend:
    """Any OpenAI-compatible endpoint: vLLM pod, LM Studio, Gemini, OpenRouter…"""

    def __init__(self, base_url: str, api_key: str, model: str):
        from openai import OpenAI
        self.model = model
        self.model_name = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def ask(self, frame: Path, context: str) -> str:
        img = base64.standard_b64encode(frame.read_bytes()).decode()
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}},
                {"type": "text", "text": f'Teacher is saying: "{context}"\n\nEmit the concept spec JSON.'},
            ]},
        ]
        # strictest → loosest: schema (vLLM guided decoding) → json mode → plain.
        # Reasoning models (e.g. Nemotron Omni on LM Studio) can return the answer only in
        # reasoning_content and leave `content` EMPTY under structured-output — so treat an
        # empty content as a miss and fall through to the next (looser) format.
        last = None
        for fmt in (
            {"type": "json_schema", "json_schema": {"name": "concept", "schema": CONCEPT_SCHEMA}},
            {"type": "json_object"},
            None,
        ):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=0.1,
                    max_tokens=6000,  # thinking models spend reasoning tokens from this budget
                    **({"response_format": fmt} if fmt else {}),
                )
                content = (resp.choices[0].message.content or "").strip()
                if content:
                    return content
            except Exception as e:
                last = e
        if last:
            raise last
        return ""


def load_dotenv() -> None:
    """Tiny .env loader — no dependency, values never printed."""
    env = Path(__file__).parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


CLOUD_BACKENDS = {"gemini", "openai"}


def make_backend(name: str):
    """local: mlx (in-process) · lmstudio (local server) — BYOK: gemini · openai (generic/vLLM)."""
    load_dotenv()
    # cost guard: cloud vision (Gemini/OpenAI) is OFF unless explicitly allowed.
    # a runaway batch over hundreds of frames is how a bill explodes.
    if name in CLOUD_BACKENDS and os.environ.get("TACTILE_ALLOW_CLOUD") != "1":
        raise SystemExit(
            f"cloud backend '{name}' is BLOCKED (cost guard).\n"
            f"Local backends (mlx / lmstudio) are free and unrestricted.\n"
            f"To deliberately spend on cloud vision, set TACTILE_ALLOW_CLOUD=1 for this one run."
        )
    if name == "mlx":
        return MlxBackend()
    if name == "lmstudio":
        return OpenAIBackend(
            base_url=os.environ.get("TACTILE_BASE_URL", "http://127.0.0.1:1234/v1"),
            api_key="lm-studio",
            model=os.environ.get("TACTILE_MODEL", "qwen2.5-vl-7b-instruct"),
        )
    if name == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise SystemExit("gemini backend needs GEMINI_API_KEY (or GOOGLE_API_KEY)")
        return OpenAIBackend(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=key,
            model=os.environ.get("TACTILE_MODEL", "gemini-3-pro-preview"),
        )
    # generic BYOK / vLLM pod
    return OpenAIBackend(
        base_url=os.environ.get("TACTILE_BASE_URL", "http://localhost:8000/v1"),
        api_key=os.environ.get("TACTILE_API_KEY", "none"),
        model=os.environ.get("TACTILE_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
    )


BACKEND_CHOICES = ["mlx", "lmstudio", "gemini", "openai"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=BACKEND_CHOICES, default="mlx")
    ap.add_argument("--data", default="data")
    ap.add_argument("--video", default="", help="video id → data/<id>")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start", type=int, default=0, help="skip first N frames")
    ap.add_argument("--out-name", default="concepts.json",
                    help="output filename (use e.g. concepts.mlx.json for eval runs)")
    ap.add_argument("--genre", default="auto",
                    help=f"system-prompt lens: auto|general|{'|'.join(GENRE_PROMPTS)}")
    args = ap.parse_args()
    data = Path(args.data) / args.video if args.video else Path(args.data)

    cues = json.loads((data / "transcript.json").read_text())
    frames = json.loads((data / "frames.json").read_text())
    frames = frames[args.start:]
    if args.limit:
        frames = frames[: args.limit]

    genre = apply_genre(detect_genre(cues) if args.genre == "auto" else args.genre)
    print(f"genre lens: {genre}")
    backend = make_backend(args.backend)

    concepts = []
    for i, fr in enumerate(frames):
        ctx = transcript_window(cues, fr["time"])
        try:
            raw = backend.ask(data / "frames" / fr["file"], ctx)
        except Exception as e:  # keep sweeping; one bad frame must not kill the run
            print(f"[{i+1}/{len(frames)}] {fr['time']:>7.1f}s  ! {e}")
            continue
        spec = extract_json(raw)
        if valid(spec):
            spec["time"] = fr["time"]
            spec["frame"] = fr["file"]
            concepts.append(spec)
            print(f"[{i+1}/{len(frames)}] {fr['time']:>7.1f}s  ✓ {spec['widget']}: {spec.get('title', '')[:60]}")
        else:
            print(f"[{i+1}/{len(frames)}] {fr['time']:>7.1f}s  – no concept")

    merged = []
    for c in concepts:
        if merged and merged[-1]["widget"] == c["widget"] and c["time"] - merged[-1]["time"] < 90:
            continue
        merged.append(c)

    (data / args.out_name).write_text(json.dumps(merged, indent=1))
    print(f"done: {len(merged)} concepts (of {len(concepts)} raw) → {data}/{args.out_name}")


if __name__ == "__main__":
    main()
