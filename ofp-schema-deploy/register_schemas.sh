#!/usr/bin/env bash
# Register generated OFP schemas onto an OSDU Schema Service.
#
# Usage:
#   OSDU_TOKEN_FILE=/path/to/token ./register_schemas.sh test     # 1 entity, then stop
#   OSDU_TOKEN_FILE=/path/to/token ./register_schemas.sh refdata  # 20 reference-data
#   OSDU_TOKEN_FILE=/path/to/token ./register_schemas.sh all      # everything, deps first
#   OSDU_TOKEN_FILE=/path/to/token ./register_schemas.sh domains  # methane-proof domain kinds (manifest-domains.json)
#
# Env overrides:
#   OSDU_BASE        (default https://104.43.134.183.nip.io)
#   OSDU_PARTITION   (default osdu)
#   OSDU_TOKEN_FILE  (file containing the bearer token; required)
#   OSDU_TOKEN       (raw token; used if OSDU_TOKEN_FILE unset)
#
# Safe by design: registers as DEVELOPMENT scope, stops on first non-2xx, per-kind status.
# REMEMBER: OSDU schemas can never be deleted. Only flip DEVELOPMENT->PUBLISHED once a
# test record validates against the schema — a PUBLISHED schema is frozen forever.
set -euo pipefail

BASE="${OSDU_BASE:-https://104.43.134.183.nip.io}"
PART="${OSDU_PARTITION:-osdu}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/schemas"
MODE="${1:-test}"

if [[ -n "${OSDU_TOKEN_FILE:-}" && -f "$OSDU_TOKEN_FILE" ]]; then
  TOKEN="$(tr -d '\r\n' < "$OSDU_TOKEN_FILE")"
elif [[ -n "${OSDU_TOKEN:-}" ]]; then
  TOKEN="$OSDU_TOKEN"
else
  echo "ERROR: set OSDU_TOKEN_FILE=/path/to/token (or OSDU_TOKEN=...)"; exit 2
fi

post_one() {
  local file="$1" id code
  id=$(python3 -c "import json;print(json.load(open('$file'))['schemaInfo']['schemaIdentity']['id'])")
  code=$(curl -sk -m 30 -o /tmp/reg_resp.$$ -w "%{http_code}" \
    -X POST "${BASE}/api/schema-service/v1/schema" \
    -H "Authorization: Bearer ${TOKEN}" -H "data-partition-id: ${PART}" \
    -H "Content-Type: application/json" --data @"$file")
  if [[ "$code" =~ ^2 ]]; then
    printf "  OK   %s  %s\n" "$code" "$id"
  elif [[ "$code" == "400" ]] && grep -q "already present" /tmp/reg_resp.$$; then
    printf "  SKIP %s  %s (already registered)\n" "$code" "$id"
  else
    printf "  FAIL %s  %s\n" "$code" "$id"; echo "  --- response ---"; head -c 700 /tmp/reg_resp.$$; echo
    rm -f /tmp/reg_resp.$$; exit 1
  fi
  rm -f /tmp/reg_resp.$$
}

dedup() { python3 -c "
import json
seen=set()
for e in json.load(open('$DIR/manifest.json'))['$1']:
    if e['file'] in seen: continue
    seen.add(e['file']); print('$DIR/'+e['file'])"; }
mapfile -t REF < <(dedup reference-data)
mapfile -t MAS < <(dedup master-data)
# transaction-data (OSDU-native work-product-component) has its own manifest
dedup_tx() { python3 -c "
import json,os
p='$DIR/manifest-transaction.json'
if not os.path.exists(p): raise SystemExit
seen=set()
for e in json.load(open(p))['work-product-component']:
    if e['file'] in seen: continue
    seen.add(e['file']); print('$DIR/'+e['file'])"; }
mapfile -t TX < <(dedup_tx)

# domain kinds (Data Verification / Org / Facility / Recording / Reporting) have their own manifest
dedup_dom() { python3 -c "
import json,os
p='$DIR/manifest-domains.json'
if not os.path.exists(p): raise SystemExit
seen=set()
for g in ('reference-data','master-data','work-product-component'):
    for e in json.load(open(p)).get(g,[]):
        if e['file'] in seen: continue
        seen.add(e['file']); print('$DIR/'+e['file'])"; }
mapfile -t DOM < <(dedup_dom)

case "$MODE" in
  test)
    echo "TEST: registering EmissionScopeType (reference-data)…"
    post_one "$DIR/ofp_wks_reference-data--EmissionScopeType_3.0.0.json"
    echo "OK -> next: $0 refdata" ;;
  refdata)
    echo "Registering ${#REF[@]} reference-data kinds…"
    for f in "${REF[@]}"; do post_one "$f"; done
    echo "Done -> next: $0 all" ;;
  transaction)
    echo "Registering ${#TX[@]} transaction-data (work-product-component) kinds…"
    for f in "${TX[@]}"; do post_one "$f"; done
    echo "Transaction-data done." ;;
  all)
    echo "Registering ${#REF[@]} reference-data, ${#MAS[@]} master-data, ${#TX[@]} transaction-data…"
    for f in "${REF[@]}"; do post_one "$f"; done
    for f in "${MAS[@]}"; do post_one "$f"; done
    for f in "${TX[@]}"; do post_one "$f"; done
    echo "All done." ;;
  domains)
    echo "Registering ${#DOM[@]} domain kinds (reference-data, master-data, work-product-component)…"
    for f in "${DOM[@]}"; do post_one "$f"; done
    echo "Domain kinds done." ;;
  *) echo "unknown mode: $MODE (test|refdata|transaction|all|domains)"; exit 2 ;;
esac
