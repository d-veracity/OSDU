#!/usr/bin/env bash
# Reproduce the full SCEP-on-OSDU proof end-to-end against any OSDU platform.
#
#   OSDU_BASE=https://<gateway> OSDU_PARTITION=osdu OSDU_TOKEN_FILE=/path/to/token \
#     bash run_all.sh
#
# Steps: generate+register CCUS/SCEP schemas -> certification lifecycle (Class VI gate)
#        -> attestation + MMV anomaly cascade -> OFP export handshake + evidence export.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${OSDU_BASE:=https://172.171.6.4.nip.io}"; : "${OSDU_PARTITION:=osdu}"
: "${OSDU_TOKEN_FILE:?set OSDU_TOKEN_FILE=/path/to/bearer-token}"
export OSDU_BASE OSDU_PARTITION OSDU_TOKEN_FILE
TOKEN="$(tr -d '\r\n' < "$OSDU_TOKEN_FILE")"; HA="Authorization: Bearer $TOKEN"; HP="data-partition-id: $OSDU_PARTITION"

echo "### 1/5  generate CCUS/SCEP schemas from SysML"
python3 "$DIR/generate_ccus_scep_schemas.py" >/dev/null

echo "### 2/5  register schemas (idempotent)"
for f in "$DIR"/schemas/ofp_wks_*.json; do
  id=$(python3 -c "import json;print(json.load(open('$f'))['schemaInfo']['schemaIdentity']['id'])")
  code=$(curl -sk -m 30 -o /tmp/r.$$ -w "%{http_code}" -X POST "$OSDU_BASE/api/schema-service/v1/schema" \
    -H "$HA" -H "$HP" -H "Content-Type: application/json" --data @"$f")
  if [[ "$code" =~ ^2 ]]; then echo "  OK   ${id##*--}"
  elif [[ "$code" == 400 ]] && grep -q "already present" /tmp/r.$$; then echo "  SKIP ${id##*--}"
  else echo "  FAIL $code $id"; cat /tmp/r.$$; exit 1; fi; rm -f /tmp/r.$$
done

echo "### 3/5  SCEP certification lifecycle (Class VI gate -> certified)"
python3 "$DIR/scep_lifecycle.py"
echo "### 4/5  attestation + MMV anomaly cascade (-> suspended)"
python3 "$DIR/scep_attestation_anomaly.py"
echo "### 5/5  OFP export handshake + evidence export"
python3 "$DIR/day4_export.py"
echo "### done — see $DIR/export/"
