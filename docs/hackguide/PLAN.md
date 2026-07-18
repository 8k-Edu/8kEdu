# 8kEdu — Hackathon Plan & Status

**Event:** AITX × NVIDIA Claw Agent Hackathon · Jul 17–19 2026 · Antler VC, 800 Brazos St #340, Austin
**Hack window:** Fri 6:45 PM → Sun 11:00 AM code freeze (~40h) · **Team: 2–3**
**Build:** a fresh **autonomous learning agent** — *YouTube video → interactive learning dashboard*
**Last updated:** Jul 18 2026 (pre-event prep)

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

## What's left  ⏳ (Friday build)

**P0 — spine (Fri night)**
- [ ] Wire Omni into the sandbox — OpenShell blocks private-address custom endpoints; 3 known fixes: load omni GGUF into **ollama** (proven `ollama-local` path) / match `vllm-local` port / find the private-endpoint override
- [ ] `agents.yaml` — manager/worker on Nemotron; onboard via `nemoclaw onboard --agents`
- [ ] One manual cycle end-to-end: Apify find → process_video → Nemotron reason → Supabase write

**P1 — heartbeat (Sat AM)**
- [ ] The loop: wake → read state → JOB1 curriculum / JOB2 monitor → act/wait
- [ ] Interruption recovery from Supabase; alert-on-change

**P2 — containment + depth (Sat PM)**
- [ ] `sandbox-policy.yaml` + the **"unauthorized action blocked"** demo (the NemoClaw+OpenShell bounty proof)
- [ ] Self-improving curriculum from quiz results (Recursive Intelligence track)

**P3 — surface (Sat night)**
- [ ] Thin dashboard: live course + run log + the blocked-action proof (reuse existing widgets)

**P4 — submit (Sun AM)**
- [ ] Harden the loop (don't crash = 15 pts) · demo video · the 6 sponsor "why" blurbs · submit by 11:00

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
