# Cloud containment — the analyze step, sandboxed

The Mac/OpenShell demo (`claw-agent/`) contains 8kEdu's reasoning step inside `scoutclaw`
with an egress allowlist. This is the **same guarantee on a cloud box that has no
`nemoclaw`/`scoutclaw` runtime** — built from plain Docker + a filtering proxy.

> **Honest framing (use this exact wording for the hackathon):** on the cloud box we
> enforce the *same egress-allowlist property* — deny-by-default egress + audit — via
> **Docker network isolation + a filtering proxy**, not nemoclaw. Different mechanism,
> same guarantee.

## What it does

`analyze.py` (the step that reasons over *untrusted* lecture frames and could exfiltrate)
runs inside a Docker sandbox that:

1. is attached to a single **`--internal`** network — **no route to the internet**;
2. reaches the outside world **only** through an egress gateway (squid) that allowlists
   **exactly one destination: `openrouter.ai:443`** (cloud inference) and denies everything
   else at L7;
3. holds **only** `OPENROUTER_API_KEY` — not the Supabase/Apify creds (it can't leak
   secrets it never had). Results (`concepts.json`) flow back to a mounted volume; the
   **host** persists to Supabase.

Every egress decision is written to a JSON audit log.

## Run it

```bash
deploy/containment/contain-analyze-cloud.sh            # synthetic 2-frame demo
deploy/containment/contain-analyze-cloud.sh <VIDEO_ID> # a video you ingested host-side
```

## What it proves (the 4-way fail-closed test)

| Attempt (from inside the sandbox) | Result |
|---|---|
| via gateway → `openrouter.ai` | ✅ HTTP 200 — reaches, **allowed + audited** |
| via gateway → any other host | ⛔ CONNECT **403** — denied by allowlist + logged |
| direct (no proxy) → any host | ⛔ **no route** — can't even resolve (fail-closed) |
| direct (no proxy) → `openrouter.ai` | ⛔ **no route** — even the allowed host is only reachable through the audited path |

Sample audit log (`TCP_TUNNEL` = allowed, `TCP_DENIED` = blocked):

```json
{"time":"…","src_ip":"172.18.0.3","dst":"openrouter.ai:443","method":"CONNECT","action":"TCP_TUNNEL","http_status":200}
{"time":"…","src_ip":"172.18.0.3","dst":"webhook.site:443","method":"CONNECT","action":"TCP_DENIED","http_status":403}
```

## Files
| File | What |
|---|---|
| `Dockerfile.analyze` | the contained reasoner — `analyze.py` + `openai`/`pillow` only |
| `Dockerfile.egress` + `squid.conf` | the allowlist gateway (openrouter.ai:443 only) |
| `contain-analyze-cloud.sh` | one command: build → isolate → reason → 4-way proof → audit |

## Limitations (state them — they're a credibility win)
- The **video download** (yt-dlp) stays host-side, exactly as in the Mac demo — YouTube's
  rotating `*.googlevideo.com` CDN can't be practically allowlisted. The contained piece is
  the **reasoning**, which is the part that handles untrusted content.
- This is the **demo/opt-in** path. Wiring it into the live `/api/ingest` endpoint (so every
  browser drop is contained) is a separate step — it adds container cold-start latency and
  should be a deliberate switch, not silent.
