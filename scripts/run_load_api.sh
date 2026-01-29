#!/bin/sh

API_KEY="${API_KEY:-}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
CONCURRENCY="${CONCURRENCY:-200}"
REQUESTS="${REQUESTS:-2000}"
TIMEOUT_S="${TIMEOUT_S:-30}"
MIX="${MIX:-health,status,metrics}"
VERIFY_STEP_DIR="${VERIFY_STEP_DIR:-}"
OUT="${OUT:-out/load/load_report.json}"

BASE="http://${HOST}:${PORT}"

i=0
code="000"
while [ $i -lt 60 ]; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/v1/health" 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then
    break
  fi
  i=$((i+1))
  sleep 0.2
done

if [ "$code" != "200" ]; then
  echo "LOAD_PREFLIGHT_FAIL base=${BASE} last_http_code=${code}" 1>&2
  exit 1
fi

python3 -m scripts.load_api \
  --base "${BASE}" \
  --api-key "${API_KEY}" \
  --concurrency "${CONCURRENCY}" \
  --requests "${REQUESTS}" \
  --timeout-s "${TIMEOUT_S}" \
  --mix "${MIX}" \
  --verify-step-dir "${VERIFY_STEP_DIR}" \
  --out "${OUT}"
