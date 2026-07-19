# EduClaw (8kEdu) — Product Specification

> A build-from-scratch spec. Implementation-agnostic: it states *what* to build and *how to know it's correct*, not which lines to type. A competent builder (or a fresh agent) should be able to produce EduClaw from this document alone. For the fast, opinionated rebuild path and known pitfalls, see [`HACKATHON.md`](../HACKATHON.md).

---

## 1. Problem & product

People watch hours of lectures and how-to videos (AI, math, real-estate, finance) and retain little — watching is passive, and the figures/code/numbers on screen are frozen. YouTube summaries stay *inside* one video and can't be manipulated.

**EduClaw turns any YouTube lecture into a lab.** It reads the video's frames + transcript and, at each teachable moment, produces a **live, editable widget** beside the player — drag a matrix, run real Python, tweak a mortgage calculator seeded with the speaker's own numbers. Learners can also point at any region of the video or ask in words to mint a widget on demand, then remix and export what they build.

**Positioning:** "Brilliant.org, auto-generated from any lecture — on any topic."

**Primary users:** students & self-learners (study), teachers (build lessons), creators/writers (draft posts), researchers (later: cross-video analysis).

**Design principle — spec-as-data:** the model emits a structured **concept spec** (JSON); a deterministic widget kit renders it. Never generate raw executable code from the model for the parametric widgets. (The one sandboxed exception is the Python notebook widget, run in an isolated in-browser runtime.)

---

## 2. System overview

Four cooperating parts:

| Part | Responsibility |
|------|----------------|
| **Ingest** (offline CLI) | YouTube URL → local video, transcript (timestamped cues), chapters, and sampled keyframes. |
| **Analyze** (offline CLI) | For each keyframe + surrounding transcript → a **concept spec** via a vision-language model. Writes one JSON array per video. |
| **Serve** (local HTTP API) | On-demand widget minting for the live app: given a moment (and optionally a screen region or a question), return a concept spec or an answer. |
| **App** (web) | Plays the video; renders concept specs as interactive widgets synced to playback; lets users select/point/ask, remix, and export. |

Data flows one way for the batch path (Ingest → Analyze → App reads JSON) and request/response for the live path (App → Serve → model).

All model access supports **local** (free, offline-capable) and **cloud BYOK** backends behind one interface. Cloud is **disabled by default** (see §9).

---

## 3. Core data contract — the Concept Spec

This schema is the heart of the product; everything else serializes to/from it.

```jsonc
{
  "widget": "matrix_mul | attention | softmax | function_plot | composite | notebook | none",
  "title": "string — short human label",
  "explanation": "string — one sentence: why this matters",
  "params": { /* shape depends on widget, see below */ },
  "time": 3780.0,              // seconds into the video this moment maps to
  "frame": "f_003780.jpg",     // source keyframe filename (provenance)
  "user_made": true            // optional: minted by a viewer (vs batch)
}
```

**Per-widget `params`:**
- `matrix_mul`: `{ a: number[][], b: number[][] }` — `a`'s column count must equal `b`'s row count.
- `attention`: `{ q: number[][], k: number[][], temperature?: number }` — `q` and `k` share the head dimension (column count).
- `softmax`: `{ logits: number[] (≥2), temperature?: number }`.
- `function_plot`: `{ expr: string (JS, in `x` + slider names), sliders: {name,min,max,value}[] }`.
- `composite`: `{ components: Component[] }` where each `Component` is `{ id, type: slider|matrix|heatmap|bars|plot|value, ... , expr? }`; later components may reference earlier component values by id (linear dataflow).
- `notebook`: `{ cells: string[] (Python, REQUIRED, non-empty), sliders?: {name,min,max,value}[] }` — slider names are injected as globals.
- `none` / `answer`: no widget; carry a text `explanation` used as an answer card.

**Validation rule:** a spec is *valid* only if `widget` is a known type AND `params` satisfies the per-widget shape above (numeric 2D arrays, dimension agreement, non-empty cells, etc.). Invalid specs must be rejected/filtered, never rendered.

**Remix encoding:** a full spec base64-encoded into the URL fragment `#s=<b64>` reconstructs a widget on any load — no backend, no account.

---

## 4. Ingest — requirements

Input: a YouTube URL or 11-char video id. Output directory: `data/<videoId>/`.

- **R1** Download the video (≤480p is enough) and English subtitles; store `video.mp4`.
- **R2** Parse subtitles into cues `[{start, end, text}]` (seconds). Auto-captions repeat rolling context — **dedupe** so each cue's text appears once; drop cue-setting/positioning noise. Write `transcript.json`.
- **R3** Fetch chapter markers if present → `chapters.json` as `[{start, end, title}]` (may be empty).
- **R4** Sample keyframes **uniformly** across the video (interval = duration / N, floor ~10s; cap N≈120). Name each `f_<second>.jpg` at a legible height (~720p so on-screen code/equations are readable). Write `frames.json` as `[{time, file}]`.
- **R5** Re-running is idempotent per video (safe to overwrite regenerated artifacts).

Acceptance: after ingest, `data/<id>/` contains `transcript.json` (deduped), `frames.json`, `chapters.json`, a `frames/` dir with ≤120 legible JPGs, and `video.mp4`.

---

## 5. Analyze — requirements

For each keyframe, send the **image + a transcript window** (~±30s of cues around the frame's time) to a vision-language model with an instruction to emit a concept spec.

- **R6** The model sees the actual frame — the widget must be grounded in the **real on-screen values** (the matrix numbers, the code, the plotted curve), not invented from the topic word.
- **R7** Frames with no manipulable concept → `has_concept:false`, `widget:"none"` (skipped).
- **R8** Advice/finance/tutorial content → prefer a `notebook` **calculator**: sliders for the numbers a viewer would change (price, rate, down-payment, years), cells that compute + plot the outcome, defaults grounded in the speaker's numbers.
- **R9** Enforce output as JSON against the concept schema (provider-native structured output where available; otherwise robust JSON extraction + `valid()` filtering). Malformed → discard, keep sweeping (one bad frame never aborts the run).
- **R10** Merge near-duplicate adjacent concepts (same widget within ~90s).
- **R11** Output `data/<id>/concepts.json` — an array of valid specs, time-sorted. Support an alternate output filename for eval runs (don't clobber the canonical file).

Acceptance: a batch over the Karpathy lecture yields tens of valid, varied specs (attention, softmax, matmul, plots, ≥1 notebook), **zero** invalid specs in the output file.

---

## 6. Serve — requirements

Local HTTP API the app calls for on-demand minting. All endpoints operate on `data/<video>/`.

- **R12** `POST /api/widget {text, time, ask, video}` → nearest keyframe to `time` + transcript context + user intent → a concept spec (`user_made:true`) OR, if the ask isn't manipulable, `{answer: string}`.
- **R13** `POST /api/region {x,y,w,h (normalized 0..1), time, text, ask, video}` → **crop** the pointed region from the nearest keyframe (with a small context pad; upscale tiny selections for legibility) → concept spec for exactly what was circled.
- **R14** `GET /api/info` → `{backend, model, mode: local|byok, cloud: bool}` so the app can show the active engine.
- **R15** Same backend abstraction as Analyze; **cloud guard applies** (§9).

Acceptance: with a local model running, selecting a passage or dragging a region returns a renderable spec within one request; endpoint offline → app shows a friendly fallback, never a crash.

---

## 7. App — requirements

Single-page web app. Layout: video player (left), widget panel (right), transcript/moments (below). Header shows brand + active-engine badge; back-to-home link.

**Navigation**
- **R16** Landing: brand, one-line pitch, URL input ("paste a lecture"), a **showcase gallery grouped by category** (AI/STEM, real-estate, fintech…), and **role cards** (student/teacher/creator/researcher). Routing via `?v=<id>&role=<role>`; browser back works.
- **R17** Opening a non-ingested video still plays (YouTube), with a hint that widgets need ingest.

**Playback-synced widgets**
- **R18** Timeline strip under the player with **type-colored ticks** at each concept's time (color by widget type; viewer-made = distinct/gold; active = emphasized; hover grows). Playhead marker. Alternating chapter shading.
- **R19** As playback passes a concept's time, surface that widget automatically (auto-follow). A manual pick **pins** the selection for ~60s so auto-follow can't steal it mid-interaction.

**The widgets** (render any valid spec; see §3)
- **R20** Each widget is fully interactive and recomputes live: editable matrices with **resize steppers** and a **fill toolkit** (random / noise / identity / lower-triangular / zeros); sliders; softmax bars with temperature; plots; composite dataflow; and the **notebook** running real Python (numpy/matplotlib, scipy/sympy on demand) in an isolated in-browser runtime, re-running on slider drag.
- **R21** Widgets report their live state so it can be shared/exported.

**Creation surfaces**
- **R22** **Transcript**: YouTube-style rows (mm:ss chip + text), chapter pills, synced highlight, click-to-seek. **Select any passage** → ask box → mint a widget for that moment.
- **R23** **Global Ask** omnibox with suggestion chips — ask the lecture anything; returns a widget or an answer card.
- **R24** **Point at the video** ("touch the screen"): toggle → drag a box over any drawing/equation/number → that region comes alive (calls `/api/region`).

**Organize, remix, export**
- **R25** **Moments** list: all concepts grouped by chapter (type icon, time, viewer mark), with checkboxes.
- **R26** **Remix**: encode current widget state to `#s=` link + show a **QR** (so a room can open your exact state on their phones). No backend.
- **R27** **Export** selected moments to: **Jupyter `.ipynb`** (each widget lowered to runnable numpy/matplotlib + links back to the moment), **Markdown** (keyframes, code blocks, watch + live-remix links — a blog draft), and a **printable deck** (one slide per moment → ⌘P → PDF). All client-side.
- **R28** **Roles** tailor defaults: which tab opens first and which export format leads (student→notebook, teacher→deck, creator→markdown, researcher→notebook + "coming soon" cross-video note).

Acceptance: load a pre-baked video with no backend → timeline ticks, transcript, moments, and all pre-baked widgets are fully interactive; remix QR round-trips exact state; exports produce a valid notebook (opens in Jupyter), a pasteable markdown, and a printable deck.

---

## 8. Offline & reliability (demo-critical)

- **R29** The in-browser Python runtime and its packages must be **vendored locally** (served from the app), so notebooks work with no internet.
- **R30** Pre-baked `concepts.json` ship in the repo so the full app demos with **zero live model calls**; only ask/region/global-Ask need a running model.
- **R31** No feature may hard-crash on: missing backend, missing frames, venue wifi loss, or a malformed spec — degrade to a message or an answer card.

---

## 9. Cost & safety (non-negotiable)

- **R32** Cloud vision backends (Gemini/OpenAI) are **blocked by default**; enabling requires an explicit per-run opt-in env flag. Local backends are unrestricted. Rationale: a batch × cloud-frames run can silently run up a very large bill. (This happened; the guard is mandatory.)
- **R33** Secrets (API keys) live only in a gitignored `.env`; never committed, never logged, never printed.
- **R34** The app must make it obvious which engine is active (local vs BYOK) via the header badge.

---

## 10. Milestones (build order)

1. **M0 Ingest** one lecture → transcript + frames + chapters.
2. **M1 Analyze** → `concepts.json` of valid specs (local model).
3. **M2 Widget kit** — the 4 parametric widgets render from spec and are interactive.
4. **M3 App shell** — player + timeline + auto-follow + transcript.
5. **M4 Create** — select→ask, global Ask, point-at-region (Serve API).
6. **M5 Notebook** — in-browser Python widget (vendored runtime).
7. **M6 Organize/remix/export** — moments list, `#s=` + QR, ipynb/md/deck.
8. **M7 Polish** — categories, roles, timeline visuals, offline pre-bake, cost guard.

**Minimum demoable core:** M2 kit + M3 shell + M4 select-ask + one M5 notebook + M6 remix/QR. Everything else is additive.

---

## 11. Success criteria (the demo test)

A stranger, given only a YouTube lecture link, can within one minute: watch → see a figure become a widget → tweak it → point at another spot and mint a new one → share it to their phone via QR → export the session as a notebook. It works on an AI lecture, a real-estate video, and a finance video — same engine, any subject — and it runs on an open model locally at negligible cost.
