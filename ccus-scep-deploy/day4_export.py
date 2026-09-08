#!/usr/bin/env python3
"""
Day 4 — close the OFP bidirectional export handshake (claim #1), then export every
record we created from OSDU to local JSON so the proof survives losing the stack.

Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.
"""
import os, json
from scep_lifecycle import put, rec, _req, BASE_ACT, SITE

HERE = os.path.dirname(__file__)
EXPORT = os.path.join(HERE, "export")
os.makedirs(EXPORT, exist_ok=True)
d2 = json.load(open(os.path.join(HERE, "day2_result.json")))
d3 = json.load(open(os.path.join(HERE, "day3_result.json")))

def main():
    print(f"\n=== Day 4: OFP export handshake + evidence export — {SITE} ===\n")

    # 1) OFP bidirectional export handshake (claim #1): reconcile the OSDU-side carbon-claim
    #    adjustment back to the Open Footprint carbon-accounting activity.
    ofp = rec("OFPAdjustmentRecord", {**BASE_ACT("ofp_adjustment"),
        "ofpActivityReferenceId": f"{SITE}-OFP-REMOVAL-01",
        "adjustmentType": "carbon_removal_reversal",
        "adjustmentReason": "SCEP suspended on AoR breach; stored-CO2 claim reduced 985kt -> 950kt",
        "originalValue": 985000.0, "adjustedValue": 950000.0,
        "adjustmentConfidence": 0.9, "reconciledBy": "dVeracity bridge"})
    ofp_id = put([ofp])[0]
    print(f"[1] OFPAdjustmentRecord -> {ofp_id.split(':')[-1][:12]}…  OSDU→OFP handshake: -35000 t removal reversal")

    # 2) collect every record id we created across Days 2–4
    ids = {}
    ids.update({f"evidence.{k}": v for k, v in d2["evidenceIds"].items()})
    ids["scep.snapshot"] = d2["scepId"]
    ids["attestation"] = d3["attestationId"]
    ids["anomaly.breachPlume"] = d3["breachPlumeId"]
    ids["anomaly.mmvEvent"] = d3["mmvId"]
    ids["anomaly.claimAdjust"] = d3["claimAdjustId"]
    ids["ofp.exportHandshake"] = ofp_id

    print(f"\n[2] Exporting {len(ids)} records + SCEP version history to {os.path.relpath(EXPORT, os.path.dirname(HERE))}/ …")
    exported = {}
    for label, rid in ids.items():
        s, r = _req("GET", f"/api/storage/v2/records/{rid}")
        if s < 300 and r:
            fn = os.path.join(EXPORT, f"{label}.json")
            json.dump(r, open(fn, "w"), indent=2)
            exported[label] = {"id": rid, "kind": r.get("kind"), "version": r.get("version")}
            print(f"    {label:26s} {r.get('kind','').split('--')[-1]:35s} v{r.get('version')}")
        else:
            print(f"    {label:26s} !! GET {s}")

    # SCEP immutable version history (the audit trail)
    s, sv = _req("GET", f"/api/storage/v2/records/versions/{d2['scepId']}")
    if s < 300 and sv:
        json.dump(sv, open(os.path.join(EXPORT, "scep.version-history.json"), "w"), indent=2)
        # pull each version's status for the timeline
        timeline = []
        for v in sv.get("versions", []):
            sv2, rv = _req("GET", f"/api/storage/v2/records/{d2['scepId']}/{v}")
            if sv2 < 300 and rv:
                timeline.append({"version": v, "status": rv["data"].get("certificationStatusAtSnapshot"),
                                 "trigger": rv["data"].get("versionTrigger")})
        json.dump(timeline, open(os.path.join(EXPORT, "scep.timeline.json"), "w"), indent=2)
        print(f"\n[3] SCEP audit trail: {len(timeline)} immutable versions")
        for t in timeline:
            print(f"    v{str(t['version'])[-6:]}  {t['status']:12s} ({t['trigger']})")

    summary = {"site": SITE, "records": exported, "failedConstraints": d3.get("failedConstraints", []),
               "counts": {"total": len(exported)}}
    json.dump(summary, open(os.path.join(EXPORT, "_summary.json"), "w"), indent=2)
    print(f"\n[4] Export complete — {len(exported)} records saved locally. Proof is now portable.\n")

if __name__ == "__main__":
    main()
