#!/usr/bin/env python3
"""
Claim #3, Day 4 — OFP restatement handshake + portable evidence export.

1. Flows the ISO 12.3 restatement back to Open Footprint as an OFPAdjustmentRecord
   (the OSDU -> OFP bidirectional handshake, mirroring the SCEP proof).
2. Exports every record created in Days 2-3, plus the immutable version histories of the
   MethaneMonitoringPlan and the attestation, to export/*.json — so the proof survives
   losing the environment.

Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.
"""
import os, json
from methane_lifecycle import put, rec, _req, BASE_ACT, W, SITE, YEAR, GWP100

HERE = os.path.dirname(__file__)
EXPORT = os.path.join(HERE, "export"); os.makedirs(EXPORT, exist_ok=True)
d2 = json.load(open(os.path.join(HERE, "day2_result.json")))
d3 = json.load(open(os.path.join(HERE, "day3_result.json")))

def get(rid): return _req("GET", f"/api/storage/v2/records/{rid}")

def main():
    print(f"\n=== Day 4: OFP restatement handshake + evidence export — {SITE} / {YEAR} ===\n")
    r = d3["restated"]
    ofp = rec(W("OFPAdjustmentRecord"), {**BASE_ACT("ofp_adjustment"),
        "ofpActivityReferenceId": f"{SITE}-OFP-CH4-{YEAR}", "adjustmentType": "methane_inventory_restatement",
        "adjustmentReason": f"ISO 25624-1 12.3 restatement: unlit-flare episode annualized (+{r['bottomUp']-d2['metrics']['bottom_up']:,.0f} kg CH4, {r['restatementPct']:.1f}% > 5% materiality)",
        "originalValue": round(d2["metrics"]["bottom_up"] * GWP100 / 1000, 1),
        "adjustedValue": round(r["bottomUp"] * GWP100 / 1000, 1),
        "adjustmentConfidence": 0.9, "reconciledBy": "dVeracity bridge"})
    ofp_id = put([ofp])[0]
    print(f"[1] OFPAdjustmentRecord -> {ofp_id.split(':')[-1][:12]}…  OSDU→OFP: {ofp['data']['originalValue']:,} → {ofp['data']['adjustedValue']:,} t CO2e")

    ids = {}
    for i, x in enumerate(d2["evidenceIds"]["inventory"]): ids[f"inventory.{i}"] = x
    for i, x in enumerate(d2["evidenceIds"]["site"]): ids[f"site.{i}"] = x
    for i, x in enumerate(d2["evidenceIds"]["refdata"]): ids[f"refdata.{i}"] = x
    ids.update({"plan": d2["planId"], "reconciliation.v1": d2["reconciliationId"], "ogmp.v1": d2["ogmpReportId"],
        "attestation": d3["attestationId"], "anomaly.alert": d3["alertId"], "anomaly.resurvey": d3["resurveyId"],
        "anomaly.topdown": d3["topdownEventId"], "restate.unlitInventory": d3["unlitInventoryId"],
        "restate.unlitQuant": d3["unlitQuantId"], "reconciliation.v2": d3["reconciliation2Id"],
        "ogmp.v2": d3["ogmpReport2Id"], "ofp.restatementHandshake": ofp_id})

    print(f"\n[2] Exporting {len(ids)} records …")
    exported = {}
    for label, rid in ids.items():
        s, j = get(rid)
        if s < 300 and j:
            json.dump(j, open(os.path.join(EXPORT, f"{label}.json"), "w"), indent=2)
            exported[label] = {"id": rid, "kind": j.get("kind"), "version": j.get("version")}
        else: print(f"    !! {label} GET {s}")
    print(f"    saved {len(exported)}")

    def timeline(rid, field):
        s, v = _req("GET", f"/api/storage/v2/records/versions/{rid}"); out = []
        for ver in (v or {}).get("versions", []):
            s2, rv = _req("GET", f"/api/storage/v2/records/{rid}/{ver}")
            if s2 < 300 and rv: out.append({"version": ver, "status": rv["data"].get(field), "trigger": rv["data"].get("versionTrigger")})
        return out
    tl_plan = timeline(d2["planId"], "verificationStatus"); tl_att = timeline(d3["attestationId"], "attestationStatus")
    json.dump(tl_plan, open(os.path.join(EXPORT, "plan.timeline.json"), "w"), indent=2)
    json.dump(tl_att, open(os.path.join(EXPORT, "attestation.timeline.json"), "w"), indent=2)
    print(f"\n[3] MonitoringPlan audit trail ({len(tl_plan)} immutable versions): " + " → ".join(t['status'] or '?' for t in tl_plan))
    print(f"    Attestation trail ({len(tl_att)} versions): " + " → ".join(t['status'] or '?' for t in tl_att))

    json.dump({"site": SITE, "year": YEAR, "records": exported, "metrics": d2["metrics"], "restated": r,
               "gate": d2["gate"], "counts": {"total": len(exported)}},
              open(os.path.join(EXPORT, "_summary.json"), "w"), indent=2)
    print(f"\n[4] Export complete — {len(exported)} records + 2 version histories saved. Proof is portable.\n")

if __name__ == "__main__":
    main()
