# 8kEdu — lectures you can touch

Turn any YouTube lecture into an **interactive learning dashboard**. An autonomous agent reads the video's transcript + keyframes and turns every teachable moment into a **live, editable widget** beside the player — drag an attention matrix, run real Python in-browser, tweak a mortgage calculator with the speaker's own numbers. Any topic: AI/STEM, real estate, fintech, how-to.

> Brilliant.org, auto-generated from any lecture — on any topic.

---

## 🏁 Hackathon submission

| | |
|---|---|
| **Project** | 8kEdu — *YouTube video → interactive learning dashboard* |
| **Team** | **Team 8kEdu** — roster below |
| **Event** | AITX × NVIDIA Claw Agent Hackathon (Jul 17–19 2026) |
| **Primary track** | **Recursive Intelligence** — a cross-teacher concept knowledge graph that makes each run cheaper/sharper ([plan](docs/hackguide/RECURSIVE.md)) |
| **Also targeting** | **Red Hat Live Data** (Apify channel monitoring in the loop) · bounties: **NemoClaw + OpenShell**, **Nemotron**, **Most Commercializable** |
| **Loom video (2–5 min)** | `<PASTE LOOM URL>` — records the core loop live *(must be recorded with Loom)* |
| **Repo** | https://github.com/8k-Edu/8kEdu *(public)* |
| **Deployed** | Runs locally — `dev.localhost:5174` (dev) / `localhost:5173` (main); working-app capture is in the Loom |

### Write-up

**Problem.** The best teaching on Earth is on YouTube, but it's *passive* — you watch someone manipulate an attention matrix or a mortgage model, and you can't touch it. Re-deriving that interactivity by hand, per lecture, doesn't scale.

**Who it helps.** Students (tonight's lab from tonight's lecture), teachers (one-click decks), creators (one lecture → endless remixable artifacts), and researchers — a combined multi-hundred-billion-dollar learning market.

**Solution.** 8kEdu is an autonomous **Claw Agent**: on a heartbeat it finds lectures, watches them with **Nemotron-3-Nano-Omni** (vision + reasoning + tools, one open model, local/$0), and turns each teachable moment into a live widget — matrices, softmax, plots, runnable notebooks. A second **curator** agent grows a shared library per genre. Everything persists + caches in **Supabase**: analyze a video once, every future learner reuses it, so marginal cost → ~$0. The agent runs **contained by NemoClaw + OpenShell** — its reasoning executes inside a sandbox that can reach only allowlisted services and is blocked (and audit-logged) from exfiltrating anything.

**Impact.** A personal AI tutor that auto-builds a maintained, *touchable* course from any video, on any topic — with a cross-teacher knowledge graph that measurably gets faster and better the more it runs.

### Team roster
| Name | Role | Contact |
|---|---|---|
| Andy Khan | Agent loop, engine, frontend, containment | support@perspectivity.co |
| Nickolas Scipione | Performance, observability, DB schema/infra | github.com/nickscip |

> Paste the Loom URL before submitting.

---

## What it does

- **Paste a lecture URL** → the pipeline extracts interactive concepts across the whole video.
- **Timeline of touchable moments** — colored ticks per concept, chapter pills, synced transcript.
- **Live widgets** — matrices, attention, softmax, function plots, and full **Python notebooks** running in-browser (numpy/matplotlib via pyodide).
- **Select any transcript passage → "make it interactive"** — the model reads that exact frame and mints a widget.
- **Point at the video** ("touch the screen") — drag a box over any drawing → it comes alive.
- **Remix** — any widget's state encodes into a URL + QR (no backend); **export** selected moments to Jupyter `.ipynb`, Markdown, or a printable deck.
- **Roles** — student / teacher / creator / researcher tailor the default view + export.
- **Recursive memory** — `?view=graph` shows cross-teacher concepts and a persisted 64→8 held-out
  replay with recall and precision guardrails.

---

## Architecture

```mermaid
flowchart TB
  U["Learner — a goal or a video URL"] --> AG
  AG(["8kEdu agent · heartbeat loop<br/>finds → processes → sequences → monitors"])
  AG --> BRAIN["Nemotron Omni<br/>reads video frames · reasons · generates widgets · grades"]
  BRAIN --> TOOLS
  subgraph TOOLS["Tools (sandboxed)"]
    F["find lectures"]
    P["video → interactive widgets"]
    R["run widget code"]
  end
  TOOLS --> CACHE[("Supabase<br/>shared content cache + learner state")]
  CACHE --> DASH["Interactive learning dashboard<br/>live widgets · notebooks · mastery"]
  DASH -. "progress feeds next cycle" .-> AG
```

Under the hood, the pipeline: `ingest.py` (yt-dlp video + subs + chapters → ffmpeg keyframes) → `analyze.py` (each keyframe + transcript → vision-language model → concept-spec JSON) → `app/` (React player + timeline + widgets) with `serve.py` (FastAPI, live widget minting). Transcripts, frames, concept specs and inference results are cached in **Supabase** and shared across users — analyze a video once, everyone reuses it.

**The product is the concept-spec schema:** the model emits data (`{widget, title, params, time, frame}`), a deterministic widget kit renders it. No live codegen for the parametric widgets; the one sandboxed exception is the Python notebook widget (pyodide, in-browser).

> Full architecture + agent design: [`docs/architecture.pdf`](docs/architecture.pdf) (previewable) · [`docs/architecture.html`](docs/architecture.html) (with bounty/judging strategy)

Widget tiers: parametric kit (`matrix_mul`/`attention`/`softmax`/`function_plot`) → `composite` grammar → `notebook` (real numpy/matplotlib/scipy/sympy). Persistence/caching (transcripts, frames, concept specs, inference results — shared across users) is backed by **Supabase** in the agent build.

---

## Quick start

Prereqs: **Node ≥ 22.19**, **Python 3.12**, [`uv`](https://docs.astral.sh/uv/), `ffmpeg`. Local inference is optional (LM Studio or ollama with a vision + tools model); cloud backends are off by default.

```bash
git clone https://github.com/8k-Edu/8kEdu.git
cd 8kEdu
uv sync                 # python deps (yt-dlp, mlx-vlm, fastapi, pillow, …)
cd app && npm install   # frontend deps
cd .. && cd app && npm run dev   # browse the pre-baked demos at localhost:5173 — zero setup, zero model calls
```

Everything below (live widget minting, the agent, the dashboard) is optional and needs `.env` + a local model.

---

## Run locally

The repo ships **pre-baked concept data** for 3 demo videos, so the app works with **zero model calls**:

```bash
# frontend only — browse the pre-baked demos
cd app && npm run dev            # → http://localhost:5173
```

To process a **new** video and/or use live "make it interactive":

```bash
# 1) ingest + analyze a video (local model, free)
uv run ingest.py "https://www.youtube.com/watch?v=<id>"
uv run analyze.py --backend mlx --video <id>     # or --backend lmstudio / vllm / gemini

# 2) start the ask backend (live widget minting)
uv run serve.py --backend mlx                    # :8756, vite proxies /api → here

# 3) frontend
cd app && npm run dev                            # http://localhost:5173
```

Backends (`--backend`): `mlx` (in-process, local) · `lmstudio` · `vllm` (local [vllm-mlx](https://github.com/waybarrios/vllm-mlx) on Apple Silicon, via `VLLM_BASE_URL`/`VLLM_MODEL`) · `openai` (any OpenAI-compatible endpoint via `KEDU_BASE_URL`/`KEDU_MODEL`) · `gemini` (BYOK). For `run.sh` and the agent jobs, pick the vision backend with `KEDU_BACKEND` (default `lmstudio`).

### The autonomous agent + live dashboard

The agent stack (`?view=agent`, `?view=learn`, `?view=community`) persists to
Supabase. One-time setup:

1. Create a Supabase project → Project Settings → Database → copy the connection URI.
2. Add it to `.env`. **Prefer the Transaction pooler** (IPv4, port 6543) — the direct
   `db.<ref>.supabase.co:5432` endpoint is **IPv6-only** and fails on networks without an IPv6 route:
   `SUPABASE_DB_URL="postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:6543/postgres"`
3. Apply the schema — pick one:
   - **Tracked** (Supabase CLI, brew install supabase/tap/supabase):
     `supabase link --project-ref <ref> && supabase db push`
   - **One-shot** (psql): `psql "$SUPABASE_DB_URL" -f supabase/migrations/*.sql`

```bash
# learner heartbeat — Nemotron decides FIND / PROCESS / SEQUENCE / MONITOR each tick
uv run python -m agent.loop --interval 60

# curator heartbeat — autonomously grows the shared library per genre (find → frame → cache)
uv run python -m agent.curator --interval 300

# dashboard API (light, no VLM) — powers ?view=agent / ?view=learn / ?view=community
uv run python -m agent.api   # :8787, vite proxies /agent and /pub → here
```
Or just **`./run.sh --loop`** to start everything (serve + api + frontend + both heartbeats).
Then open **http://localhost:5173/?view=agent** (or `dev.localhost:5174` on the dev branch) — the live
heartbeat feed, the curriculum building itself, the cache moat, and the OpenShell containment status.
Containment is applied + proven separately: see [`claw-agent/`](claw-agent/).

> **Cost guard:** cloud backends (`gemini`/`openai`) are **blocked by default** — set `KEDU_ALLOW_CLOUD=1` to deliberately spend. Local (`mlx`/`lmstudio`/`vllm`) is unrestricted. Secrets live in a gitignored `.env` (see `.env.example`).

Pyodide (for notebook widgets) is vendored under `data/pyodide-dist/` for offline use.

### Contained agent (NemoClaw + OpenShell)

The agent's reasoning can run **inside an OpenShell sandbox** that allowlists only YouTube, Apify,
Supabase and the local model — everything else is blocked + OCSF-logged. Reproduce:

```bash
export DOCKER_HOST="unix:///Users/<you>/.orbstack/run/docker.sock"   # OrbStack socket
nemoclaw scoutclaw policy-add 8kedu --from-file claw-agent/policies/8kedu.yaml --yes
bash claw-agent/contain_demo.sh            # allowed sinks succeed, exfil blocked + logged
bash claw-agent/contained_agent_demo.sh    # 8kEdu's analyze runs INSIDE the sandbox → real widget
```
Full write-up: [`claw-agent/README.md`](claw-agent/README.md).

---

## Sample `.env`

Secrets live in a gitignored `.env` at the repo root. Copy this and fill in your values:

```bash
# --- Supabase (persistence + shared cache) ---
# Prefer the Transaction pooler (IPv4 :6543); the direct db.<ref>.supabase.co:5432 is IPv6-only.
SUPABASE_DB_URL="postgresql://postgres.<ref>:<db-password>@aws-0-<region>.pooler.supabase.com:6543/postgres"
SUPABASE_URL="https://<ref>.supabase.co"
SUPABASE_SECRET_KEY="sb_secret_..."          # service role (server-side only)
SUPABASE_PUBLISHABLE_KEY="sb_publishable_..."
SUPABASE_PROJECT_REF="<ref>"

# --- Apify (live channel monitoring) ---
APIFY_API_TOKEN="apify_api_..."
APIFY_USER_ID="<apify-user-id>"

# --- Model (Nemotron via any OpenAI-compatible server; LM Studio or ollama) ---
KEDU_MODEL="nvidia/nemotron-3-nano-omni"       # analyze/serve
NEMOTRON_MODEL="nvidia/nemotron-3-nano-omni"      # agent brain
# KEDU_BASE_URL / NEMOTRON_BASE_URL default to http://localhost:1234/v1 (LM Studio)

# --- Local runtime ---
AGENT_HANDLE="demo"                                # per-learner isolation on the shared DB
DOCKER_HOST="unix:///Users/<you>/.orbstack/run/docker.sock"   # for the NemoClaw sandbox
# KEDU_ALLOW_CLOUD=1                             # opt-in only; cloud VLM backends are off by default
```

No cloud API keys are required — the default path is **fully local** (LM Studio/ollama), $0.

---

## Datasets & provenance

- **Demo lectures** — public YouTube videos, fetched with `yt-dlp`: Karpathy *Let's build GPT*
  (`kCc8FmEb1nY`), VisualAI *Multi-Head Attention* (`42L1q1Z4Ojc`), a real-estate explainer, a fintech
  explainer, an Epicurious how-to. We store derived artifacts only (transcript, keyframes, concept
  specs) under `data/<videoId>/` — not the source video.
- **Concept specs** — *generated* by Nemotron-3-Nano-Omni from each keyframe + transcript window
  (the `{widget, params, …}` JSON). Cached in Supabase and reused across users.
- **Community feed seed** — **synthetic** demo data: public-artifact rows seeded from real cached
  concepts, with fabricated usernames (`ada`, `karpathy_fan`, …) and vote counts, to populate
  `?view=community`. Clearly synthetic; no real user data.
- **Curator library** — the curator agent discovers real YouTube videos per genre at runtime and
  frames them; those become additional cached concepts.

---

## Known limitations & next steps

**Fixed**
- ✅ **Video download now runs contained** — `*.googlevideo.com` + `*.youtube.com` are wildcard-allowlisted
  in the `8kedu` policy, and yt-dlp runs inside the sandbox (`--no-check-certificates`, since the egress
  proxy is the boundary). Verified: a full video pulled + framed inside scoutclaw.
- ✅ **The whole heartbeat runs in-sandbox** — search, download, frame, Nemotron analyze, and the DB
  write all execute inside scoutclaw. Raw Postgres can't cross the SNI egress proxy, so DB writes go
  via **Supabase PostgREST** (`agent/db_rest.py`, `KEDU_DB_REST=1`). Verified: run rows + concept
  upserts written to Supabase from inside the sandbox, exfil still blocked + OCSF-logged.

**Limitations**
- **Recursive benchmark is a replay** — the 64→8 result uses cached real full-sweep outputs and a
  concrete warm retrieval plan; it is not a fresh paired wall-clock run.
- **Warm reuse copies a validated prior spec** — adapting that spec to the new teacher's exact visual
  parameters is the next grounding upgrade.
- **Widget priors and prerequisite edges are visible but not yet closed-loop** — generation bias and
  prerequisite-sorted course assembly remain future work.
- **Mastery → re-sequence** loop is schema-only (not yet wired).
- **Community needs real auth** — currently a single `demo` learner; profiles/voting need Supabase Auth.

**Next steps**
1. Run fresh paired cold/warm model benchmarks and adapt retrieved specs to new-frame parameters.
2. Use widget priors during generation and prerequisite edges during course assembly.
3. Wire mastery feedback → curriculum re-sequencing.
4. Add Supabase Auth for real profiles/voting (the remaining community limitation).

---

## Repo layout

```
ingest.py  analyze.py  serve.py     # python pipeline + ask API
app/src/    App.jsx widgets.jsx exporters.js main.jsx
data/<videoId>/                     # per-video: transcript, frames, chapters, concepts
spec/spec.md                        # build-from-scratch spec
docs/architecture.pdf|.html         # architecture diagram (previewable)
docs/hackguide/                     # PLAN · STRATEGY · HACKATHON (hackathon docs)
```
