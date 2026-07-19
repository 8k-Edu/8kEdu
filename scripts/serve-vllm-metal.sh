#!/usr/bin/env bash
# Launch vllm-metal — the OFFICIAL vLLM Metal plugin (upstream vLLM 0.25.1 + an Apple-Silicon
# Metal backend), OpenAI-compatible, for 8kEdu. This is the native path; scripts/serve-vllm.sh
# (the third-party vllm-mlx port) stays alongside it — pick one, they both expose :8000/:8001.
#
# Install once (lands in ~/.venv-vllm-metal, native arm64 Python 3.12; needs Xcode CLT):
#   curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
#
# Two instances: vision on :8000 (Qwen3-VL-4B, VLLM_*), brain on :8001 (DeepSeek-R1, NEMOTRON_*).
#
#   ./scripts/serve-vllm-metal.sh          # start (serial: vision, then brain)
#   ./scripts/serve-vllm-metal.sh --stop   # stop
#
# Then bring up the app against it:
#   KEDU_BACKEND=vllm ./run.sh
#   (.env: VLLM_BASE_URL=http://localhost:8000/v1, NEMOTRON_BASE_URL=http://localhost:8001/v1)
#
# What this buys over vllm-mlx: real PagedAttention (the default paged-varlen Metal kernel),
# prefix caching, chunked prefill, and upstream vLLM's scheduler/continuous batching — not an
# MLX reimplementation.
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

VENV="${VLLM_METAL_VENV:-$HOME/.venv-vllm-metal}"
VLLM="$VENV/bin/vllm"

if [ "${1:-}" = "--stop" ]; then
  pkill -f "$VENV/bin/vllm serve" 2>/dev/null
  echo "stopped vllm-metal."
  exit 0
fi

[ -x "$VLLM" ] || { echo "vllm-metal not found at $VLLM — install it first (see header)"; exit 1; }

# Vision: an already-downloaded local MLX dir (no re-download). Falls back to the portable HF repo
# if that dir is absent. VLLM_MODEL is the id the CLIENT sends, so it doubles as --served-model-name.
VISION_LOAD="${VLLM_METAL_VISION_PATH:-$HOME/.lmstudio/models/lmstudio-community/Qwen3-VL-4B-Instruct-MLX-4bit}"
[ -d "$VISION_LOAD" ] || VISION_LOAD="mlx-community/Qwen3-VL-4B-Instruct-4bit"
VISION_NAME="${VLLM_MODEL:-qwen3-vl-4b}"
VISION_PORT="${VLLM_PORT:-8000}"

# Brain: DeepSeek-R1-Distill-Qwen-7B — a vllm-metal-supported reasoning model, replacing Nemotron
# (whose 30B-A3B MoE arch vllm-metal doesn't serve). --reasoning-parser routes the <think> trace to
# reasoning_content, leaving OpenAI `content` clean (agent/brain.py keeps content, drops reasoning).
BRAIN_LOAD="${VLLM_METAL_BRAIN_PATH:-mlx-community/DeepSeek-R1-Distill-Qwen-7B-4bit}"
BRAIN_NAME="${NEMOTRON_MODEL:-deepseek-r1-distill-qwen-7b}"
BRAIN_PORT="${BRAIN_VLLM_PORT:-8001}"

# Memory sizing for TWO coexisting instances on one Mac. The dominant cost is the KV cache, whose
# size scales with max-model-len × max-num-seqs, so we keep max-model-len small (the widget/brain
# prompts are ~2.4k / ~4.5k tokens — 8192 is ample) and the memory fraction modest. Picked
# empirically: with these values `vm.swapusage used` stays flat during inference; raising
# max-model-len to 32768 at 0.35 each oversubscribes 48 GB and thrashes swap (everything 3-5x slower).
MEM="${VLLM_METAL_MEM_FRACTION:-0.24}"
MAXSEQ="${VLLM_MAX_NUM_SEQS:-6}"
MAXLEN="${VLLM_MAX_MODEL_LEN:-8192}"

# vLLM's V1 engine core handshakes with its API server over a TCPStore. By default it binds the
# machine's LAN IP; a macOS firewall "deny" on python then blocks that loopback-over-LAN connection
# and startup hangs in a 30-min retry. Pin the handshake to loopback so the firewall never sees it.
export VLLM_HOST_IP=127.0.0.1
export VLLM_METAL_USE_PAGED_ATTENTION=1   # already the Metal default; set explicitly for clarity

LOGDIR="/tmp/8kedu-logs"; mkdir -p "$LOGDIR"

# 1x1 JPEG — a warmup ping over the multimodal path so the FIRST real request doesn't eat Metal
# kernel compilation (a cold first inference can otherwise blow past the client timeout).
WARM_PX="/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAA//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AfwD/2Q=="

warm() {  # <port> <served-model-name> <is_vision:1|0> — blocks until the model is up, then pings it
  curl -s --retry 240 --retry-connrefused --retry-delay 3 "http://localhost:$1/v1/models" >/dev/null || return
  if [ "$3" = "1" ]; then
    curl -s -m 180 -o /dev/null -X POST "http://localhost:$1/v1/chat/completions" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/jpeg;base64,$WARM_PX\"}},{\"type\":\"text\",\"text\":\"hi\"}]}],\"max_tokens\":1}"
  else
    curl -s -m 180 -o /dev/null -X POST "http://localhost:$1/v1/chat/completions" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":1}"
  fi
  echo "  warmed :$1"
}

# Start serially — vision fully up before the brain — so the two don't thrash Metal kernel
# compilation against each other (concurrent cold starts stall for many minutes).
echo "→ vllm-metal vision : $VISION_NAME  ($VISION_LOAD) on :$VISION_PORT"
"$VLLM" serve "$VISION_LOAD" --served-model-name "$VISION_NAME" \
  --host 127.0.0.1 --port "$VISION_PORT" \
  --max-model-len "$MAXLEN" --limit-mm-per-prompt '{"image": 2}' \
  --enable-prefix-caching --max-num-seqs "$MAXSEQ" --gpu-memory-utilization "$MEM" \
  > "$LOGDIR/vllm-metal-vision.log" 2>&1 &
warm "$VISION_PORT" "$VISION_NAME" 1

if [ -n "$BRAIN_PORT" ]; then
  echo "→ vllm-metal brain  : $BRAIN_NAME  ($BRAIN_LOAD) on :$BRAIN_PORT"
  "$VLLM" serve "$BRAIN_LOAD" --served-model-name "$BRAIN_NAME" \
    --host 127.0.0.1 --port "$BRAIN_PORT" \
    --max-model-len "$MAXLEN" --max-num-seqs "$MAXSEQ" --gpu-memory-utilization "$MEM" \
    --reasoning-parser deepseek_r1 \
    > "$LOGDIR/vllm-metal-brain.log" 2>&1 &
  warm "$BRAIN_PORT" "$BRAIN_NAME" 0
fi

echo "ready. logs in $LOGDIR/vllm-metal-*.log — health: curl -s localhost:$VISION_PORT/v1/models"
