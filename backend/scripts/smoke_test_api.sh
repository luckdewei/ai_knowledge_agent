#!/usr/bin/env bash
# 前端主流程 API 冒烟测试
set -euo pipefail

BASE="${BASE_URL:-http://127.0.0.1:8000}"
FAIL=0

check() {
  local name="$1"
  local method="$2"
  local path="$3"
  local data="${4:-}"
  local expect="${5:-200}"

  echo -n "[$name] $method $path ... "
  local curl_max="${6:-30}"
  if [ -n "$data" ]; then
    code=$(curl -s -m "$curl_max" -o /tmp/smoke_body.json -w "%{http_code}" -X "$method" \
      -H "Content-Type: application/json" \
      -d "$data" "$BASE$path")
  else
    code=$(curl -s -m "$curl_max" -o /tmp/smoke_body.json -w "%{http_code}" -X "$method" "$BASE$path")
  fi

  if [ "$code" = "$expect" ]; then
    success=$(python3 -c "import json; d=json.load(open('/tmp/smoke_body.json')); print(d.get('success', False))" 2>/dev/null || echo "n/a")
    if [ "$success" = "True" ] || [ "$success" = "n/a" ]; then
      echo "OK ($code)"
    else
      echo "FAIL ($code, success=false)"
      cat /tmp/smoke_body.json | head -c 200
      echo
      FAIL=$((FAIL + 1))
    fi
  else
    echo "FAIL (HTTP $code, expected $expect)"
    cat /tmp/smoke_body.json | head -c 300
    echo
    FAIL=$((FAIL + 1))
  fi
}

echo "=== API Smoke Test @ $BASE ==="

check "health" GET "/api/health/"
check "knowledge stats" GET "/api/knowledge/stats"
check "knowledge recent" GET "/api/knowledge/recent?days=90&limit=10"
cp /tmp/smoke_body.json /tmp/smoke_recent.json
check "activity trend" GET "/api/insights/trends/activity?days=90"
check "attention shift" GET "/api/insights/trends/attention?days=90"
check "reminders" GET "/api/insights/reminders"

# 需要已有知识 ID
KID=$(python3 -c "
import json
d=json.load(open('/tmp/smoke_recent.json'))
items=d.get('data') or []
print(items[0]['id'] if items else '')
" 2>/dev/null || true)

if [ -n "$KID" ]; then
  check "knowledge detail" GET "/api/knowledge/$KID"
  check "knowledge network" GET "/api/insights/network/$KID?depth=2" "" 200 60
else
  echo "[knowledge detail] SKIP (no knowledge in DB)"
fi

check "knowledge search" POST "/api/knowledge/search" '{"query":"Python","top_k":3}'
check "agent chat" POST "/api/agent/chat" '{"query":"你好","session_id":"smoke-test","stream":false}' 200 90

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "=== All checks passed ==="
  exit 0
else
  echo "=== $FAIL check(s) failed ==="
  exit 1
fi
