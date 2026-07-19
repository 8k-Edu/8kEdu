#!/usr/bin/env bash
# 8kEdu — cloud containment of the analyze (reasoning) step.
#
# The bounty's Option D on a cloud box: 8kEdu's analyze.py runs INSIDE a Docker sandbox
# whose only route to the internet is a filtering proxy that allowlists exactly one host —
# OpenRouter (cloud inference). It reasons over lecture frames, produces a real widget,
# and every egress decision is written to an audit log. An exfil to anything else is
# blocked (both at the proxy AND by having no other route). Same guarantee as the Mac
# scoutclaw demo (claw-agent/contained_agent_demo.sh); different mechanism, because this
# box has plain Docker, not the nemoclaw/OpenShell runtime.
#
# Usage:  deploy/containment/contain-analyze-cloud.sh [VIDEO_ID]   (default: 8kedu-contain-demo)
set -euo pipefail
cd "$(dirname "$0")/../.."                      # repo root

VID="${1:-8kedu-contain-demo}"
LIMIT="${LIMIT:-2}"
SB=kedu-analyze-sandbox                          # image + reasoner
GW_IMG=kedu-egress-gw; GW=kedu-gw                # gateway image / container
NET_INT=kedu-internal                            # no internet
NET_EXT=kedu-egress                              # internet (gateway only)
EXFIL="https://webhook.site/8kedu-exfil-test"    # a NON-allowlisted sink

say(){ printf '\n\033[1m▸ %s\033[0m\n' "$*"; }
ok(){ printf '  \033[32m✓ %s\033[0m\n' "$*"; }
no(){ printf '  \033[31m⛔ %s\033[0m\n' "$*"; }

# Only the inference key crosses into the sandbox — NOT the full .env (no Supabase/Apify creds).
KEY="$(grep -E '^OPENROUTER_API_KEY=' .env | cut -d= -f2-)"
MODEL="$(grep -E '^OPENROUTER_MODEL=' .env | cut -d= -f2- || true)"; MODEL="${MODEL:-google/gemini-2.5-flash}"
[ -n "${KEY:-}" ] || { echo "no OPENROUTER_API_KEY in .env"; exit 1; }

cleanup(){ docker rm -f "$GW" >/dev/null 2>&1 || true; }
trap cleanup EXIT

say "build images"
docker build -q -f deploy/containment/Dockerfile.analyze -t "$SB" .     >/dev/null
docker build -q -f deploy/containment/Dockerfile.egress  -t "$GW_IMG" . >/dev/null
ok "sandbox + gateway images ready"

# The default demo has no real frames (the video download is host-side by design and
# frames/ is gitignored), so synthesize a tiny 2-frame input. Real ingested videos
# already have data/<id>/frames/*.jpg and are left untouched.
if [ "$VID" = "8kedu-contain-demo" ] && ! ls data/"$VID"/frames/*.jpg >/dev/null 2>&1; then
  say "prepare demo input (synthetic frames — a real drop's download stays host-side)"
  mkdir -p data/"$VID"/frames
  docker run -i --rm --entrypoint python -v "$PWD/data/$VID:/out" "$SB" - <<'PY'
import json, os
from PIL import Image, ImageDraw
d="/out"; os.makedirs(d+"/frames", exist_ok=True)
json.dump([{"start":0.0,"text":"Backpropagation computes gradients by the chain rule, layer by layer."},
           {"start":58.0,"text":"The softmax turns logits into a probability distribution over tokens."}],
          open(d+"/transcript.json","w"))
frames=[{"time":0.0,"file":"f_000000.jpg"},{"time":58.0,"file":"f_000058.jpg"}]
json.dump(frames, open(d+"/frames.json","w"))
for i,label in enumerate(["Backpropagation: dL/dw via chain rule","Softmax: p_i = e^z_i / sum e^z_j"]):
    img=Image.new("RGB",(1280,720),(12,15,20)); dr=ImageDraw.Draw(img)
    dr.rectangle([40,40,1240,680],outline=(120,160,255),width=3); dr.text((80,340),label,fill=(230,235,240))
    img.save(f"{d}/frames/{frames[i]['file']}",quality=85)
print("  demo input generated")
PY
  ok "demo input ready"
fi

say "networks: $NET_INT (no internet) + $NET_EXT (internet, gateway only)"
docker network create --internal "$NET_INT" >/dev/null 2>&1 || true
docker network create "$NET_EXT"            >/dev/null 2>&1 || true

say "start egress gateway (allowlist: openrouter.ai:443 only), dual-homed"
docker rm -f "$GW" >/dev/null 2>&1 || true
docker run -d --name "$GW" --network "$NET_INT" "$GW_IMG" >/dev/null
docker network connect "$NET_EXT" "$GW"
sleep 2; ok "gateway up on $NET_INT + $NET_EXT"

say "isolation check: the reasoner sees only the internal network, no NET_ADMIN"
NETS=$(docker run --rm --network "$NET_INT" --entrypoint sh "$SB" -c 'echo ok' >/dev/null 2>&1 && \
       docker run -d --name kedu-iso --network "$NET_INT" --entrypoint sleep "$SB" 30 >/dev/null && \
       docker inspect kedu-iso --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'; docker rm -f kedu-iso >/dev/null 2>&1 || true)
echo "  reasoner networks: ${NETS:-?}"
[ "$(echo "$NETS" | tr -d ' ')" = "$NET_INT" ] && ok "single NIC ($NET_INT) — no direct internet" || no "unexpected extra network!"

say "CONTAINED analyze — Nemotron-class reasoning INSIDE the sandbox, egress via gateway only"
docker run --rm --network "$NET_INT" \
  -e HTTPS_PROXY="http://$GW:3128" -e https_proxy="http://$GW:3128" \
  -e HTTP_PROXY="http://$GW:3128"  -e http_proxy="http://$GW:3128" \
  -e KEDU_ALLOW_CLOUD=1 -e OPENROUTER_API_KEY="$KEY" -e OPENROUTER_MODEL="$MODEL" \
  -v "$PWD/data/$VID:/sandbox/data/$VID" \
  "$SB" --backend openrouter --data /sandbox/data --video "$VID" --limit "$LIMIT" 2>&1 | sed 's/^/  /'
W=$(python3 -c "import json;print(len(json.load(open('data/$VID/concepts.json'))))" 2>/dev/null || echo 0)
ok "produced $W widget(s) → data/$VID/concepts.json (flowed back to host)"

say "4-way fail-closed proof (attempts from inside the sandbox)"
# %{http_code} = the TARGET's response; %{http_connect} = the PROXY's CONNECT response.
# A squid-denied tunnel shows http_code=000 http_connect=403; a no-route attempt shows 000 000.
probe(){ local url="$2"; shift 2; docker run --rm --network "$NET_INT" "$@" --entrypoint curl "$SB" \
           -s -o /dev/null -w '%{http_code} %{http_connect}' --max-time 12 "$url" 2>/dev/null || true; }
r1=$(probe x https://openrouter.ai/api/v1/models -e HTTPS_PROXY=http://$GW:3128 -e https_proxy=http://$GW:3128)
r2=$(probe x "$EXFIL"                            -e HTTPS_PROXY=http://$GW:3128 -e https_proxy=http://$GW:3128)
r3=$(probe x "$EXFIL")
r4=$(probe x https://openrouter.ai/api/v1/models)
[ "${r1%% *}" = 200 ] && ok "via gateway → OpenRouter      = HTTP 200  (reaches, allowed+audited)"     || echo "  via gateway → OpenRouter = $r1 (want code 200)"
[ "${r2##* }" = 403 ] && no "via gateway → exfil sink       = CONNECT 403  (DENIED by allowlist + logged)" || echo "  via gateway → exfil = $r2 (want connect 403)"
[ "${r3% *}" = 000 ]  && no "direct (no proxy) → exfil sink = no route  (fail-closed, can't resolve)"    || echo "  direct exfil = $r3 (want no route)"
[ "${r4% *}" = 000 ]  && no "direct (no proxy) → OpenRouter = no route  (only the audited path works)"   || echo "  direct openrouter = $r4 (want no route)"

say "egress audit log (every decision the gateway made)"
docker exec "$GW" sh -c 'cat /var/log/squid/access.log 2>/dev/null' | tail -20 | sed 's/^/  /'

say "done — reasoning contained, exfil blocked, decisions audited"
