# 8kEdu — Demo Runbook

Target: a tight **~2-minute** demo video that hits all four judging criteria. Record in this order.

## Before you record
```bash
./run.sh            # serve + agent-api + frontend  (add --loop to run the live heartbeat)
```
Confirm the LLM server is up — LM Studio serving `nvidia/nemotron-3-nano-omni` on :1234, or vllm-mlx via `./scripts/serve-vllm.sh` (then `TACTILE_BACKEND=vllm`) — and the scoutclaw sandbox is up
(`nemoclaw scoutclaw status`). Open the app at `http://dev.localhost:5174/`.

Have two terminals ready: one for the app, one for `claw-agent/contain_demo.sh`.

---

## Scene 1 — the hook (15s)
**Landing page.** "Drop any YouTube lecture, an autonomous agent turns it into an interactive
course." Show the hero: the Karpathy video pours into the funnel, artifacts pop out, the river of
artifacts flows. One line: *"This isn't a chatbot — it's an agent that works on a heartbeat."*

## Scene 2 — the product vision, live (30s)  → `?view=learn`
Click **learn**. Type **"Reinforcement Learning"** → *build my course*.
- The agent runs a real search and proposes **two paths** (Fast track / Deep dive) — real videos.
- Pick Fast track → the **Duolingo unit map** appears: unit 1 unlocked, the rest locked.
- Line: *"It found the videos, sequenced the course, and it'll process each unit on its heartbeat."*

## Scene 3 — watch the autonomy (30s)  → `?view=agent`
Click **agent live**. This is the money shot.
- **Heartbeat feed**: real decisions — FIND → PROCESS (⚡ 55 widgets reused) → SEQUENCE — each with
  Nemotron's reasoning and a timestamp.
- Press **⏻ wake now** → a new heartbeat fires live, Nemotron decides, the feed updates.
- Point at the tiles: **cache hit-rate**, **$ saved**, **containment ON · N exfil blocked**.
- **Watching for new uploads** (Apify) + **Contained by OpenShell** panels.
- Line: *"Nemotron decides, the tools act, Supabase remembers — every 60 seconds, on its own."*

## Scene 4 — contain the capable agent (25s)  → terminal
```bash
bash claw-agent/contain_demo.sh
```
- YouTube → 200 (allowed) · Supabase → 401 reached (allowed) · **webhook.site exfil → BLOCKED**.
- Show the OCSF audit line: `NET:OPEN DENIED python3 -> webhook.site:443 [not allowed by any policy]`.
- Line: *"A learning agent that runs generated code and reaches the web is dangerous — so we
  contained it. Everything off the allowlist is blocked and logged."*
- Optional flourish: `nemoclaw scoutclaw shields up`.

## Scene 5 — it compounds (15s)  → `?view=community`
Click **community**. The remix feed: artifacts other learners published, upvoted, forked.
- Line: *"Every artifact is a URL — publish, upvote, remix. One lecture becomes endless content."*

## Close (10s)
Back to the landing gallery — scroll the genres (AI, How-To, Real estate, Fintech).
- Line: *"Any topic, not just code. Analyze once, cached for everyone — marginal cost near zero.
  That's 8kEdu."*

---

## The four criteria, hit in order
- **Technical execution** — Scene 3 (real heartbeat, tools, DB, no crash).
- **Sponsor use** — Scenes 3+4 (Nemotron, OpenShell, Supabase, Apify all on screen) + the 6 "why"
  lines in [`SUBMISSION.md`](SUBMISSION.md).
- **Value & impact** — Scene 2 (paste a goal → a real course).
- **Frontier factor** — Scene 4 (a *contained* code-gen agent) + the cache moat number in Scene 3.

## If something fails on camera
- LM Studio slow/down → the loop shows a **heuristic fallback** run (still advances) — that's a
  feature, mention it. The frontend still renders cached data.
- Apify slow → `monitor_channel` falls back to yt-dlp automatically.
- serve.py down → the engine badge shows "offline"; the dashboard + learn/community still work
  (they read Supabase via the agent API, not the VLM).
