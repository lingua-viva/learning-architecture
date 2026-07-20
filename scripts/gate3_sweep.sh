#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${LV_GATE3_PORT:-8787}"
BASE="http://127.0.0.1:${PORT}"
TMP_DIR="$(mktemp -d)"
QUERY="What CEFR targets for Grade 3 La Famiglia?"
PRIVATE_QUERY="student name: Marco parent report progress report keep local"

cleanup() {
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

json_check() {
  local payload
  payload="$(cat)"
  python3 - "$1" "$payload" <<'PY'
import json
import sys

mode = sys.argv[1]
data = json.loads(sys.argv[2])

if mode == "query":
    assert data.get("route") == "local", data
    assert data.get("trace_id"), data
    assert data.get("classification", {}).get("node"), data
elif mode == "private_query":
    assert data.get("route") == "local", data
    assert data.get("external_calls") == 0, data
elif mode == "why":
    raw = json.dumps(data)
    assert "CEFR targets" not in raw, data
    assert "La Famiglia" not in raw, data
    assert (data.get("traces") or data).get("external_calls", 0) == 0 if isinstance((data.get("traces") or data), dict) else True
elif mode == "privacy":
    assert data["external_calls"] == 0, data
    assert data["docx_modifications"] == 0, data
elif mode == "health":
    assert data["status"] in ("OK", "WARN", "FIXABLE"), data
elif mode == "brief":
    assert "today" in data and "attention" in data and "health" in data, data
elif mode == "filemap":
    assert "summary" in data and "student_zones_detected" in data, data
elif mode == "clear_rejected":
    assert "error" in data, data
PY
}

wait_ready() {
  for _ in $(seq 1 80); do
    if curl -fsS --max-time 1 "${BASE}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

if python3 - <<PY
import socket
s=socket.socket(); s.settimeout(.25)
raise SystemExit(0 if s.connect_ex(('127.0.0.1', ${PORT})) != 0 else 1)
PY
then
  :
else
  echo "Port ${PORT} is already in use" >&2
  exit 1
fi

cd "$ROOT"

for i in $(seq 1 15); do
  echo "=== Gate 3 sweep iteration ${i} ==="
  export LV_TRACE_PATH="${TMP_DIR}/traces-${i}.ndjson"
  export LV_PRIVACY_LOG_PATH="${TMP_DIR}/privacy-${i}.ndjson"
  export LV_FILE_MAP_PATH="${TMP_DIR}/filemap-${i}.yaml"
  export LV_STUDENT_DB_PATH="${TMP_DIR}/students-${i}.db"
  export LV_REVISION_LOG_PATH="${TMP_DIR}/revision-${i}.ndjson"
  export LV_REASON_TIMEOUT_SECONDS=2

  python3 src/web.py "$PORT" >/dev/null 2>&1 &
  SERVER_PID=$!
  wait_ready

  curl -fsS -X POST "${BASE}/api/query" -H 'Content-Type: application/json' \
    -d "{\"query\":\"${QUERY}\",\"intent\":\"TEACH\",\"timeout_seconds\":10,\"eval_mode\":true}" | json_check query

  curl -fsS -X POST "${BASE}/api/query" -H 'Content-Type: application/json' \
    -d "{\"query\":\"${PRIVATE_QUERY}\",\"intent\":\"TEACH\",\"timeout_seconds\":10,\"eval_mode\":true}" | json_check private_query

  curl -fsS "${BASE}/api/why" | json_check why
  curl -fsS "${BASE}/api/privacy" | json_check privacy
  curl -fsS "${BASE}/api/health" | json_check health
  curl -fsS "${BASE}/api/brief" | json_check brief
  curl -fsS "${BASE}/api/filemap" | json_check filemap

  set +e
  clear_body="$(curl -sS -X POST "${BASE}/api/profile/clear" -H 'Content-Type: application/json' -d '{"confirm":"wrong"}')"
  clear_status=$?
  set -e
  [ "$clear_status" -eq 0 ]
  printf '%s' "$clear_body" | json_check clear_rejected

  git status --short -- Manuale_Italiano_Laboratorio_Linguistico_G1-G5.docx | python3 -c 'import sys; assert sys.stdin.read().strip() == ""'

  kill "$SERVER_PID" >/dev/null 2>&1 || true
  wait "$SERVER_PID" >/dev/null 2>&1 || true
  unset SERVER_PID
  sleep 0.5
  python3 - <<PY
import socket
s=socket.socket(); s.settimeout(.25)
assert s.connect_ex(('127.0.0.1', ${PORT})) != 0
PY
  echo "Iteration ${i} PASSED"
done

echo "Gate 3 sweep: 15/15 passed"
