#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

FAIL=0
VISION_BASE="${VLLM_BASE_URL:-http://localhost:8000/v1}"
BRAIN_BASE="${NEMOTRON_BASE_URL:-http://localhost:8001/v1}"
VISION_MODEL="${VLLM_MODEL:-qwen3-vl-4b}"
BRAIN_MODEL="${NEMOTRON_MODEL:-deepseek-r1-distill-qwen-7b}"
FRONTEND="${KEDU_DEMO_FRONTEND:-http://localhost:5173}"

pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=1; }

check_match() {
  local label="$1" url="$2" expected="$3" body
  if ! body=$(curl -fsS --max-time 8 "$url" 2>/dev/null); then
    fail "$label ($url)"
  elif [[ "$body" == *"$expected"* ]]; then
    pass "$label"
  else
    fail "$label (expected $expected)"
  fi
}

check_engines() {
  local body
  if ! body=$(curl -fsS --max-time 8 "$FRONTEND/agent/vllm_metrics" 2>/dev/null); then
    fail "vLLM engine metrics ($FRONTEND/agent/vllm_metrics)"
  elif printf '%s' "$body" | python3 -c 'import json,sys; d=json.load(sys.stdin); e=d.get("engines", {}); assert d.get("ok") and e.get("vision") and e.get("brain")' 2>/dev/null; then
    pass "vLLM engine metrics (vision + brain)"
  else
    fail "vLLM engine metrics (one or both engines offline)"
  fi
}

check_file() {
  if [ -s "$2" ]; then pass "$1"; else fail "$1 ($2)"; fi
}

printf '%s\n' '── inference'
check_match "vision model :8000" "${VISION_BASE%/}/models" "$VISION_MODEL"
check_match "brain model :8001" "${BRAIN_BASE%/}/models" "$BRAIN_MODEL"
check_match "widget API uses vLLM" "http://127.0.0.1:8756/api/info" '"backend":"vllm"'

printf '%s\n' '── browser workflow'
check_match "frontend :5173" "$FRONTEND/" '8kEdu'
check_match "Excel demo concepts" "$FRONTEND/5IgOP7Lpk5g/concepts.json" 'Excel Column Formatting Options'
check_match "Excel demo transcript" "$FRONTEND/5IgOP7Lpk5g/transcript.json" 'text'
check_match "Excel demo chapters" "$FRONTEND/5IgOP7Lpk5g/chapters.json" 'Wrap Text'
check_match "Excel demo metadata" "$FRONTEND/5IgOP7Lpk5g/metadata.json" '331.0'
check_engines

printf '%s\n' '── presentation assets'
check_file "runbook" "docs/RED_HAT_VLLM_DEMO.md"
check_file "performance artifact" "docs/perf.html"
for asset in excel-widget vllm-engine-live vllm-throughput paged-attention; do
  check_file "$asset fallback" "docs/assets/redhat-vllm-demo/$asset.png"
done

if [ "$FAIL" -eq 0 ]; then
  printf '\n\033[32mRED HAT DEMO READY.\033[0m\n'
else
  printf '\n\033[31mRED HAT DEMO NOT READY. Fix the failed checks before presenting.\033[0m\n'
fi
exit "$FAIL"
