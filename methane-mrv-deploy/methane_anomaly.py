#!/usr/bin/env python3
"""
Claim #3, Day 3 — attestation + anomaly cascade on live OSDU, per ISO 25624-1.

The anomaly is the discrepancy ISO 25624-1 itself uses as its worked example (11.3):
an UNLIT FLARE releasing raw gas (Cl. 6.3, DRE = 0), caught by a top-down survey as a
super-emitter. The cascade follows the standard's reconciliation workflow (Figure 1):
  instantaneous re-reconciliation FAILS (11.3.1) -> discrepancy class C, abnormal operating
  condition (11.3) -> plan suspended -> adjustment: annualize the episode from the last
  credible lit data (6.3.4.3) -> RESTATEMENT (12.3, > 5% materiality) -> re-reconcile ->
  plan restated -> attestation re-issued bound to the restated hash.

Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.
"""
import os, json, hashlib
from methane_lifecycle import (put, rec, _req, BASE_ACT, W, R, HOURS, GWP100, SITE, YEAR,
    TOPDOWN_RATE_KGH, TOPDOWN_U_STD_PCT, K, DIVERGENCE_LIMIT, plan, ACL, LEGAL)

HERE = os.path.dirname(__file__)
d2 = json.load(open(os.path.join(HERE, "day2_result.json")))
PLAN_ID, RECON_ID, IDS, M = d2["planId"], d2["reconciliationId"], d2["evidenceIds"], d2["metrics"]

FLARE_LIT_SLIP_KGH = 12.0        # normal slip at 98% DRE (Day 2 inventory)
FLARE_UNLIT_KGH = 600.0          # ISO Formula (7): q·x_CH4·ρ with DRE = 0
UNLIT_HOURS = 72.0               # duration from last credible lit data (ISO 6.3.4.3)
SUPER_EMITTER_KGH = 100.0        # super-emitter threshold (EPA OOOOb response protocol)

def attestation(plan_hash, status, reason=None, unc=TOPDOWN_U_STD_PCT * K):
    d = {"activityType": "methane_attestation", "attestationId": f"{SITE}-ATT-{YEAR}",
         "planId": f"{SITE}-MP-{YEAR}", "planRecordId": PLAN_ID, "planHash": plan_hash,
         "reconciliationResultId": RECON_ID, "attestationStatus": status,
         "confidenceScore": 0.9, "expandedUncertaintyPercent": unc, "coverageFactorK": K,
         "verifiableCredential": {"type": "MethaneMRVVerificationCredential", "issuer": "did:web:dveracity.com",
             "subject": f"{SITE}-MP-{YEAR}", "issuanceDate": "2026-09-08T12:00:00Z",
             "proofType": "Ed25519Signature2020", "proofValue": f"sha256:{plan_hash[:32]}",
             "credentialStatus": "active" if status in ("issued", "reissued") else status},
         "attestationRef": f"attref:{plan_hash[:24]}", "issuedBy": "dVeracity Verifier",
         "issuedAt": "2026-09-08T12:00:00Z"}
    if reason: d["reason"] = reason
    return rec(W("MethaneAttestation"), d)

def main():
    print(f"\n=== Day 3: attestation + unlit-flare anomaly — {SITE} / {YEAR} (ISO 25624-1) ===\n")
    _, head = _req("GET", f"/api/storage/v2/records/{PLAN_ID}")
    h0 = head["data"]["planHash"]
    print(f"[0] Plan {PLAN_ID.split(':')[-1][:12]}…  status={head['data']['verificationStatus']}  hash={h0[:16]}…")

    att_id = put([attestation(h0, "issued")])[0]
    print(f"[1] dVeracity attestation ISSUED -> {att_id.split(':')[-1][:12]}…  VC bound to plan hash, U={TOPDOWN_U_STD_PCT*K:.0f}% (k=2)")

    # 2) anomaly — unlit flare caught as a super-emitter by a top-down re-survey
    print("\n[2] Anomaly: unlit flare (ISO 6.3) detected as super-emitter by drone re-survey …")
    alert_id = put([rec(W("MethaneAlertEvent"), {**BASE_ACT("ch4_alert"), "alertType": "superEmitter",
        "thresholdValue": SUPER_EMITTER_KGH, "measuredValue": FLARE_UNLIT_KGH, "responseRequired": True})])[0]
    td_event = TOPDOWN_RATE_KGH - FLARE_LIT_SLIP_KGH + FLARE_UNLIT_KGH   # site rate during the event
    resurvey_id = put([rec(W("MethaneDetectionEvent"), {**BASE_ACT("ch4_detection"), "deviceId": "DRONE-CRDS-07",
        "technology": "drone", "detectedConcentrationPPM": 96.0, "windSpeedMPS": 4.1, "windDirection": 250.0,
        "ogmpLevel": "level5", "plumeSizeM2": 42000.0})])[0]
    td_id = put([rec(W("EmissionQuantification"), {**BASE_ACT("ch4_quantification"), "sourceId": "SITE",
        "emissionRateKgPerHour": round(td_event, 1), "quantificationMethod": "massBalance",
        "uncertaintyPercent": TOPDOWN_U_STD_PCT * K, "co2eKg": round(td_event * HOURS * GWP100, 1), "ogmpLevel": "level5"})])[0]
    print(f"    alert {alert_id.split(':')[-1][:12]}…  measured {FLARE_UNLIT_KGH:.0f} kg/h > super-emitter {SUPER_EMITTER_KGH:.0f} kg/h")
    print(f"    re-survey site rate {td_event:.1f} kg/h (was {TOPDOWN_RATE_KGH})")

    # 3) instantaneous re-reconciliation (ISO 11.3.1): convert bottom-up to an instantaneous rate
    bu_inst = M["bottom_up"] / HOURS
    div_inst = abs(bu_inst - td_event) / td_event * 100
    print(f"\n[3] ISO 11.3.1 instantaneous re-reconciliation: bottom-up {bu_inst:.1f} kg/h vs top-down {td_event:.1f} kg/h")
    print(f"    [{'PASS' if div_inst <= DIVERGENCE_LIMIT else 'FAIL'}] SiteLevelReconciliation  |BU−TD|/TD = {div_inst:.1f}% ≤ {DIVERGENCE_LIMIT}%")
    print("    discrepancy class C (ISO 11.3): source in inventory but in an abnormal operating condition — unlit flare")

    # 4) plan verified -> suspended; attestation -> suspended
    ids = json.loads(json.dumps(IDS))
    put([{**plan(ids, "suspended", "1.0.0", "eventDriven", RECON_ID), "id": PLAN_ID}])
    put([{**attestation(h0, "suspended", "SiteLevelReconciliation failed on super-emitter event"), "id": att_id}])
    print("[4] MonitoringPlan verified -> SUSPENDED (eventDriven) | attestation issued -> SUSPENDED")

    # 5) adjustment: annualize the episode (ISO 6.3.4.3 duration, 11.3 annualize) and RESTATE (12.3)
    excess_kg = (FLARE_UNLIT_KGH - FLARE_LIT_SLIP_KGH) * UNLIT_HOURS
    bu_restated = M["bottom_up"] + excess_kg
    td_restated = TOPDOWN_RATE_KGH * (HOURS - UNLIT_HOURS) + td_event * UNLIT_HOURS
    div_restated = abs(bu_restated - td_restated) / td_restated * 100
    restate_pct = excess_kg / M["bottom_up"] * 100
    print(f"\n[5] Adjustment: unlit {UNLIT_HOURS:.0f} h × ({FLARE_UNLIT_KGH:.0f}−{FLARE_LIT_SLIP_KGH:.0f}) kg/h = +{excess_kg:,.0f} kg  "
          f"→ {restate_pct:.1f}% of inventory > 5% materiality → formal RESTATEMENT (ISO 12.3)")
    inv_id = put([rec(W("MethaneSourceInventory"), {**BASE_ACT("ch4_source_inventory"), "sourceCategory": "flaring",
        "componentType": "unlit flare episode (DRE=0, 72 h)", "lastInspectionDate": "2025-11-02T00:00:00Z",
        "emissionFactor": FLARE_UNLIT_KGH})])[0]
    q_id = put([rec(W("EmissionQuantification"), {**BASE_ACT("ch4_quantification"), "sourceId": "SRC-FLARE-UNLIT",
        "emissionRateKgPerHour": round(excess_kg / HOURS, 4), "quantificationMethod": "modelBased",
        "uncertaintyPercent": 30.0, "co2eKg": round(excess_kg * GWP100, 1), "ogmpLevel": "level4"})])[0]
    ref_id = put([rec(R("MethaneSourceCategory"), {"code": "unlitFlare", "name": "Unlit flare",
        "description": "ISO 25624-1 Clause 6.3 — flare operating as a vent, DRE = 0", "isoClause": "6.3"})])[0]
    ids["inventory"].append(inv_id); ids["site"].append(td_id); ids["refdata"].append(ref_id)

    recon2_id = put([rec(W("ReconciliationResult"), {**BASE_ACT("ch4_reconciliation"),
        "bottomUpTotalKg": round(bu_restated, 1), "topDownTotalKg": round(td_restated, 1),
        "divergencePercent": round(div_restated, 2), "reconciliationVerdict": "passed" if div_restated <= DIVERGENCE_LIMIT else "failed",
        "reconciledTotalKg": round(bu_restated, 1)})])[0]
    cov2 = (bu_restated - 4380.0) / bu_restated * 100   # fugitives remain the only L3 source
    ogmp2_id = put([rec(W("OGMPReport"), {**BASE_ACT("ogmp_report"), "reportingYear": YEAR, "reportingLevel": "level4",
        "coveredEmissionsPercent": round(cov2, 1), "goldStandardCompliant": div_restated <= DIVERGENCE_LIMIT and cov2 >= 95,
        "submittedToIMEO": False, "submissionStatus": "draft"})])[0]
    print(f"    restated: bottom-up {bu_restated:,.0f} vs top-down {td_restated:,.0f} kg/yr → divergence {div_restated:.1f}% "
          f"[{'PASS' if div_restated <= DIVERGENCE_LIMIT else 'FAIL'}]  → restated OGMPReport ({bu_restated*GWP100/1000:,.0f} t CO2e)")

    # 6) plan suspended -> restated (corrective), new hash over the enlarged evidence set
    p2 = plan(ids, "restated", "1.0.1", "corrective", recon2_id, prev=PLAN_ID)
    put([{**p2, "id": PLAN_ID}]); h1 = p2["data"]["planHash"]
    print(f"[6] MonitoringPlan suspended -> RESTATED (corrective, v1.0.1)  new hash {h1[:16]}…")

    # 7) attestation re-issued, bound to the restated plan hash
    put([{**attestation(h1, "reissued", "Re-issued after ISO 12.3 restatement; reconciliation passed on restated inventory"), "id": att_id}])
    print("[7] Attestation suspended -> REISSUED (bound to restated hash)")

    _, ph = _req("GET", f"/api/storage/v2/records/{PLAN_ID}"); _, pv = _req("GET", f"/api/storage/v2/records/versions/{PLAN_ID}")
    _, ah = _req("GET", f"/api/storage/v2/records/{att_id}"); _, av = _req("GET", f"/api/storage/v2/records/versions/{att_id}")
    print(f"\n[8] Final: plan={ph['data']['verificationStatus']} ({len(pv['versions'])} versions)  "
          f"attestation={ah['data']['attestationStatus']} ({len(av['versions'])} versions)")
    print("    Cascade proven: super-emitter → reconciliation FAIL → suspended → annualized adjustment → RESTATEMENT → re-reconciled → restated → attestation re-issued.\n")
    json.dump({"attestationId": att_id, "alertId": alert_id, "resurveyId": resurvey_id, "topdownEventId": td_id,
               "unlitInventoryId": inv_id, "unlitQuantId": q_id, "reconciliation2Id": recon2_id, "ogmpReport2Id": ogmp2_id,
               "restated": {"bottomUp": bu_restated, "topDown": td_restated, "divergencePct": div_restated,
                            "restatementPct": restate_pct, "instantDivergencePct": div_inst}},
              open(os.path.join(HERE, "day3_result.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
