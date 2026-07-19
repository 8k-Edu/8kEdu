#!/usr/bin/env bash
# Launch vllm-metal — the OFFICIAL vLLM Metal plugin (upstream vLLM 0.25.1 + an Apple-Silicon
# Metal backend), OpenAI-compatible, for 8kEdu. Alternative to the default Nemotron-Omni-on-vllm-mlx
# path (scripts/serve-vllm.sh) — vllm-metal doesn't support Nemotron-Omni's MoE, so it serves
# Qwen3-VL-4B (vision) + DeepSeek-R1-Distill-Qwen-7B (brain).
#
# Install once (lands in ~/.venv-vllm-metal, native arm64 Python 3.12; needs Xcode CLT):
#   curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
#
#   ./scripts/serve-vllm-metal.sh          # start (vision blocks until ready; brain loads in bg)
#   ./scripts/serve-vllm-metal.sh --stop   # stop BOTH, cleanly (no orphaned engine cores)
#   ./scripts/serve-vllm-metal.sh --status # health of both ports
#   ./scripts/serve-vllm-metal.sh --watch  # supervisor: restart a server if it dies (Ctrl-C to end)
#
# Then:  KEDU_BACKEND=vllm ./run.sh
#   (.env: VLLM_MODEL=qwen3-vl-4b, VLLM_BASE_URL=:8000/v1, NEMOTRON_MODEL=deepseek-r1-distill-qwen-7b,
#          NEMOTRON_BASE_URL=:8001/v1)
#
# What this buys over vllm-mlx: real PagedAttention (the default paged-varlen Metal kernel) — which
# is load-bearing here (without it the KV cache admits only 1 sequence and the vision workload
# crashes the engine), plus prefix caching, chunked prefill, and upstream vLLM's real scheduler.
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

VENV="${VLLM_METAL_VENV:-$HOME/.venv-vllm-metal}"
VLLM="$VENV/bin/vllm"
LOGDIR="/tmp/8kedu-logs"; mkdir -p "$LOGDIR"

VISION_LOAD="${VLLM_METAL_VISION_PATH:-$HOME/.lmstudio/models/lmstudio-community/Qwen3-VL-4B-Instruct-MLX-4bit}"
[ -d "$VISION_LOAD" ] || VISION_LOAD="mlx-community/Qwen3-VL-4B-Instruct-4bit"
VISION_NAME="${VLLM_MODEL:-qwen3-vl-4b}"
VISION_PORT="${VLLM_PORT:-8000}"

BRAIN_LOAD="${VLLM_METAL_BRAIN_PATH:-mlx-community/DeepSeek-R1-Distill-Qwen-7B-4bit}"
BRAIN_NAME="${NEMOTRON_MODEL:-deepseek-r1-distill-qwen-7b}"
BRAIN_PORT="${BRAIN_VLLM_PORT:-8001}"

# vLLM's memory-profiling run at startup does a dummy forward pass sized by
# max-num-seqs x max-model-len; on a memory-pressured Mac (swap in use) an oversized dummy batch
# thrashes and the bind stalls for minutes. Keep max-model-len modest and give each role only the
# concurrency it needs — vision fans out in the offline sweep (6), the brain is a single-request
# heartbeat (2). Memory fraction: the KV cache fills up to this; both instances must fit ~48 GB.
MAXLEN="${VLLM_MAX_MODEL_LEN:-8192}"
VISION_SEQS="${VLLM_MAX_NUM_SEQS:-6}"
VISION_MEM="${VLLM_METAL_MEM_FRACTION:-0.24}"
BRAIN_SEQS="${VLLM_BRAIN_MAX_NUM_SEQS:-2}"
BRAIN_MEM="${VLLM_METAL_BRAIN_MEM_FRACTION:-0.18}"

# vLLM's V1 engine core handshakes with its API server over a TCPStore. By default it binds the
# machine's LAN IP; a macOS firewall "deny" on python then blocks that connection and startup hangs
# in a ~30-min retry. Pin the handshake to loopback so the firewall never sees it.
export VLLM_HOST_IP=127.0.0.1
export VLLM_METAL_USE_PAGED_ATTENTION=1   # already the Metal default; explicit for clarity

# Serve models by repo-id and huggingface_hub does a hub metadata check at startup EVEN when the
# model is fully cached. On a host with flaky IPv6 to AWS/HF, that check hangs in SYN_SENT for ~10
# min (a socket timeout) before falling back to cache — a fully idle 10-min stall before the port
# binds (the vision model dodges it only because it loads from a LOCAL dir). Force cache-only so
# there's zero network at startup. ensure_cached() below still downloads (online) on first run.
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"

WARM_PX="/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAA//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AfwD/2Q=="

log() { echo "[serve-vllm-metal] $*"; }

# Kill a process and ALL its descendants (children first). A plain `pkill -f 'vllm serve'` misses the
# renamed `VLLM::EngineCore` subprocess, which then orphans and keeps the model resident — starving
# the next start into swap. This walks the tree so the engine core + resource_tracker die too.
_kill_tree() {
  local pid=$1 child
  for child in $(pgrep -P "$pid" 2>/dev/null); do _kill_tree "$child"; done
  kill -TERM "$pid" 2>/dev/null || true
}

_pids_on_port() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null; }

# First run only: a repo-id model isn't cached yet, so fetch it ONCE with the network on (offline is
# forced off just here). Cached runs return immediately — no network, so no startup hub-check hang.
ensure_cached() {  # <repo-id-or-local-path>
  local m=$1
  case "$m" in /*|"~"*|.*) return 0 ;; esac                       # local path → nothing to fetch
  [ -d "$HOME/.cache/huggingface/hub/models--${m//\//--}" ] && return 0   # already cached
  log "first run: downloading $m (network on, one time)…"
  HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 "$VENV/bin/python" - "$m" <<'PY' || { log "download failed: $m"; return 1; }
import sys
from huggingface_hub import snapshot_download
snapshot_download(sys.argv[1])
PY
}

# Stop whatever serves <port>: the listener's whole tree, plus a still-loading server not yet bound
# (matched by its --port in the cmdline). Leaves other ports untouched.
stop_port() {
  local port=$1 pid
  for pid in $(_pids_on_port "$port"); do _kill_tree "$pid"; done
  for pid in $(pgrep -f "bin/vllm serve.*--port $port( |\$)" 2>/dev/null); do _kill_tree "$pid"; done
  sleep 1
  for pid in $(_pids_on_port "$port"); do kill -KILL "$pid" 2>/dev/null || true; done
}

stop_all() {
  # kill any running watchdog first, or it would immediately resurrect the servers we're stopping
  pkill -f "serve-vllm-metal.sh.*watch" 2>/dev/null || true
  stop_port "$VISION_PORT"; stop_port "$BRAIN_PORT"
  sleep 1
  # belt & suspenders — stop_all takes EVERYTHING down, so sweep any survivors from this venv:
  # the api server, the renamed engine core, and its resource_tracker stub (else they linger).
  pkill -f "$VENV/bin/vllm serve" 2>/dev/null || true
  pkill -f "VLLM::EngineCore" 2>/dev/null || true
  pkill -f "$VENV/bin/python.*resource_tracker" 2>/dev/null || true
}

# Block until <port> answers /v1/models, OR its process died (crash), OR timeout. 0=ready, 1=crash/timeout.
wait_ready() {
  local port=$1 pidfile=$2 label=$3 deadline=$(( SECONDS + ${4:-900} ))
  while (( SECONDS < deadline )); do
    curl -s -m 3 "http://127.0.0.1:$port/v1/models" 2>/dev/null | grep -q '"object"' && return 0
    if [ -f "$pidfile" ] && ! kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      log "$label process exited before binding :$port — see $LOGDIR/vllm-metal-$label.log"; return 1
    fi
    sleep 3
  done
  log "$label did not bind :$port within ${4:-900}s (host may be memory-bound; check --status)"; return 1
}

start_vision() {
  log "vision : $VISION_NAME ($VISION_LOAD) on :$VISION_PORT  [seqs=$VISION_SEQS mem=$VISION_MEM]"
  "$VLLM" serve "$VISION_LOAD" --served-model-name "$VISION_NAME" \
    --host 127.0.0.1 --port "$VISION_PORT" \
    --max-model-len "$MAXLEN" --limit-mm-per-prompt '{"image": 2}' \
    --enable-prefix-caching --max-num-seqs "$VISION_SEQS" --gpu-memory-utilization "$VISION_MEM" \
    > "$LOGDIR/vllm-metal-vision.log" 2>&1 &
  echo $! > "$LOGDIR/vllm-metal-vision.pid"
}

start_brain() {
  log "brain  : $BRAIN_NAME ($BRAIN_LOAD) on :$BRAIN_PORT  [seqs=$BRAIN_SEQS mem=$BRAIN_MEM]"
  "$VLLM" serve "$BRAIN_LOAD" --served-model-name "$BRAIN_NAME" \
    --host 127.0.0.1 --port "$BRAIN_PORT" \
    --max-model-len "$MAXLEN" --max-num-seqs "$BRAIN_SEQS" --gpu-memory-utilization "$BRAIN_MEM" \
    --no-async-scheduling --reasoning-parser deepseek_r1 \
    > "$LOGDIR/vllm-metal-brain.log" 2>&1 &
  echo $! > "$LOGDIR/vllm-metal-brain.pid"
}

warm() {  # <port> <served-model-name> <is_vision:1|0> — best-effort kernel warmup once bound
  if [ "$3" = "1" ]; then
    curl -s -m 180 -o /dev/null -X POST "http://localhost:$1/v1/chat/completions" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/jpeg;base64,$WARM_PX\"}},{\"type\":\"text\",\"text\":\"hi\"}]}],\"max_tokens\":1}" || true
  else
    curl -s -m 180 -o /dev/null -X POST "http://localhost:$1/v1/chat/completions" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":1}" || true
  fi
}

port_ok() { curl -s -m 3 "http://127.0.0.1:$1/v1/models" 2>/dev/null | grep -q '"object"'; }

do_status() {
  local mem; mem=$(vm_stat 2>/dev/null | awk '/Swapouts/{so=$2} END{print ""}')
  for pair in "$VISION_PORT:vision" "$BRAIN_PORT:brain"; do
    local port=${pair%%:*} name=${pair##*:}
    if port_ok "$port"; then echo "  :$port $name  UP   ($(curl -s -m3 http://127.0.0.1:$port/v1/models | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"][0]["id"])' 2>/dev/null))"
    else echo "  :$port $name  DOWN (loading or dead — tail $LOGDIR/vllm-metal-$name.log)"; fi
  done
  echo "  swap in use: $(sysctl -n vm.swapusage 2>/dev/null | grep -oE 'used = [0-9.]+M' | head -1)"
}

# Supervisor: restart a server if its port stops answering. The model load is slow on a
# memory-pressured host, so give a fresh start a long grace period before declaring it dead again.
do_watch() {
  log "watchdog: monitoring :$VISION_PORT and :$BRAIN_PORT every 20s (Ctrl-C to stop)"
  local grace_v=0 grace_b=0
  while true; do
    if port_ok "$VISION_PORT"; then grace_v=0; elif (( grace_v <= 0 )); then
      log "vision :$VISION_PORT down — restarting"; stop_port "$VISION_PORT"; start_vision; grace_v=60
    else grace_v=$((grace_v-1)); fi
    if port_ok "$BRAIN_PORT"; then grace_b=0; elif (( grace_b <= 0 )); then
      log "brain :$BRAIN_PORT down — restarting"; stop_port "$BRAIN_PORT"; start_brain; grace_b=60
    else grace_b=$((grace_b-1)); fi
    sleep 20
  done
}

case "${1:-start}" in
  --stop|stop)   stop_all; log "stopped vllm-metal (both servers + engine cores)."; exit 0 ;;
  --status|status) do_status; exit 0 ;;
  --watch|watch) do_watch; exit 0 ;;
esac

# start (default): clean slate first so restarts never accumulate orphaned engine cores.
stop_all
avail=$(vm_stat 2>/dev/null | awk '/Pages free/{f=$3} /speculative/{s=$3} END{printf "%.0f", (f+s)*16384/1024/1024/1024}')
log "starting (free≈${avail}GB). vision blocks until ready; brain loads in the background."
ensure_cached "$VISION_LOAD" || log "vision model not cached & download failed — serving may fail"
ensure_cached "$BRAIN_LOAD"  || log "brain model not cached & download failed — serving may fail"

# Vision first and fully up (it's the hot path) — this also gets its Metal kernels compiled before
# the brain starts, so the two don't thrash kernel compilation against each other.
start_vision
if wait_ready "$VISION_PORT" "$LOGDIR/vllm-metal-vision.pid" vision 900; then
  warm "$VISION_PORT" "$VISION_NAME" 1; log "vision ready on :$VISION_PORT ✓"
else
  log "vision failed to come up — aborting"; exit 1
fi

# Brain in the background: it's a periodic reasoning heartbeat, not the hot path, and its load can be
# slow on a swap-pressured host. Don't block the shell on it — the watchdog / the agent's own retries
# bring it up. Check with: ./scripts/serve-vllm-metal.sh --status
start_brain
( wait_ready "$BRAIN_PORT" "$LOGDIR/vllm-metal-brain.pid" brain 1200 && warm "$BRAIN_PORT" "$BRAIN_NAME" 0 && log "brain ready on :$BRAIN_PORT ✓" ) &

log "vision live now; brain warming in background. Health: ./scripts/serve-vllm-metal.sh --status"
log "keep both alive across crashes: ./scripts/serve-vllm-metal.sh --watch &"
