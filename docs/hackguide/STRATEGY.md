# 8kEdu — Bounty & Judging Strategy

How each requirement, bounty, and track maps to a real part of the build. (Visual version: [`../architecture.html`](../architecture.html).)

## Claw Agent definition (mandatory)
| Trait | How 8kEdu satisfies it |
|---|---|
| **Heartbeat-driven** | OpenClaw Cron wakes on interval → reads Supabase state → advances curriculum or checks channels → acts/waits. Trigger is time/state, never a human message. |
| **Proactively autonomous** | Finds lectures, builds & repairs the curriculum, generates + verifies widgets, alerts on new uploads, recovers from interruption — unprompted. |
| **Persistent with context** | Supabase = the agent's workspace/memory/session: learner model, course, mastery, run log. |

## Bounties
| Bounty | How we win it |
|---|---|
| **NemoClaw + OpenShell** | `nemoclaw onboard --agents agents.yaml`. Agent has web (Apify/yt-dlp) + **exec** (runs generated Python) → worth containing. OpenShell allowlists youtube/apify/supabase + guards the filesystem. **Demo:** off-list host or `~/.ssh` → **blocked + logged**. |
| **Nemotron** | `nemotron-3-nano-omni` is the whole brain — one model reads video frames (omni vision), plans the course, generates widget specs, grades quizzes, calls tools. Why: multimodal + thinking budget + tool-calling in one open, sandbox-runnable model. |
| **vLLM** | Blueprint `vllm` serving profile hosts Nemotron; local LM Studio proves the loop today. |
| **Most Commercializable** | A personal AI tutor that auto-builds your course from YouTube — obvious market, near-zero marginal cost via the shared cache. |

## Tracks
- **Recursive Intelligence** — a **cross-teacher concept knowledge graph** built as the byproduct of the widget pipeline: same concept from different teachers collapses to one node; new videos reuse known nodes instead of regenerating → measurably faster/sharper each run. Full plan: [`RECURSIVE.md`](RECURSIVE.md).
- **HiddenLayer Runtime Security** — pairs with the OpenShell containment story.
- **Red Hat Live Data** — Apify live monitoring of channels.

## Judging — 100 points
| Criterion | Pts | Our play |
|---|---|---|
| Technical execution & completeness | 30 | Real pipeline (heartbeat + 4 sandboxed tools + omni brain + 2-tier DB); completes core workflow without crashing. |
| Use of sponsor tech | 30 | Six load-bearing sponsors — NemoClaw · OpenShell · Nemotron · Supabase · Apify · vLLM — each with a one-line "why". |
| Value & impact | 20 | Non-obvious + usable tomorrow: paste a goal → maintained interactive course. |
| Frontier factor | 20 | Novel combo (contained code-gen learning agent) + performance (shared cache, A3B active params). |

## The "why sponsor" one-liners (the 15 hidden points most teams skip)
- **Nemotron:** multimodal + thinking budget + tool-calling in one open model that runs *inside* the sandbox — no data leaves.
- **Supabase:** the agent's persistence *is* the Claw-Agent requirement; global cache makes marginal cost per learner ~0.
- **OpenShell:** an agent with web + code-exec is genuinely dangerous → containment is the product's trust story.
- **Apify:** turns "monitor conditions" from a toy into real live-web coverage.
