# 8kEdu — Submission

**YouTube video → interactive learning dashboard, built by an autonomous agent.**

Give 8kEdu a learning goal. On a heartbeat — not a prompt — it finds the right lectures,
watches them with a vision-language model, turns every figure, equation and code block into a
touchable widget, sequences a Duolingo-style course, and keeps watching the source channels for
new uploads. It reasons with **Nemotron**, is contained by **NemoClaw + OpenShell**, and persists
+ caches everything in **Supabase** so the marginal cost of the next learner is ~$0.

- **Live app:** `http://localhost:5173` (or `dev.localhost:5174` on the dev branch)
- **Watch the agent work:** `/?view=agent` · **Learn flow:** `/?view=learn` · **Remix feed:** `/?view=community`
- **Containment proof:** `bash claw-agent/contain_demo.sh`
- **Repo:** github.com/8k-Edu/8kEdu · **Run:** see [`../../README.md`](../../README.md)

---

## Why it's a Claw Agent (not a chatbot)

| Trait | In 8kEdu |
|---|---|
| **Heartbeat-driven** | `agent/loop.py` wakes on an interval, reads state from Supabase, decides the single next action, acts. The trigger is time + state, never a human message. |
| **Proactively autonomous** | Two agents, three jobs: the **learner loop** builds a curriculum (find → process → sequence) and monitors channels (Apify → new upload auto-joins the course); the **curator loop** grows the shared library on its own — picks the least-covered genre, finds + frames a new lecture, caches it for everyone. All unprompted. |
| **Persistent with context** | Supabase *is* the agent's memory — learners, goals, curriculum, mastery, run log, and the shared cache. |

Proven live: a real 3-tick run — `FIND_VIDEO` → `PROCESS_VIDEO` (55 widgets reused from cache) →
`SEQUENCE` — every decision made by Nemotron and logged. The loop is crash-proof: model
unreachable → heuristic fallback; tool failure → logged error run; it never dies.

---

## The 6 sponsors — each load-bearing, each with its "why"

1. **Nemotron (nvidia/nemotron-3-nano-omni)** — *the whole brain, one model.* It reads the video
   frames (omni vision), plans the course, writes the widget specs, and calls the tools. Why this
   model: multimodal + a thinking budget + tool-calling in a single **open** model that runs
   *inside* the sandbox — so no learner data ever leaves the box. ~3B active params (MoE) = fast.

2. **NemoClaw + OpenShell** — *build a capable agent worth containing, then contain it.* The agent
   has web reach (yt-dlp/Apify) and executes generated Python — genuinely dangerous. The `8kedu`
   egress policy allowlists exactly YouTube, Apify, Supabase and the local model; **everything else
   is blocked at the proxy and written to a tamper-evident OCSF audit log.** And it's not just a
   probe: **8kEdu's actual reasoning (`analyze.py`) runs *inside* `scoutclaw`** — Nemotron reaches
   only the allowlisted endpoint, produces a real widget, and **cannot exfil what it made** (POST to
   `webhook.site` → `DENIED`, OCSF-logged). Provisioned within the policy (pypi-only), snapshot-persisted.
   See [`claw-agent/contained_agent_demo.sh`](../../claw-agent/contained_agent_demo.sh).

3. **Supabase** — *persistence is the Claw-Agent requirement, and the moat.* Two tiers: per-learner
   state (goals, curriculum, mastery) and a **global cache** (transcripts, frames, concepts,
   inference results) shared across all users. Analyze a video once → every future learner reuses
   it. Live number on the dashboard: **cache hit-rate % and $ saved.**

4. **Apify** — *live-web coverage, not a toy.* Channel monitoring runs through the Apify YouTube
   scraper (yt-dlp fallback for resilience). "Watch this creator" becomes real: a new upload is
   detected and auto-added to the course on the next heartbeat.

5. **vLLM** — *the serving path to scale.* The blueprint `vllm` profile hosts Nemotron in
   production; local LM Studio proves the exact same OpenAI-compatible loop today at $0.

6. **The product itself (Most Commercializable)** — a personal AI tutor that auto-builds your
   course from YouTube. Obvious market (students, teachers, creators, researchers — $400B / $160B /
   $250B / $35B), near-zero marginal cost via the shared cache, usable tomorrow.

---

## Judging self-map — 100 pts

| Criterion | Pts | Evidence in the build |
|---|---|---|
| **Technical execution & completeness** | 30 | Heartbeat loop + 4 real tools + omni brain + 2-tier Supabase; completes the core workflow and doesn't crash (hardened with fallbacks). Live agent dashboard. |
| **Use of sponsor tech** | 30 | Six load-bearing sponsors above, each with a one-line "why" (the 15 points most teams skip). |
| **Value & impact** | 20 | Paste a goal → a maintained, interactive course. Four named markets. Dynamic curriculum + remix network. |
| **Frontier factor** | 20 | A *contained* code-generating learning agent — novel combo — plus a measured cost moat (shared cache, A3B active params, frame-level hit-rate). |

---

## Tracks

- **Recursive Intelligence** — quiz/mastery feeds back each cycle → the agent re-sequences the
  course and re-picks sources (schema + loop in place).
- **HiddenLayer Runtime Security** — the OpenShell containment + OCSF audit story.
- **Red Hat Live Data** — Apify live channel monitoring.

---

## What's live and proven (not slideware)

- Autonomous heartbeat: Nemotron decides FIND/PROCESS/SEQUENCE/MONITOR, persists every run.
- Containment: `8kedu` policy applied (v4); exfil blocked + logged; `contain_demo.sh` reproduces it.
- Cache moat: 55 widgets cached; frame-level `inference_cache` proven (identical ask = 0s hit).
- Dynamic curriculum: `?view=learn` — subject → 2 real paths → Duolingo unit map, end to end.
- Remix network: `?view=community` — hot/new feed, upvote, fork.
- Breadth: `how_to` genre lens + a real How-To course (scrambled eggs) in the gallery.
- Curator: a 2nd autonomous agent that grows the library per genre — visible on the dashboard
  ("Library, growing itself"), compounding the cache moat with no human in the loop.

*Companion docs:* [`DEMO.md`](DEMO.md) (runbook) · [`PLAN.md`](PLAN.md) (status) · [`STRATEGY.md`](STRATEGY.md) · [`ROADMAP.md`](ROADMAP.md) · [`../architecture.pdf`](../architecture.pdf).
