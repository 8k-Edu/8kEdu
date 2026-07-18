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
| [`policies/8kedu.yaml`](policies/8kedu.yaml) | Egress policy preset — YouTube, Apify, Supabase, local inference. Nothing else. |
| [`agent_egress_probe.py`](agent_egress_probe.py) | The agent's own urllib egress pattern + a rogue exfil. Run inside the sandbox. |
| [`contain_demo.sh`](contain_demo.sh) | One-command demo: allowed sinks succeed, exfil blocked + logged. |

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
