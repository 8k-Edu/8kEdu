#!/usr/bin/env bash
# Pre-demo preflight — run right before recording. Green across the board = go.
cd "$(dirname "$0")/.."
G='\033[32m✓\033[0m'; R='\033[31m✗\033[0m'
ok() { printf "  $G %s\n" "$1"; }
bad() { printf "  $R %s\n" "$1"; FAIL=1; }
chk() { # chk <name> <url> [grep]
  local body; body=$(curl -s -m 6 "$2" 2>/dev/null)
  if [ -n "$3" ]; then echo "$body" | grep -q "$3" && ok "$1" || bad "$1  ($2)"
  else [ -n "$body" ] && ok "$1" || bad "$1  ($2)"; fi
}

echo "── services"
chk "vLLM model :8000"        "http://localhost:8000/v1/models"        "Nemotron"
chk "widget API :8756"        "http://127.0.0.1:8756/api/info"         '"backend"'
chk "agent API :8787"         "http://127.0.0.1:8787/pub/config"       '"anon_key"'
chk "frontend :5174"          "http://localhost:5174/"                 "8kEdu"

echo "── data through the frontend proxy"
chk "karpathy widgets"        "http://localhost:5174/kCc8FmEb1nY/concepts.json"  '"widget"'
chk "community feed"          "http://localhost:5174/pub/feed?sort=hot"          '"items"'
chk "agent state"             "http://localhost:5174/agent/state"                '"ok"'
chk "recursive graph"         "http://localhost:5174/agent/graph?topic=ai_stem"  '"nodes"'
chk "billing (credits)"       "http://localhost:5174/api/billing"                '"credits"'

echo "── cloud path"
# unauthenticated billing correctly reports authenticated:false; cloud unlocks after the
# in-app guest sign-in. This just proves the endpoint + key plumbing are alive.
chk "billing endpoint (auth-gated)"  "http://127.0.0.1:8756/api/billing"  '"authenticated"'
[ -n "$OPENROUTER_API_KEY" ] || grep -q "^OPENROUTER_API_KEY=sk-or" .env 2>/dev/null && ok "OPENROUTER_API_KEY in .env" || bad "OPENROUTER_API_KEY missing from .env"

echo "── heartbeats"
pgrep -f "agent.curator" >/dev/null && ok "curator running" || bad "curator NOT running (nohup uv run python -m agent.curator --interval 600 &)"

[ -z "$FAIL" ] && printf "\n\033[32mALL GREEN — record.\033[0m\n" || printf "\n\033[31mFix the ✗ lines before recording.\033[0m\n"
