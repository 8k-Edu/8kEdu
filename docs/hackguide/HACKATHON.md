# EduClaw — Hackathon Rebuild Playbook

**Event:** Austin vLLM & llm-d Inference Meetup / hackathon — Thu Jul 16 2026, 5–9 PM, 800 Brazos St #340.
**Rule:** no already-built projects — must build fresh on-site. This doc = the plan you rebuild *from* (allowed: you know the design; you retype the code). Pre-build lives on your machine + github.com/brishtiteveja/tactile; on-site you `git init` a new repo and reconstruct.

**One-liner:** paste a YouTube lecture → AI turns every teachable moment into a LIVE, tweakable widget beside the video. "Brilliant.org, auto-generated from any lecture — on any topic."

---

## The pitch (90-second demo arc)
1. Landing → categories (AI / real-estate / fintech) → "any topic, not just code."
2. Open Karpathy → play → at the tril moment a widget appears; drag temperature → attention heatmap re-sharpens live.
3. **🐍 notebook widget**: his actual code running as real numpy in the browser (pyodide); drag `T` → matrix reprints, matplotlib redraws.
4. **🎯 touch the screen**: drag a box around any drawing → that exact region comes alive (crop → VLM → widget).
5. Open real-estate video → a mortgage calculator built from *his own numbers*. "Same engine, any subject."
6. **share remix** → QR on screen → room opens YOUR widget state on their phones. Room becomes the demo.
7. Close: "every lecture ever uploaded → a lab you can touch. Local model, one GPU, pennies."

vLLM-crowd hook (say it): pipeline runs on **open models, self-hosted** — local MLX today, vLLM + GuideLLM benchmark for the cost slide. Zero API dependency.

---

## Architecture (spec = data; no live codegen)
```
ingest.py   yt-dlp video+subs+chapters → ffmpeg uniform keyframes (~1/interval, cap 120)
            → data/<videoId>/{video.mp4, transcript.json, frames/, chapters.json}
analyze.py  each keyframe + transcript window → VLM → concept-spec JSON (schema-enforced)
            backends: mlx (local, free) | lmstudio | gemini | openai  (cloud BLOCKED by default)
serve.py    FastAPI :8756 — live endpoints the app calls
              POST /api/widget  (transcript select → widget)
              POST /api/region  (click-the-whiteboard: PIL-crop the dragged box → widget)
              GET  /api/info
app/        Vite React — player + timeline + transcript/moments + widget panel + exports
```
The whole product is **the concept-spec schema**: `{widget, title, explanation, params, time, frame}`. VLM emits data; a deterministic widget kit renders it. Never generate raw code to run.

### Widget tiers (widgets.jsx)
1. **Parametric kit** — `matrix_mul · attention · softmax · function_plot`. Alammar role colors (Q purple, K orange, V blue, W green). Resize steppers + fill toolkit (🎲 random / ± noise / I identity / ◣ tril / 0 zeros).
2. **composite** — grammar of primitives (slider/matrix/heatmap/bars/plot/value) wired by a curated expr env. Linear dataflow.
3. **notebook** — pyodide (CPython 3.14 wasm), numpy+matplotlib preloaded, scipy/sympy on demand; sliders inject globals; matplotlib figs → images; debounced re-run.
4. **answer** — non-manipulable question → plain text answer card.

---

## Rebuild order (fastest path from blank, ~2–3 hr with muscle memory)
1. `uv init --python 3.12 && uv add yt-dlp mlx-vlm openai fastapi uvicorn pillow`
2. **ingest.py** (142 lines) — `video_id()`, `download()`, `parse_vtt()` (keep last line per cue, dedupe rolling captions), `extract_frames()` (uniform `fps=1/interval`, cap 120, name `f_<sec>.jpg`), `fetch_chapters()`. Default out = `data/<id>`.
3. Run ingest on the Karpathy URL → get frames while you code the rest.
4. **analyze.py** (308) — `CONCEPT_SCHEMA`, `SYSTEM` prompt, `valid()` (per-widget param shape check), `MlxBackend` / `OpenAIBackend`, `make_backend()` with **cloud guard** (`TACTILE_ALLOW_CLOUD=1` gate), CLI `--backend --video --limit --out-name`.
5. `cd app && npm create vite@latest . -- --template react && npm i qrcode pyodide` ; `vite.config.js`: `publicDir: '../data'` + proxy `/api → 127.0.0.1:8756`.
6. **widgets.jsx** (533) — the 4 kit widgets + composite + notebook + `WIDGETS` map. All take `{params, onState}`.
7. **App.jsx** (844) — `useYouTube` hook, timeline ticks, `Transcript` (select→AskBox), `Moments` list, `GlobalAsk` omnibox, `TouchOverlay` (drag→region), `ShareModal` (QR), `Landing` (categories + role cards), export bar. Router: `?v=<id>&role=<role>`, `#s=<b64spec>` remix.
8. **exporters.js** (154) — `buildNotebook`/`buildMarkdown`/`buildDeckHtml`/`download`; lowers every widget to runnable numpy.
9. **serve.py** (148) — the 3 endpoints; `nearest_frame`, PIL crop for /api/region.
10. Vendor pyodide offline (see below). Smoke-test, rehearse the arc.

**If time-boxed:** kit widgets + transcript-ask + one notebook + share/QR is the demoable core. composite / region / exports / roles are additive.

---

## Run it
```bash
# backend (local, free — no cloud possible without explicit flag)
TACTILE_MLX_MODEL=mlx-community/Qwen2.5-VL-32B-Instruct-4bit uv run serve.py --backend mlx
# frontend
cd app && npm run dev            # http://localhost:5173
# batch-extract a video's widgets (local)
uv run ingest.py "<youtube-url>" && uv run analyze.py --backend mlx --video <id>
```
Models on disk: `Qwen2.5-VL-7B-Instruct-4bit` (fast) and `-32B-` (strong). 32B reads tight crops far better.

## Cost guard (LEARNED THE HARD WAY — $3k Gemini blowup)
`make_backend()` **refuses gemini/openai unless `TACTILE_ALLOW_CLOUD=1`**. Batch × cloud frames is how a bill explodes. Local MLX = $0, unrestricted. Keep it this way for the demo. `.env` holds `GEMINI_API_KEY` (gitignored) — but keys got abuse-banned; demo on local.

## Offline safety (venue wifi WILL fail)
- **pyodide vendored** → `data/pyodide-dist/` (45MB closure incl scipy/sympy); `widgets.jsx` loads `indexURL: '/pyodide-dist/'`. Re-vendor script in git history if missing.
- **Pre-baked concepts** ship in `data/<id>/concepts.json` (Karpathy 55, real-estate 6, fintech 8) — the demo works with **zero** live model calls. Only ask/region/global-Ask need the model.
- YouTube playback needs internet; if venue blocks it, have a screen recording as fallback.

## Gotchas (already hit)
- Grid blowout: player rendered 8080px wide because nowrap chapter pills inflated the column → **`minmax(0,fr)` + `minWidth:0`** on grid children.
- Auto-follow stole the selected widget mid-load → manual marker clicks **pin selection 60s** (`pinnedUntil` ref).
- npm `pyodide` pkg has **no wheels**; vite SPA-fallback returns 200 for missing files (looks fine, isn't) → must vendor or use version-matched CDN.
- Thinking models (gemini pro) burn the token budget on reasoning → `max_tokens` ≈ 6000.
- Synthetic mouse events fight React drag state → `TouchOverlay` uses a **ref** for drag, not state (test with real mouse).

## Data model — concept spec
```json
{"widget":"attention","title":"...","explanation":"...",
 "params":{"q":[[...]],"k":[[...]],"temperature":1.0},
 "time":3780.0,"frame":"f_003780.jpg","user_made":true}
```
`notebook` → `params:{cells:[py...], sliders:[{name,min,max,value}]}` (cells REQUIRED).
Remix = whole spec b64-encoded into `#s=`. No backend, no accounts.

## Post-hackathon backlog (panel-ranked)
Click-the-Whiteboard ✓ built · Room mode (QR follows lecture) · Knob Golf (match-the-curve, Wordle share) · Gold Tick Wall (publish widget into a lecture — needs backend) · Autopilot Reel · Living Share Card (GIF) · fact-check/claim-board (Perspectivity crossover).
