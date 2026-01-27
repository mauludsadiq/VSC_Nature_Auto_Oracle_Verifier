#!/usr/bin/env bash

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
BASE="http://${HOST}:${PORT}"

FIXTURE_ROOT="${FIXTURE_ROOT:-tests/fixtures/historical}"
STREAM_ID="${STREAM_ID:-oracle_001}"
STEP_NUMBER="${STEP_NUMBER:-1}"

PUBKEY_PATH="${PUBKEY_PATH:-$ROOT/keys/ledger_pubkey.hex}"
SCHEME="${SCHEME:-ed25519.v1}"

TMP="$(mktemp -d)"
HIST="$TMP/historical"
mkdir -p "$HIST"

cp -R "$FIXTURE_ROOT/$STREAM_ID" "$HIST/$STREAM_ID" 2>/dev/null || true

if [ ! -d "$HIST/$STREAM_ID/step_$(printf '%06d' "$STEP_NUMBER")" ]; then
  echo "SMOKE_FAIL missing fixture step dir"
  echo "$HIST/$STREAM_ID/step_$(printf '%06d' "$STEP_NUMBER")"
  exit 2
fi

rm -f "$HIST/$STREAM_ID/step_$(printf '%06d' "$STEP_NUMBER")/root.sig"

rm -f out/api_server.log
mkdir -p out

VSC_HISTORICAL_ROOT="$HIST" \
VSC_SIGNATURE_SCHEME="$SCHEME" \
VSC_LEDGER_PUBKEY_PATH="$PUBKEY_PATH" \
python3 -m uvicorn api.app:app --host "$HOST" --port "$PORT" 2>&1 | tee out/api_server.log &
SVPID="$!"

python3 - <<PY
import time
import urllib.request
base = "${BASE}"
deadline = time.time() + 15.0
ok = False
while time.time() < deadline:
    try:
        with urllib.request.urlopen(base + "/v1/health", timeout=2.0) as r:
            if r.status == 200:
                ok = True
                break
    except Exception:
        time.sleep(0.2)
print("SMOKE_HEALTH_OK" if ok else "SMOKE_HEALTH_FAIL")
raise SystemExit(0 if ok else 2)
PY
RC="$?"
if [ "$RC" != "0" ]; then
  kill "$SVPID" 2>/dev/null || true
  exit 2
fi

curl -sS "$BASE/v1/status" | python3 -m json.tool > "$TMP/status.json"

python3 - <<PY
import json
p = "${TMP}/status.json"
d = json.load(open(p,"r",encoding="utf-8"))
need = ["notary_on","signature_scheme","ledger_pubkey_path"]
for k in need:
    if k not in d:
        raise SystemExit(2)
if not d["notary_on"]:
    raise SystemExit(2)
if d["signature_scheme"] != "${SCHEME}":
    raise SystemExit(2)
if d["ledger_pubkey_path"] != "${PUBKEY_PATH}":
    raise SystemExit(2)
print("SMOKE_STATUS_OK")
PY
RC="$?"
if [ "$RC" != "0" ]; then
  kill "$SVPID" 2>/dev/null || true
  exit 2
fi

curl -sS -X POST \
  "$BASE/v1/stream/$STREAM_ID/step/$STEP_NUMBER/sign" \
  -H 'Content-Type: application/json' \
  -d '{}' | python3 -m json.tool > "$TMP/sign.json"

python3 - <<PY
import json
p = "${TMP}/sign.json"
d = json.load(open(p,"r",encoding="utf-8"))
if not d.get("ok"):
    raise SystemExit(2)
if d.get("reason") != "PASS_SIGN_STEP":
    raise SystemExit(2)
print("SMOKE_SIGN_OK")
PY
RC="$?"
if [ "$RC" != "0" ]; then
  kill "$SVPID" 2>/dev/null || true
  exit 2
fi

SIGP="$HIST/$STREAM_ID/step_$(printf '%06d' "$STEP_NUMBER")/root.sig"
if [ ! -f "$SIGP" ]; then
  echo "SMOKE_FAIL root.sig missing"
  kill "$SVPID" 2>/dev/null || true
  exit 2
fi

curl -sS -X POST \
  "$BASE/v1/audit/verify-historical" \
  -H 'Content-Type: application/json' \
  -d "{\"stream_id\":\"$STREAM_ID\",\"step_number\":$STEP_NUMBER}" | python3 -m json.tool > "$TMP/audit.json"

python3 - <<PY
import json
p = "${TMP}/audit.json"
d = json.load(open(p,"r",encoding="utf-8"))
if not d.get("ok"):
    raise SystemExit(2)
if d.get("reason") != "PASS_VERIFY_BUNDLE":
    raise SystemExit(2)
if not d.get("same_hash"):
    raise SystemExit(2)
if not d.get("signature_valid"):
    raise SystemExit(2)
print("SMOKE_AUDIT_OK")
PY
RC="$?"
if [ "$RC" != "0" ]; then
  kill "$SVPID" 2>/dev/null || true
  exit 2
fi

grep -n "PASS_API_STATUS" out/api_server.log | tail -20 || true
grep -n "PASS_API_SIGN_STEP" out/api_server.log | tail -20 || true
grep -n "PASS_API_VERIFY_HISTORICAL_SIGNATURE" out/api_server.log | tail -20 || true

kill "$SVPID" 2>/dev/null || true

echo "SMOKE_PASS"
exit 0
