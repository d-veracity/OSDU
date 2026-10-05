#!/usr/bin/env bash
# Reproduce the Methane MRV (ISO 25624-1) proof end-to-end against any OSDU platform.
#
#   OSDU_BASE=https://<gateway> OSDU_PARTITION=osdu OSDU_TOKEN_FILE=/path/to/token bash run_all.sh
#
# Steps: generate+register schemas (from SysML + ISO reference data) -> reconciliation
#        lifecycle (bottom-up vs top-down gate -> verified) -> attestation + unlit-flare
#        anomaly -> ISO 12.3 restatement -> OFP handshake + evidence export -> OFP data-domain
#        kinds + grounding -> complete evidence export -> offline verification.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${OSDU_BASE:=https://172.171.6.4.nip.io}"; : "${OSDU_PARTITION:=osdu}"
: "${OSDU_TOKEN_FILE:?set OSDU_TOKEN_FILE=/path/to/bearer-token}"
export OSDU_BASE OSDU_PARTITION OSDU_TOKEN_FILE
TOKEN="$(tr -d '\r\n' < "$OSDU_TOKEN_FILE")"; HA="Authorization: Bearer $TOKEN"; HP="data-partition-id: $OSDU_PARTITION"

echo "### 1/5  generate methane schemas (SysML + ISO 25624-1 reference data)"
python3 "$DIR/generate_methane_schemas.py" >/dev/null
echo "### 2/5  register schemas (idempotent)"
for f in "$DIR"/schemas/ofp_wks_*.json; do
  id=$(python3 -c "import json;print(json.load(open('$f'))['schemaInfo']['schemaIdentity']['id'])")
  code=$(curl -sk -m 30 -o /tmp/r.$$ -w "%{http_code}" -X POST "$OSDU_BASE/api/schema-service/v1/schema" \
    -H "$HA" -H "$HP" -H "Content-Type: application/json" --data @"$f")
  if [[ "$code" =~ ^2 ]]; then echo "  OK   ${id#ofp:wks:}"
  elif [[ "$code" == 400 ]] && grep -q "already present" /tmp/r.$$; then echo "  SKIP ${id#ofp:wks:}"
  else echo "  FAIL $code $id"; cat /tmp/r.$$; exit 1; fi; rm -f /tmp/r.$$
done
echo "### 3/5  reconciliation lifecycle (ISO Cl.11 gate -> verified)"
python3 "$DIR/methane_lifecycle.py"
echo "### 4/5  attestation + unlit-flare anomaly -> ISO 12.3 restatement"
python3 "$DIR/methane_anomaly.py"
echo "### 5/7  OFP restatement handshake + evidence export"
python3 "$DIR/day4_export.py"
echo "### 6/7  OFP data-domain kinds via the ofp-schema-deploy pipeline (idempotent)"
( cd "$DIR/.." && python3 ofp-schema-deploy/generate_domain_schemas.py >/dev/null && bash ofp-schema-deploy/register_schemas.sh domains )
echo "### 7/7  ground the proof in the OFP domains (org/facility/recording/reporting/data-verification) + export"
python3 "$DIR/ofp-domains/ofp_grounding.py"
python3 "$DIR/ofp-domains/ofp_export.py"
echo "### 8/9  complete evidence export (all records, all versions, all schema bodies)"
python3 "$DIR/export_claim3.py"
echo "### 9/9  verify the export offline (no network)"
python3 "$DIR/verify_export.py"
echo "### done — see $DIR/export/README.md (bundle) and $DIR/export/claim3/_manifest.json"
