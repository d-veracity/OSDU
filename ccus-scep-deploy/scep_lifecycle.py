#!/usr/bin/env python3
"""
SCEP certification lifecycle on the live cimpl-stack OSDU — Day 2.

Decatur-modeled (Illinois Basin Decatur Project: Mount Simon Sandstone reservoir, Eau Claire
Shale caprock, ~1 Mt CO2, Class VI). Builds a linked storage-complex evidence set, stores it
in OSDU, runs the EPA UIC Class VI certification gate (the SysML 14_constraints.sysml checks),
and — only if the gate passes — drives a SCEPVersionSnapshot draft -> underReview -> certified
via OSDU record versioning (each transition an immutable OSDU version = audit trail).

Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.
"""
import os, json, ssl, hashlib, time, urllib.request, urllib.error

BASE = os.environ.get("OSDU_BASE", "https://172.171.6.4.nip.io")
PART = os.environ.get("OSDU_PARTITION", "osdu")
TOKEN = open(os.environ["OSDU_TOKEN_FILE"]).read().strip()
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
ACL = {"owners": ["data.default.owners@osdu.group"], "viewers": ["data.default.viewers@osdu.group"]}
LEGAL = {"legaltags": ["osdu-demo-legaltag"], "otherRelevantDataCountries": ["US"], "status": "compliant"}
K = lambda n: f"ofp:wks:work-product-component--{n}:1.0.0"

def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "data-partition-id": PART, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, context=CTX, timeout=30) as resp:
            t = resp.read().decode(); return resp.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, (json.loads(e.read().decode() or "{}"))

def put(records):
    s, j = _req("PUT", "/api/storage/v2/records", records if isinstance(records, list) else [records])
    if s >= 300: raise RuntimeError(f"PUT {s}: {j}")
    return j["recordIds"]

def rec(kind, data): return {"kind": K(kind), "acl": ACL, "legal": LEGAL, "data": data}

# ---------------- Decatur-modeled evidence set ----------------
SITE = "IBDP-Decatur"; WELL = "CCS1-Decatur-ClassVI"; RES = "MountSimon-SS"; SEAL = "EauClaire-SH"
BASE_ACT = lambda t: {"activityType": t, "dataSource": "IBDP synthetic (Decatur-modeled)",
    "reportingPeriodStart": "2011-11-01T00:00:00Z", "reportingPeriodEnd": "2014-11-30T23:59:59Z",
    "facilityId": WELL, "recordingType": "measured", "sensitivity": "confidential"}

def build_evidence():
    ev = {}
    ev["baseline"] = rec("PreInjectionBaselineRecord", {**BASE_ACT("pre_injection_baseline"),
        "baselineId": f"{SITE}-BL-01", "reservoirPressureMPa": 21.8, "groundwaterChemistry": "TDS 200k ppm brine",
        "seismicBaselineSurveyId": "3D-2010-Decatur", "insarBaselineMmPerYear": 1.2, "soilGasBaselinePPM": 410,
        "ecosystemBaseline": "row-crop agriculture", "surveyCompletionDate": "2011-08-15T00:00:00Z"})
    ev["structmap"] = rec("StructureMapRecord", {**BASE_ACT("structure_map_interpretation"),
        "mapId": f"{SITE}-SM-01", "mapType": "depth_structure", "seismicSurveyId": "3D-2010-Decatur",
        "horizonName": "Top Mount Simon", "depthConversionMethod": "checkshot-calibrated",
        "spatialResolutionM": 25.0, "interpretationConfidence": 0.9})
    ev["integrity"] = rec("ContainmentIntegrityAssessment", {**BASE_ACT("containment_integrity"),
        "caprockSealingEffectiveness": "effective", "faultSealingBehavior": "sealing",
        "caprockEntryPressureMPa": 12.5, "co2BuoyancyPressureMPa": 3.1, "sealIntegrityIndex": 0.94,
        "reactivationRiskScore": 0.12, "assessmentConfidence": 0.88})
    ev["injection"] = rec("CO2InjectionRecord", {**BASE_ACT("co2_injection"),
        "wellId": WELL, "injectionRateTPA": 333000, "wellheadPressureMPa": 9.6,
        "bottomholePressureMPa": 31.5, "cumulativeInjectedTonnes": 999000})
    ev["plume"] = rec("CO2PlumeObservation", {**BASE_ACT("plume_observation"),
        "observationMethod": "seismic", "lateralExtentKm2": 7.8, "migrationRateMPerYear": 210.0,
        "depthM": 2130.0, "modelComparisonScore": 0.86})
    ev["storage"] = rec("CO2StorageRecord", {**BASE_ACT("co2_storage"),
        "reservoirId": RES, "storedMassTonnes": 985000, "leakageRateKgPerYear": 4.0,
        "plumeExtentKm2": 7.8, "containmentStatus": "stabilized"})
    ev["massbal"] = rec("CO2MassBalanceRecord", {**BASE_ACT("co2_mass_balance"),
        "injectedMassTonnes": 999000, "storedMassTonnes": 985000, "leakedMassTonnes": 0.004,
        "dissolvedMassTonnes": 11200, "mineralizedMassTonnes": 2799.996,
        "surfaceDensityKgPerM3": 1.98, "reservoirDensityKgPerM3": 700.0, "reservoirVolumeM3": 1.41e6,
        "allocationMethod": "mass", "balanceUncertaintyPercent": 2.0})
    ev["monitor"] = rec("ContainmentAssessment", {**BASE_ACT("containment_assessment"),
        "assessmentType": "pressure", "baselineValue": 21.8, "measuredValue": 31.5,
        "deviationPercent": 44.5, "verdict": "pass"})
    return ev

# ---------------- EPA UIC Class VI certification gate (SysML 14_constraints.sysml) ----------------
FRACTURE_PRESSURE_MPA = 38.0   # Mount Simon frac pressure at depth (demo)
PERMITTED_AOR_KM2 = 30.0       # Class VI Area of Review
WELL_INTEGRITY_SCORE = 0.98    # from MIT / cement bond (demo)
WELL_INTEGRITY_MIN = 0.95
MAX_LEAKAGE_PCT = 0.0001       # ISO 27914 / Class VI 0.01%/yr
MASSBAL_TOL_PCT = 0.5

def class_vi_gate(ev):
    d = {k: v["data"] for k, v in ev.items()}
    checks = []
    # InjectionPressureLimit: bottomhole <= fracture*(1-margin)
    bh = d["injection"]["bottomholePressureMPa"]; lim = FRACTURE_PRESSURE_MPA * (1 - 0.10)
    checks.append(("InjectionPressureLimit (Class VI)", bh <= lim, f"{bh} MPa <= {lim:.1f} MPa (90% frac)"))
    # PlumeMigrationBoundary: plume <= AoR
    pl = d["plume"]["lateralExtentKm2"]
    checks.append(("PlumeMigrationBoundary (Class VI AoR)", pl <= PERMITTED_AOR_KM2, f"{pl} km² <= {PERMITTED_AOR_KM2} km²"))
    # WellIntegrityThreshold
    checks.append(("WellIntegrityThreshold (Class VI)", WELL_INTEGRITY_SCORE >= WELL_INTEGRITY_MIN,
        f"{WELL_INTEGRITY_SCORE} >= {WELL_INTEGRITY_MIN}"))
    # CO2StoragePermanence: leak/(stored*1000) <= max
    lk = d["storage"]["leakageRateKgPerYear"]; st = d["storage"]["storedMassTonnes"]
    perm = lk / (st * 1000)
    checks.append(("CO2StoragePermanence (ISO 27914)", perm <= MAX_LEAKAGE_PCT, f"{perm:.2e} <= {MAX_LEAKAGE_PCT}"))
    # MassBalanceConservation
    m = d["massbal"]; inj = m["injectedMassTonnes"]
    resid = abs(inj - (m["storedMassTonnes"] + m["leakedMassTonnes"] + m["dissolvedMassTonnes"] + m["mineralizedMassTonnes"]))
    mb = (resid / inj) <= (MASSBAL_TOL_PCT / 100)
    checks.append(("MassBalanceConservation", mb, f"residual {resid:.3f} t, {resid/inj:.2e} <= {MASSBAL_TOL_PCT/100}"))
    # SealIntegrity: entry >= buoyancy*(1+margin)
    ip = d["integrity"]; seal = ip["caprockEntryPressureMPa"] >= ip["co2BuoyancyPressureMPa"] * 1.5
    checks.append(("SealIntegrityConstraint", seal, f"entry {ip['caprockEntryPressureMPa']} >= 1.5×buoyancy {ip['co2BuoyancyPressureMPa']*1.5:.1f} MPa"))
    # CarbonClaimReconciliation: claims <= verified stored
    claims = 985000
    checks.append(("CarbonClaimReconciliation", claims <= st, f"{claims} t claimed <= {st} t stored"))
    return checks

# ---------------- SCEP snapshot + state machine ----------------
def snapshot(evidence_ids, status, version, prev_snap_id=None, trigger="periodic"):
    pack = {"scepId": f"{SITE}-SCEP-01", "version": version, "versionTrigger": trigger,
        "evidenceArtifactIds": evidence_ids, "certificationStatusAtSnapshot": status,
        **BASE_ACT("scep_version_snapshot")}
    pack["snapshotHash"] = hashlib.sha256(json.dumps(evidence_ids, sort_keys=True).encode()).hexdigest()
    if prev_snap_id: pack["previousVersionSnapshotId"] = prev_snap_id
    return rec("SCEPVersionSnapshot", pack)

def main():
    print(f"\n=== SCEP certification lifecycle — {SITE} (Class VI) ===\n")
    ev = build_evidence()
    print(f"[1] Storing {len(ev)} evidence records to OSDU …")
    ids = {}
    for name, r in ev.items():
        rid = put([r])[0]; ids[name] = rid
        print(f"    {name:10s} {r['kind'].split('--')[1]:35s} -> {rid.split(':')[-1][:12]}…")
    evidence_ids = list(ids.values())

    print("\n[2] EPA UIC Class VI certification gate:")
    checks = class_vi_gate(ev)
    allpass = True
    for label, ok, detail in checks:
        allpass &= ok
        print(f"    [{'PASS' if ok else 'FAIL'}] {label:38s} {detail}")
    print(f"\n    Gate verdict: {'ALL CONSTRAINTS SATISFIED' if allpass else 'BLOCKED — cannot certify'}")

    print("\n[3] Driving SCEP state machine (immutable OSDU versions):")
    # draft
    snap_id = put([snapshot(evidence_ids, "draft", "1.0.0")])[0]
    print(f"    draft        -> {snap_id.split(':')[-1][:12]}… (v?)")
    # underReview  (same id => new OSDU version)
    put([{**snapshot(evidence_ids, "underReview", "1.0.0"), "id": snap_id}])
    print(f"    underReview  -> {snap_id.split(':')[-1][:12]}… (OSDU v+1)")
    # certified — ONLY if the Class VI gate passed
    if allpass:
        put([{**snapshot(evidence_ids, "certified", "1.0.0"), "id": snap_id}])
        print(f"    certified    -> {snap_id.split(':')[-1][:12]}… (OSDU v+1)  ✓ gate-gated")
    else:
        print("    certified    -> WITHHELD (gate failed)")

    # verify head state + version history
    s, head = _req("GET", f"/api/storage/v2/records/{snap_id}")
    print(f"\n[4] Verify: SCEP head status = {head['data']['certificationStatusAtSnapshot']}  (OSDU version {head.get('version')})")
    s, vers = _req("GET", f"/api/storage/v2/records/versions/{snap_id}")
    if s < 300 and vers: print(f"    immutable version history: {len(vers.get('versions', []))} versions retained")
    print(f"\n    SCEP id: {snap_id}")
    print(f"    evidence artifacts: {len(evidence_ids)}  |  snapshotHash bound\n")
    json.dump({"scepId": snap_id, "evidenceIds": ids, "gate": [(l, o) for l, o, _ in checks]},
              open(os.path.join(os.path.dirname(__file__), "day2_result.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
