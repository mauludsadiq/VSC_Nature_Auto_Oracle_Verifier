#!/bin/bash

cd "$(git rev-parse --show-toplevel)"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8011}"
BASE="http://${HOST}:${PORT}"

API_KEY="${API_KEY:-ci_key}"
CONCURRENCY="${CONCURRENCY:-1000}"
REQUESTS="${REQUESTS:-20000}"

export VSC_API_AUTH_ENABLED="${VSC_API_AUTH_ENABLED:-true}"
export VSC_API_KEYS="${VSC_API_KEYS:-ci_key}"
export VSC_API_KEY_SCOPES="${VSC_API_KEY_SCOPES:-ci_key:read,verify,promote,sign,admin}"

LOG="out/load/api_server.log"
mkdir -p out/load

python3 -m uvicorn api.app:app --host "${HOST}" --port "${PORT}" > "${LOG}" 2>&1 &
PID=$!

python3 - <<'PY'
import time, sys, urllib.request
base = sys.argv[1]
for _ in range(60):
    try:
        with urllib.request.urlopen(base + "/v1/health", timeout=1.0) as r:
            if r.status == 200:
                sys.exit(0)
    except Exception:
        pass
    time.sleep(0.2)
sys.exit(2)
PY "${BASE}"

python3 -m scripts.load_api --base "${BASE}" --api-key "${API_KEY}" --concurrency "${CONCURRENCY}" --requests "${REQUESTS}" --out out/load/load_report.json

kill "${PID}" >/dev/null 2>&1 || true
wait "${PID}" >/dev/null 2>&1 || true

grep -n "^PASS_API_STATUS " "${LOG}" | tail -5 || true
