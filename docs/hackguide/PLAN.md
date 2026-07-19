# 8kEdu — Hackathon Plan & Status

**Event:** AITX × NVIDIA Claw Agent Hackathon · Jul 17–19 2026 · Antler VC, 800 Brazos St #340, Austin
**Hack window:** Fri 6:45 PM → Sun 11:00 AM code freeze (~40h) · **Team: 2–3**
**Build:** a fresh **autonomous learning agent** — *YouTube video → interactive learning dashboard*
**Last updated:** Sun Jul 19 2026 — recursive KG, held-out replay, graph viewer, submission docs, and final Loom script complete

---

## What we're building

Give 8kEdu a learning **goal**; on a heartbeat it autonomously (1) **builds a curriculum** — finds lectures, turns each into interactive widgets, sequences a course, tracks mastery, fills gaps; and (2) **monitors channels** — new upload → auto-builds its dashboard. Contained by OpenShell, reasoned by Nemotron Omni, persisted in Supabase.

It qualifies as a "Claw Agent": **heartbeat-driven** (wakes on a loop, not a prompt) · **proactively autonomous** · **persistent with context**. See [`architecture.pdf`](../architecture.pdf) and [`STRATEGY.md`](STRATEGY.md).

---

## Where we are  ✅ (prep, before the clock)

| Piece | State |
|---|---|
| Direction locked | 8kEdu autonomous learning agent (Claw-Agent compliant) |
| Hackathon spec + NVIDIA stack | read + researched (NemoClaw/OpenShell/Nemotron from primary sources) |
| NemoClaw + OpenShell + OpenClaw | **live locally** — sandbox `scoutclaw`, dashboard `127.0.0.1:18789` |
| Nemotron **Omni** brain | **running local** — `nemotron-3-nano-omni` in LM Studio (:1234), vision + tool + reasoning, verified, $0 |
| Supabase (persistence + cache) | 2-tier schema applied to live DB (`cfyelmzuuwqadnwxcxkv`), REST + Postgres roundtrip proven |
| Apify (live data) | token validated (user `perspectivity`) |
| Containment mechanism | understood — `sandbox-policy.schema.json` + `nemoclaw scoutclaw shields up` |
| Engine (video→widgets) | exists as the `process_video` tool; app rebranded 8kEdu; branch-aware host (dev.localhost) |
| Docs | README + architecture diagram (mermaid) + `architecture.pdf`/`.html` + this hackguide |

**Every hard/risky piece is proven before the event.** Friday = assemble the loop on a working foundation.

---

## The funnel, formalized  🧮 (whiteboard, Sat AM)

What goes into the funnel and what comes out — the artifact equation:

```
V   = [(m_i, Tr_i)]  i=1..M          # video → segments: keyframes m_i = {f_i1..f_in} + transcript chunk Tr_i
      payload: transcript [{chunk:str, timestamp}], video_payload [{t_i, f_i}]
g   = G(Tr, title) ∈ Genres          # genre classifier; taxonomy grows 20→100 (AI, RE, FIN, …)
S_g = system prompt for genre g      # the lens the model reads the frame through
A_i = M̂(S_g, UC_k, m_i ⊕ f_i..f_n ⊕ Tr_i)   # M̂ = Nemotron-3-Nano-Omni; UC_k = user context/question
C[(v, i, g)] = A_i                   # Supabase global cache — computed once, reused ∀ learners
O   = Map(⋃ A_i, t_i → T_i)          # dashboard: artifacts pinned to the timeline
```

Marginal cost per learner → 0 because C is keyed on (video, segment, genre), not on user.

**Implemented:** `analyze.py --genre auto|ai_stem|finance|real_estate` — `detect_genre()` votes over the
transcript, `apply_genre()` composes `SYSTEM ⊕ S_g`. UC_k is the live ask-path (`serve.py /api/widget`, `/api/region`).

**Ingest access notes (whiteboard):** yt-dlp today; scale options = (a) rotating proxies, (b) piggyback the
user's own IP via a browser extension (screen-capture permission?). Beyond YouTube: Nebula / Vimeo APIs.

---

## What's left  ⏳

**P0 — spine** ✅ done — Omni local (LM Studio :1234), tools wired, end-to-end cycle proven
**P1 — heartbeat** ✅ done — `agent/loop.py`: Nemotron decides FIND→PROCESS→SEQUENCE, Supabase persists runs; cache-reuse verified (`supabase-cache, reused: True`)
**Landing** ✅ done — hero pour-in/pop-out artifact loop, river carousel, genre shelves, typed markets section, light/dark

**P2 — containment** ✅ done — the NemoClaw+OpenShell bounty proof
- [x] `claw-agent/policies/8kedu.yaml` — egress allowlist (youtube/apify/supabase/local-inference), schema-valid, applied as **policy v4** on `scoutclaw`
- [x] Blocked-exfil demo: `claw-agent/contain_demo.sh` — YouTube→200, Supabase→401 (reached), webhook.site exfil→**BLOCKED**; agent's own `python3` urllib path denied too
- [x] OCSF audit log proof: `NET:OPEN DENIED python3.13 -> webhook.site:443 [reason: not allowed by any policy]`, `denied_action_count=1`
- [x] **option D done** — 8kEdu's `analyze` runs *inside* scoutclaw (Nemotron via allowlisted endpoint → real widget; exfil blocked + OCSF-logged; snapshot-persisted). Unblocked by allowlisting the OpenShell gateway IP. See `claw-agent/contained_agent_demo.sh`
- [ ] final step for demo: `nemoclaw scoutclaw shields up` on camera

**P3 — agent dashboard** ✅ done — judges SEE the autonomy
- [x] `agent/api.py` (light, no VLM) — `/agent/state` (runs+curriculum+cache), `/agent/tick` (wake on demand), `/agent/containment` (live policy status)
- [x] `?view=agent` dashboard in the app: heartbeat feed (action-coded decisions + why + cache-reuse), curriculum building itself, cache-moat tiles (55 widgets, marginal cost → $0), containment strip (allowlist + N exfil blocked), "wake now" button; polls every 2.5s; "agent live" nav link on landing
- [x] proven live: tick fires Nemotron decision → persists → feed updates 4→5

**JOB2 — monitor** ✅ done — the 2nd autonomous job (proactive, not prompted)
- [x] `monitor_channel` (Apify primary, yt-dlp fallback) wired into the heartbeat MONITOR action
- [x] order-independent new-upload diff vs `last_video_id` baseline; FK-safe (`ensure_video`); auto-adds new uploads to the curriculum
- [x] dashboard panel "Watching for new uploads" (@AndrejKarpathy · last checked · 📡 via Apify)
- [x] proven live: bootstrap → 0 added (baseline), then 2 new uploads detected → curriculum 1→3

**P3.5 — Recursive Intelligence** ✅ done — the primary-track proof
- [x] persistent cross-teacher graph: 71 concepts, 163 real exemplars, eight videos, seven teachers
- [x] controlled held-out replay: 64 cold calls → eight warm exploration calls + seven graph reuses
- [x] quality guardrails: 100% known-concept recall and 100% retrieval precision
- [x] `?view=graph`: live graph, cross-teacher exemplars, persisted cold/warm rows, demo controls
- [x] executed paired conditions persisted under one experiment ID with actual wall-clock timings

**P4 — submit (Sun AM)**
- [x] Harden the loop — heuristic fallback + per-action/-channel error isolation + failed runs logged; never crashes
- [x] [`SUBMISSION.md`](SUBMISSION.md) — what-it-is, 6 sponsor "why" blurbs, 100-pt rubric self-map
- [x] [`DEMO.md`](DEMO.md) + [`DEMO_VIDEO_TRANSCRIPT.md`](DEMO_VIDEO_TRANSCRIPT.md) — record-ready 4:20 Loom flow
- [ ] **YOURS:** record the Loom video · paste its URL into README · submit on the platform

---

## Roadmap — the product beyond the hack  🚀

Where 8kEdu goes after the demo. Ordered by leverage. The schema foundation already
exists (`goals`, `curriculum`, `mastery`, `monitored_channels`, `inference_cache`) — most
of this is surface + orchestration on top of the agent we built.

> **Detailed, buildable specs** (data model → API → UI → effort → demo-scope) for all four:
> **[`ROADMAP.md`](ROADMAP.md)**. Summary below.
>
> **✅ Update:** a working slice of **all four** was built at the hack — R4 cache hit-rate,
> R3 How-To lens + course, R1 `?view=learn` Duolingo flow, R2 `?view=community` remix feed.

### R1 — Learn track: dynamic curriculum, Duolingo-style  *(the core product)*
The learner says **what** they want to learn — a *how-to*, a *concept*, a *subject*
("Reinforcement Learning", "Deep Learning", "buy my first house"). The agent then:
1. **Suggests source videos** from strong channels — offering **multiple course paths**
   (e.g. "fast track · 4 videos" vs "deep · 12 videos", or by channel/teacher).
2. Learner **picks a path, or auto-picks** (agent sequences the best subset).
3. Builds a **Duolingo-style curriculum** — ordered units from *subsets of YouTube videos*
   on that subject, each unit = a lecture segment → interactive artifacts.
4. Learner **learns → generates artifacts → shares → remixes**; mastery tracked, gaps refilled.
5. Everything is **cached** (per video·segment·genre) → the 2nd learner on that path pays ~0.
- Builds on: `agent/loop.py` JOB1 (already finds + processes + sequences), `goals`/`curriculum`/`mastery` tables.
- New: a "what do you want to learn?" intake → path proposals; unit/lesson UI (streak, progress, next-up).

### R2 — Social + community: remix network
Public feed of generated artifacts + courses. **Upvote, fork, remix** (a remix is already a URL).
Creator/educator profiles; "most remixed this week". Turns single-player learning into a network
where the best artifacts compound. Ties the **Creator** market ($250B) directly to the product.
- New: public artifact/course records, votes, follow graph; moderation.

### R3 — Breadth of examples (esp. "How To" + more categories)
More pre-baked, high-quality demo courses across genres — **How-To** front and center, plus
cooking, fitness, coding tutorials, business. Each new genre = a new `S_g` lens ([analyze.py](../../analyze.py)).
Drives the "any topic, not just code" promise and the gallery.
- Partly in-scope now: adds credibility to the demo. Cheap wins via the genre-lens system already built.

### R4 — Robust caching for effectiveness
Harden the moat: populate `inference_cache` (prompt-hash keyed, `hits` counter) so identical
frame+prompt+genre asks never recompute; add cache-warming for popular channels; eviction/versioning
when the model or prompt changes. Make marginal-cost-→0 a measured, dashboarded number, not a claim.
- Builds on: `inference_cache` table (exists, empty) + the `process_video` 3-tier cache already live.

**Sequencing:** R3 + R4 are partly in-scope (content + cache depth strengthen the demo). R1 is the
next real build (the schema is ready). R2 is the growth layer once R1 has users.

---

## Decisions on record
- Fresh agent, **not** a recast of the prompt-driven video app (that would fail the Claw-Agent definition).
- Nemotron **Omni** = the whole brain (vision + reasoning + tools in one model) → Nemotron bounty is central, not bolted-on.
- Local-first inference (LM Studio / ollama) → **zero cloud cost** (after a $3k Gemini incident, cloud is off by default).
- Engine reused as a **tool**; the fresh build is the autonomy loop + containment + persistence.

## Sponsor keys (in `claw-agent/.env`, gitignored)
Supabase ✅ · Apify ✅ · Featherless ⛔ optional (backup serving). Nemotron via local LM Studio (no cloud key needed).

## Risk to manage
The engine is pre-built → keep the widget UI minimal/rebuilt and make the **autonomous loop the demo star**, so it reads as built-at-event.

---

*Companion docs:* [`HACKATHON.md`](HACKATHON.md) (rebuild playbook + stack recipe) · [`STRATEGY.md`](STRATEGY.md) (bounty + judging map) · [`../architecture.pdf`](../architecture.pdf) (diagram).
