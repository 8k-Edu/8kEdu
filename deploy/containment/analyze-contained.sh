#!/usr/bin/env bash
# Run ONE video's analyze (reasoning) step inside the egress-allowlisted sandbox.
# Called by serve.py when KEDU_CONTAINED=1, once the host-side download has produced
# data/<id>/frames.  Idempotently ensures the images, networks, and a long-lived
# gateway exist (the gateway is shared across drops and auto-restarts), then runs the
# contained analyze. concepts.json flows back to the mounted volume for the host to
# persist — the reasoner reaches only openrouter.ai:443, everything else is denied+logged.
#
# Usage: analyze-contained.sh VIDEO_ID [LIMIT]
set -euo pipefail
cd "$(dirname "$0")/../.."

VID="${1:?usage: analyze-contained.sh VIDEO_ID [LIMIT]}"
LIMIT="${2:-12}"
SB=kedu-analyze-sandbox; GW_IMG=kedu-egress-gw; GW=kedu-gw
NET_INT=kedu-internal; NET_EXT=kedu-egress

KEY="${OPENROUTER_API_KEY:-$(grep -E '^OPENROUTER_API_KEY=' .env | cut -d= -f2- || true)}"
MODEL="${OPENROUTER_MODEL:-$(grep -E '^OPENROUTER_MODEL=' .env | cut -d= -f2- || true)}"; MODEL="${MODEL:-google/gemini-2.5-flash}"
[ -n "${KEY:-}" ] || { echo "analyze-contained: no OPENROUTER_API_KEY" >&2; exit 1; }

# images (built once; fast no-op if present)
docker image inspect "$SB"     >/dev/null 2>&1 || docker build -q -f deploy/containment/Dockerfile.analyze -t "$SB" .     >/dev/null
docker image inspect "$GW_IMG" >/dev/null 2>&1 || docker build -q -f deploy/containment/Dockerfile.egress  -t "$GW_IMG" . >/dev/null

# networks: internal (no internet) + egress (internet, gateway only)
docker network create --internal "$NET_INT" >/dev/null 2>&1 || true
docker network create "$NET_EXT"            >/dev/null 2>&1 || true

# long-lived, auto-restarting gateway shared across drops
if ! docker ps --format '{{.Names}}' | grep -qx "$GW"; then
  docker rm -f "$GW" >/dev/null 2>&1 || true
  docker run -d --restart unless-stopped --name "$GW" --network "$NET_INT" "$GW_IMG" >/dev/null
  docker network connect "$NET_EXT" "$GW" 2>/dev/null || true
  sleep 2
fi

# the contained reasoning run — only OPENROUTER_API_KEY crosses in, egress via gateway only
exec docker run --rm --network "$NET_INT" \
  -e HTTPS_PROXY="http://$GW:3128" -e https_proxy="http://$GW:3128" \
  -e HTTP_PROXY="http://$GW:3128"  -e http_proxy="http://$GW:3128" \
  -e KEDU_ALLOW_CLOUD=1 -e OPENROUTER_API_KEY="$KEY" -e OPENROUTER_MODEL="$MODEL" \
  -v "$PWD/data/$VID:/sandbox/data/$VID" \
  "$SB" --backend openrouter --data /sandbox/data --video "$VID" --limit "$LIMIT"
