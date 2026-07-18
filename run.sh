#!/usr/bin/env bash
# 8kEdu — bring up the whole stack for the demo.
#   ./run.sh              # serve + agent-api + frontend
#   ./run.sh --loop       # also start the autonomous heartbeat (every 60s)
# Stop everything:  ./run.sh --stop
set -uo pipefail
cd "$(dirname "$0")"
export DOCKER_HOST="${DOCKER_HOST:-unix:///Users/azehady/.orbstack/run/docker.sock}"
export TACTILE_MODEL="${TACTILE_MODEL:-nvidia/nemotron-3-nano-omni}"
LOGDIR="/tmp/8kedu-logs"; mkdir -p "$LOGDIR"

stop() {
  echo "stopping 8kEdu services…"
  pkill -f "serve.py" 2>/dev/null
  pkill -f "agent.api" 2>/dev/null
  pkill -f "agent/loop.py" 2>/dev/null
  pkill -f "vite" 2>/dev/null
  echo "stopped."
}
[ "${1:-}" = "--stop" ] && { stop; exit 0; }

stop; sleep 1
echo "→ ask backend (Nemotron via LM Studio) on :8756"
uv run serve.py --backend lmstudio --port 8756 > "$LOGDIR/serve.log" 2>&1 &

echo "→ agent dashboard API on :8787"
uv run python -m agent.api --port 8787 > "$LOGDIR/agent_api.log" 2>&1 &

echo "→ frontend (vite) — dev.localhost:5174 on dev branch, localhost:5173 on main"
( cd app && npm run dev > "$LOGDIR/vite.log" 2>&1 & )

if [ "${1:-}" = "--loop" ]; then
  echo "→ autonomous heartbeat (60s interval)"
  uv run agent/loop.py --interval 60 > "$LOGDIR/loop.log" 2>&1 &
fi

sleep 6
echo
echo "8kEdu up. logs in $LOGDIR/"
echo "  app        → http://dev.localhost:5174/   (or http://localhost:5173/)"
echo "  agent live → /?view=agent      learn → /?view=learn      community → /?view=community"
echo "  containment demo →  bash claw-agent/contain_demo.sh"
echo "  stop everything  →  ./run.sh --stop"
