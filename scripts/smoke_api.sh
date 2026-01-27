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

STEP_DIR="$HIST/$STREAM_ID/step_$(printf '%06d' "$STEP_NUMBER")"
if [ ! -d "$STEP_DIR" ]; then
  echo "SMOKE_FAIL missing fixture step dir"
  echo "$STEP_DIR"
  exit 2
fi

rm -f "$STEP_DIR/root.sig"

rm -f out/api_server.log
mkdir -p out

VSC_HISTORICAL_ROOT="$HIST" \
VSC_SIGNATURE_SCHEME="$SCHEME" \
VSC_LEDGER_PUBKEY_PATH="$PUBKEY_PATH" \
python3 -m uvicorn api.app:app --host "$HOST" --port "$PORT" 2>&1 | tee out/api_server.log &
SVPID="$!"

fail_with_logs () {
  echo "=== SMOKE_FAIL_CONTEXT ==="
  echo "BASE=$BASE"
  echo "HIST=$HIST"
  echo "STEP_DIR=$STEP_DIR"
  echo "PUBKEY_PATH=$PUBKEY_PATH"
  echo "SCHEME=$SCHEME"
  echo
  echo "=== SERVER LOG TAIL ==="
  tail -200 out/api_server.log 2>/dev/null || true
  kill "$SVPID" 2>/dev/null || true
  exit 2
}

# Health gate (curl loop): stable + produces uvicorn access log line
i=0
ok=0
while [ "$i" -lt 300 ]; do
  if curl -fsS "$BASE/v1/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 0.2
  i=$((i+1))
done

if [ "$ok" != "1" ]; then
  echo "SMOKE_HEALTH_FAIL"
  fail_with_logs
fi
echo "SMOKE_HEALTH_OK"

curl -fsS "$BASE/v1/status" | python3 -m json.tool > "$TMP/status.json" 2>/dev/null || true

python3 - <<PY
import json, sys
p = "${TMP}/status.json"
try:
    d = json.load(open(p,"r",encoding="utf-8"))
except Exception:
    sys.exit(2)
need = ["notary_on","signature_scheme","ledger_pubkey_path"]
for k in need:
    if k not in d:
        sys.exit(2)
if not d["notary_on"]:
    sys.exit(2)
if d["signature_scheme"] != "${SCHEME}":
    sys.exit(2)
if d["ledger_pubkey_path"] != "${PUBKEY_PATH}":
    sys.exit(2)
print("SMOKE_STATUS_OK")
PY
RC="$?"
if [ "$RC" != "0" ]; then
  echo "=== STATUS.JSON ==="
  cat "$TMP/status.json" 2>/dev/null || true
  fail_with_logs
fi

curl -fsS -X POST \
  "$BASE/v1/stream/$STREAM_ID/step/$STEP_NUMBER/sign" \
  -H 'Content-Type: application/json' \
  -d '{}' | python3 -m json.tool > "$TMP/sign.json" 2>/dev/null || true

python3 - <<PY
import json, sys
p = "${TMP}/sign.json"
try:
    d = json.load(open(p,"r",encoding="utf-8"))
except Exception:
    sys.exit(2)
if not d.get("ok"):
    sys.exit(2)
if d.get("reason") != "PASS_SIGN_STEP":
    sys.exit(2)
print("SMOKE_SIGN_OK")
PY
RC="$?"
if [ "$RC" != "0" ]; then
  echo "=== SIGN.JSON ==="
  cat "$TMP/sign.json" 2>/dev/null || true
  fail_with_logs
fi

SIGP="$STEP_DIR/root.sig"
if [ ! -f "$SIGP" ]; then
  echo "SMOKE_FAIL root.sig missing"
  fail_with_logs
fi

curl -fsS -X POST \
  "$BASE/v1/audit/verify-historical" \
  -H 'Content-Type: application/json' \
  -d "{\"stream_id\":\"$STREAM_ID\",\"step_number\":$STEP_NUMBER}" | python3 -m json.tool > "$TMP/audit.json" 2>/dev/null || true

python3 - <<PY
import json, sys
p = "${TMP}/audit.json"
try:
    d = json.load(open(p,"r",encoding="utf-8"))
except Exception:
    sys.exit(2)
if not d.get("ok"):
    sys.exit(2)
if d.get("reason") != "PASS_VERIFY_BUNDLE":
    sys.exit(2)
if not d.get("same_hash"):
    sys.exit(2)
if not d.get("signature_valid"):
    sys.exit(2)
print("SMOKE_AUDIT_OK")
PY
RC="$?"
if [ "$RC" != "0" ]; then
  echo "=== AUDIT.JSON ==="
  cat "$TMP/audit.json" 2>/dev/null || true
  fail_with_logs
fi

grep -n "^PASS_API_STATUS " out/api_server.log | tail -20 || true
grep -n "^PASS_API_SIGN_STEP " out/api_server.log | tail -20 || true
grep -n "^PASS_API_VERIFY_HISTORICAL_SIGNATURE " out/api_server.log | tail -20 || true

kill "$SVPID" 2>/dev/null || true

echo "SMOKE_PASS"
exit 0
