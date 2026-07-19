# 8kEdu — Containment (NemoClaw + OpenShell)

The bounty: **"build a capable agent worth containing, then contain it."**

8kEdu's learning agent is capable — on a heartbeat it searches YouTube, calls Apify,
writes learner state to Supabase, and reasons on a local Nemotron model. This directory
is the **containment** half: an OpenShell egress policy that allowlists exactly those four
sinks and denies everything else, enforced by the `scoutclaw` sandbox and written to a
tamper-evident OCSF audit log.

## Files
| File | What |
|---|---|
| [`policies/8kedu.yaml`](policies/8kedu.yaml) | Egress policy preset — YouTube, Apify, Supabase, local inference (+ the OpenShell gateway IP). Nothing else. |
| [`agent_egress_probe.py`](agent_egress_probe.py) | The agent's own urllib egress pattern + a rogue exfil. Run inside the sandbox. |
| [`contain_demo.sh`](contain_demo.sh) | One-command demo: allowed sinks succeed, exfil blocked + logged. |
| [`contained_agent_demo.sh`](contained_agent_demo.sh) | **Option D** — 8kEdu's `analyze` step runs *inside* the sandbox: Nemotron reasoning → real widget, exfil blocked. |

## The agent runs contained (option D)

Beyond proving the policy blocks exfil, **8kEdu's actual reasoning runs inside `scoutclaw`**:

1. **Provisioned within the policy** — `yt-dlp`, `ffmpeg` (static), `openai`, `pillow` installed via the
   policy-allowed **pypi** channel into `/sandbox/.local` (no arbitrary-host downloads).
2. **`analyze.py` runs inside the sandbox** — reaches only the allowlisted Nemotron endpoint
   (`host.openshell.internal:1234`), reasons over lecture frames, and produces a real widget spec
   (proven: *"Scrambled Egg Cooking Time Calculator"*). Results flow back to the host to persist in Supabase.
3. **Exfil stays blocked while it works** — a POST of the widgets it just made → denied + OCSF-logged.
4. **Durable** — snapshotted as `8kedu-contained` (survives restart).

**Key fix that unblocked this:** `host.openshell.internal` resolves to `0.250.250.254` inside the sandbox —
outside the standard private ranges, so the SSRF guard 403'd the model until `0.250.250.0/24` was added to
the policy's `allowed_ips`.

**Honest limitation:** the *video download* (yt-dlp) stays host-side — YouTube's media is served from
rotating `*.googlevideo.com` subdomains that per-host egress can't practically allowlist. The contained
piece is the reasoning (the part that handles untrusted content and could leak).

Persistence (Supabase two-tier schema — global cache + per-user state) is applied to the
live DB and accessed via [`agent/db.py`](../agent/db.py).

## Run it
```bash
export DOCKER_HOST="unix:///Users/azehady/.orbstack/run/docker.sock"   # OrbStack socket

# 1. apply the policy (already applied as policy version 4)
nemoclaw scoutclaw policy-add 8kedu --from-file claw-agent/policies/8kedu.yaml --yes

# 2. prove containment
bash claw-agent/contain_demo.sh

# 3. lock config for a sensitive run
nemoclaw scoutclaw shields up
```

## What the demo shows (verified)
```
FIND_VIDEO  → youtube    [allowed]         → HTTP 200            ✅
PERSIST     → supabase   [allowed]         → HTTP 401 (reached)  ✅
EXFIL       → attacker   [must be blocked] → BLOCKED (URLError)  ✅
CONTAINED — capable agent, zero unauthorized egress.
```
The denial in the OCSF audit log:
```
NET:OPEN [MED] DENIED /usr/bin/curl -> webhook.site:443
  [policy:- engine:opa] [reason:endpoint webhook.site:443 is not allowed by any policy]
Flushed activity summary ... denied_action_count=1
```

## How it works
OpenShell runs the sandbox with an L4/L7 egress proxy in front of every process. The
`8kedu` preset declares `network_policies` keyed by sink (youtube/apify/supabase/
local_inference), each with allowed hosts, ports, and REST method+path rules. Any
connection to a host not in a policy is denied by the OPA engine before it leaves the
sandbox — regardless of which binary or code path attempts it. Postgres pooler ports
(5432/6543) are opened as raw `access: full` TCP; the local model is reached via
`host.openshell.internal:1234` with the private-IP allowlist OpenShell's SSRF guard requires.
