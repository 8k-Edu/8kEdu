#!/usr/bin/env bash
# Launch vllm-mlx — the local, Apple-Silicon vLLM (OpenAI-compatible) server(s) for 8kEdu.
# Install once:  uv tool install vllm-mlx   (or: pip install vllm-mlx)   # needs Python 3.10+
#
# Two instances by default: vision on :8000 (VLLM_*), brain on :8001 (NEMOTRON_*).
# To run ONE server for both, point NEMOTRON_BASE_URL at :8000 and skip the brain line
# (set BRAIN_VLLM_PORT= to disable), or give both the same model+port.
#
#   ./scripts/serve-vllm.sh          # start
#   ./scripts/serve-vllm.sh --stop   # stop
#
# Then bring up the app against vLLM:
#   TACTILE_BACKEND=vllm ./run.sh
#   (and set NEMOTRON_BASE_URL=http://localhost:8001/v1 in .env for the brain)
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

if [ "${1:-}" = "--stop" ]; then
  pkill -f "vllm-mlx serve" 2>/dev/null
  echo "stopped vllm-mlx."
  exit 0
fi

VISION_MODEL="${VLLM_MODEL:-mlx-community/Qwen2.5-VL-7B-Instruct-4bit}"
VISION_PORT="${VLLM_PORT:-8000}"
# Brain instance model. NOTE: NEMOTRON_MODEL in .env is the identifier the brain CLIENT sends
# (an LM Studio name like nvidia/nemotron-3-nano), NOT necessarily an MLX repo — so serve
# VLLM_BRAIN_MODEL here (an mlx-community repo), defaulting to the vision model so first run
# works. To actually route the brain to this instance, also set (in .env):
#   NEMOTRON_BASE_URL=http://localhost:8001/v1   and   NEMOTRON_MODEL=<this same served repo>
BRAIN_MODEL="${VLLM_BRAIN_MODEL:-$VISION_MODEL}"
BRAIN_PORT="${BRAIN_VLLM_PORT:-8001}"
# Server-side request timeout (s). Backstop pairing with analyze.py's client-side TACTILE_TIMEOUT:
# vllm-mlx keeps generating for a client that has gone away, so without a cap slow requests pile
# up and cascade to 100s+ under load. Cancel them instead.
REQ_TIMEOUT="${VLLM_TIMEOUT:-180}"

LOGDIR="/tmp/8kedu-logs"; mkdir -p "$LOGDIR"

# 1x1 JPEG — a warmup ping over the multimodal path so the FIRST real request doesn't eat MLX
# Metal kernel compilation (a cold first inference can otherwise blow past the client timeout).
WARM_PX="/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAA//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AfwD/2Q=="

warm() {  # <port> <served-model-name> <is_vision:1|0>
  curl -s --retry 90 --retry-connrefused --retry-delay 2 "http://localhost:$1/v1/models" >/dev/null || return
  if [ "$3" = "1" ]; then
    curl -s -m 180 -o /dev/null -X POST "http://localhost:$1/v1/chat/completions" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/jpeg;base64,$WARM_PX\"}},{\"type\":\"text\",\"text\":\"hi\"}]}],\"max_tokens\":1}"
  else
    curl -s -m 180 -o /dev/null -X POST "http://localhost:$1/v1/chat/completions" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$2\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":1}"
  fi
  echo "  warmed :$1"
}

echo "→ vllm-mlx vision : $VISION_MODEL on :$VISION_PORT"
# --mllm forces multimodal (vision) load — the vision role always sends images.
vllm-mlx serve "$VISION_MODEL" --port "$VISION_PORT" --continuous-batching --mllm --timeout "$REQ_TIMEOUT" \
  > "$LOGDIR/vllm-vision.log" 2>&1 &

if [ -n "$BRAIN_PORT" ]; then
  echo "→ vllm-mlx brain  : $BRAIN_MODEL on :$BRAIN_PORT"
  vllm-mlx serve "$BRAIN_MODEL" --port "$BRAIN_PORT" --continuous-batching --timeout "$REQ_TIMEOUT" \
    > "$LOGDIR/vllm-brain.log" 2>&1 &
fi

echo "vllm-mlx loading (first run downloads the model). warming up…"
warm "$VISION_PORT" "$VISION_MODEL" 1
[ -n "$BRAIN_PORT" ] && warm "$BRAIN_PORT" "$BRAIN_MODEL" 0
echo "ready. logs in $LOGDIR/ — health: curl -s localhost:$VISION_PORT/v1/models"
