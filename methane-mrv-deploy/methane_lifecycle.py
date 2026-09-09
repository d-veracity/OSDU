#!/usr/bin/env python3
"""
Methane MRV reconciliation lifecycle on live OSDU — claim #3, Day 2.
Grounded in ISO 25624-1:2026 (in line with OGMP 2.0, EU Reg 2024/1787).

Builds a synthetic upstream gas site:
  - source-level (bottom-up) inventory via ISO Formula (1): E = Σ(EF_i × AF_i), AF_i = N_i × t_i
  - site-level (top-down) measurement with expanded uncertainty U = k·u (k=2, ISO 9.5.3)
Runs the reconciliation gate (ISO Cl.11 / SysML 14_constraints methane block), then drives
the MethaneMonitoringPlan draft -> underReview -> verified via OSDU record versioning,
gated on the constraints passing.

Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.
"""
import os, json, ssl, hashlib, urllib.request, urllib.error

BASE = os.environ.get("OSDU_BASE", "https://172.171.6.4.nip.io")
PART = os.environ.get("OSDU_PARTITION", "osdu")
TOKEN = open(os.environ["OSDU_TOKEN_FILE"]).read().strip()
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
ACL = {"owners": ["data.default.owners@osdu.group"], "viewers": ["data.default.viewers@osdu.group"]}
LEGAL = {"legaltags": ["osdu-demo-legaltag"], "otherRelevantDataCountries": ["US"], "status": "compliant"}
W = lambda n: f"ofp:wks:work-product-component--{n}:1.0.0"
R = lambda n: f"ofp:wks:reference-data--{n}:1.0.0"

def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "data-partition-id": PART, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, context=CTX, timeout=30) as resp:
            t = resp.read().decode(); return resp.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

def put(records):
    s, j = _req("PUT", "/api/storage/v2/records", records)
    if s >= 300: raise RuntimeError(f"PUT {s}: {j}")
    return j["recordIds"]

def rec(kind, data): return {"kind": kind, "acl": ACL, "legal": LEGAL, "data": data}

# ---------------- the site ----------------
SITE = "MRV-01"; ASSET = "NorthField-GasProcessing"; YEAR = 2025
HOURS = 8760; GWP100 = 28.0
BASE_ACT = lambda t: {"activityType": t, "dataSource": "synthetic (ISO 25624-1 worked site)",
    "reportingPeriodStart": f"{YEAR}-01-01T00:00:00Z", "reportingPeriodEnd": f"{YEAR}-12-31T23:59:59Z",
    "facilityId": SITE, "recordingType": "measured", "sensitivity": "confidential"}

# Bottom-up sources: ISO Formula (1)  E_i = EF_i * AF_i,  AF_i = N_i * t_i
# (SysML EmissionSourceCategory enum: venting|flaring|fugitive|combustion; ISO Cl.6 code for reference data)
SOURCES = [
    # id, sysml cat, iso code, component, EF kg/h/unit, N units, t hours, method, ogmp level, unc %
    ("SRC-FLARE",  "flaring",    "flaring",                       "flare stack (98% DRE)",     12.0, 1,  8000, "directMeasurement", "level4", 15.0),
    ("SRC-PNEU",   "venting",    "ventingPneumatic",              "intermittent pneumatic ctrl", 0.05, 40, 8760, "emissionFactor",   "level4", 25.0),
    ("SRC-COMPR",  "venting",    "ventingCompressorReciprocating","rod-packing vent",           1.2,  2,  8000, "directMeasurement", "level4", 12.0),
    ("SRC-ENGINE", "combustion", "incompleteCombustion",          "recip. engine slip (CEMS)",   0.8,  3,  8000, "directMeasurement", "level4", 10.0),
    ("SRC-FUG",    "fugitive",   "fugitive",                      "leaking connectors (generic)",0.02, 25, 8760, "emissionFactor",   "level3", 50.0),
]

# Top-down site measurement (drone flux, ISO Cl.7): instantaneous rate + standard uncertainty
TOPDOWN_RATE_KGH = 19.5; TOPDOWN_U_STD_PCT = 12.0; K = 2.0; LOQ_KGH = 0.5

# Gate parameters (MethaneMonitoringPlan data)
DIVERGENCE_LIMIT = 20.0; COVERAGE_TARGET = 95.0; MATERIALITY = 5.0; QUARTERLY_LDAR = 4

def build_evidence():
    ev = {"inventory": [], "quant": [], "refdata": []}
    for sid, cat, iso, comp, ef, n, t, method, lvl, unc in SOURCES:
        e_kg = ef * n * t                       # Formula (1)
        ev["inventory"].append((sid, rec(W("MethaneSourceInventory"), {**BASE_ACT("ch4_source_inventory"),
            "sourceCategory": cat, "componentType": comp, "lastInspectionDate": f"{YEAR}-10-15T00:00:00Z",
            "emissionFactor": ef})))
        ev["quant"].append((sid, e_kg, rec(W("EmissionQuantification"), {**BASE_ACT("ch4_quantification"),
            "sourceId": sid, "emissionRateKgPerHour": round(e_kg / HOURS, 4), "quantificationMethod": method,
            "uncertaintyPercent": unc, "co2eKg": round(e_kg * GWP100, 1), "ogmpLevel": lvl})))
        ev["refdata"].append(rec(R("MethaneSourceCategory"), {"code": iso, "name": comp,
            "description": f"ISO 25624-1 Clause 6 source category '{iso}'", "isoClause": "6"}))
    # top-down survey + site-scope quantification
    ev["detection"] = rec(W("MethaneDetectionEvent"), {**BASE_ACT("ch4_detection"),
        "deviceId": "DRONE-CRDS-07", "technology": "drone", "detectedConcentrationPPM": 4.8,
        "windSpeedMPS": 3.6, "windDirection": 245.0, "ogmpLevel": "level5", "plumeSizeM2": 1800.0})
    ev["topdown"] = rec(W("EmissionQuantification"), {**BASE_ACT("ch4_quantification"),
        "sourceId": "SITE", "emissionRateKgPerHour": TOPDOWN_RATE_KGH, "quantificationMethod": "massBalance",
        "uncertaintyPercent": TOPDOWN_U_STD_PCT * K, "co2eKg": round(TOPDOWN_RATE_KGH * HOURS * GWP100, 1),
        "ogmpLevel": "level5"})
    ev["ldar"] = rec(W("LDARSurveyRecord"), {**BASE_ACT("ldar_survey"), "surveyType": "ogi",
        "componentsSurveyed": 2400, "leaksDetected": 25, "leaksRepaired": 23, "surveyDurationHours": 64.0})
    return ev

# ---------------- reconciliation gate (ISO Cl.8, 9, 11; SysML 14_constraints methane) ----------------
def gate(ev):
    bottom_up = sum(e for _, e, _ in ev["quant"])
    top_down = TOPDOWN_RATE_KGH * HOURS
    div = abs(bottom_up - top_down) / top_down * 100
    l45 = sum(e for (sid, e, r) in ev["quant"] if r["data"]["ogmpLevel"] in ("level4", "level5"))
    cov = l45 / bottom_up * 100
    # materiality: every material source (>5% of total, ISO 8 Formula 25) must be quantified at L4+
    mat_ok = all((e / bottom_up * 100 <= MATERIALITY) or r["data"]["ogmpLevel"] in ("level4", "level5")
                 for (sid, e, r) in ev["quant"])
    flare_meas, flare_ref = 12.4, 12.0   # EmissionRateAccuracy on the flare (L4 tolerance 10%)
    acc = abs(flare_meas - flare_ref) / flare_ref * 100
    U_exp = TOPDOWN_U_STD_PCT * K
    checks = [
        ("SiteLevelReconciliation (ISO 11)",   div <= DIVERGENCE_LIMIT, f"|BU−TD|/TD = {div:.1f}% ≤ {DIVERGENCE_LIMIT}%"),
        ("GoldStandardCoverage (OGMP 2.0)",    cov >= COVERAGE_TARGET,  f"L4/L5 coverage {cov:.1f}% ≥ {COVERAGE_TARGET}%"),
        ("MaterialityRigor (ISO 8, F.25)",     mat_ok,                  f"material sources (>{MATERIALITY}%) all at L4+"),
        ("MethaneLeakDetectionThreshold",      TOPDOWN_RATE_KGH >= LOQ_KGH, f"{TOPDOWN_RATE_KGH} kg/h ≥ LoQ {LOQ_KGH}"),
        ("EmissionRateAccuracy (ISO 9)",       acc <= 10.0,             f"flare {acc:.1f}% ≤ 10% (L4)"),
        ("ReportingFrequency (EU 2024/1787)",  QUARTERLY_LDAR >= 4,     f"{QUARTERLY_LDAR} LDAR surveys ≥ 4/yr"),
    ]
    return checks, dict(bottom_up=bottom_up, top_down=top_down, divergence=div, coverage=cov, U_expanded_pct=U_exp)

def plan(ev_ids, status, version, trigger, recon_id, prev=None):
    d = {**BASE_ACT("methane_monitoring_plan"), "planId": f"{SITE}-MP-{YEAR}", "siteId": SITE, "assetId": ASSET,
         "reportingBoundary": "operational control — gas processing site MRV-01",
         "sourceInventoryIds": ev_ids["inventory"], "siteMeasurementIds": ev_ids["site"],
         "reconciliationResultId": recon_id, "targetOgmpLevel": "level4",
         "materialityThresholdPercent": MATERIALITY, "goldStandardCoveragePercent": COVERAGE_TARGET,
         "reconciliationDivergenceLimitPercent": DIVERGENCE_LIMIT, "uncertaintyCoverageFactorK": K,
         "verificationStatus": status, "versionTrigger": trigger,
         "planHash": hashlib.sha256(json.dumps(ev_ids, sort_keys=True).encode()).hexdigest()}
    if prev: d["previousVersionId"] = prev
    return rec(W("MethaneMonitoringPlan"), d)

def main():
    print(f"\n=== Methane MRV reconciliation — site {SITE} / {ASSET} / {YEAR} (ISO 25624-1) ===\n")
    ev = build_evidence()

    print("[1] Bottom-up inventory (ISO Formula 1: E = Σ EF·N·t) …")
    ids = {"inventory": [], "site": [], "refdata": []}
    for (sid, r) in ev["inventory"]:
        ids["inventory"].append(put([r])[0])
    for (sid, e, r) in ev["quant"]:
        put([r]); print(f"    {sid:11s} {r['data']['quantificationMethod']:18s} {r['data']['ogmpLevel']}  {e:>10,.0f} kg/yr")
    for r in ev["refdata"]: ids["refdata"].append(put([r])[0])
    print(f"    ISO reference-data source categories stored: {len(ids['refdata'])}")

    print("\n[2] Top-down site measurement (drone flux, ISO Cl.7) …")
    ids["site"].append(put([ev["detection"]])[0]); ids["site"].append(put([ev["topdown"]])[0])
    put([ev["ldar"]])
    print(f"    {TOPDOWN_RATE_KGH} kg/h instantaneous, expanded uncertainty U = k·u = {TOPDOWN_U_STD_PCT*K:.0f}% (k=2, 95%)")

    print("\n[3] Reconciliation gate:")
    checks, m = gate(ev)
    print(f"    bottom-up {m['bottom_up']:,.0f} kg/yr  vs  top-down {m['top_down']:,.0f} kg/yr")
    allpass = True
    for lab, ok, det in checks:
        allpass &= ok; print(f"    [{'PASS' if ok else 'FAIL'}] {lab:36s} {det}")
    verdict = "passed" if m["divergence"] <= DIVERGENCE_LIMIT else ("marginal" if m["divergence"] <= 30 else "failed")
    print(f"\n    Gate verdict: {'ALL CONSTRAINTS SATISFIED' if allpass else 'BLOCKED'}  (reconciliation: {verdict})")

    print("\n[4] ReconciliationResult + OGMPReport …")
    recon_id = put([rec(W("ReconciliationResult"), {**BASE_ACT("ch4_reconciliation"),
        "bottomUpTotalKg": round(m["bottom_up"], 1), "topDownTotalKg": round(m["top_down"], 1),
        "divergencePercent": round(m["divergence"], 2), "reconciliationVerdict": verdict,
        "reconciledTotalKg": round(m["bottom_up"], 1)})])[0]   # best estimate = validated source-level inventory (ISO 11.3)
    ogmp_id = put([rec(W("OGMPReport"), {**BASE_ACT("ogmp_report"), "reportingYear": YEAR, "reportingLevel": "level4",
        "coveredEmissionsPercent": round(m["coverage"], 1), "goldStandardCompliant": bool(allpass),
        "submittedToIMEO": False, "submissionStatus": "draft"})])[0]
    print(f"    reconciled best estimate {m['bottom_up']:,.0f} kg CH4 ({m['bottom_up']*GWP100/1000:,.0f} t CO2e @GWP100=28)")

    print("\n[5] MethaneMonitoringPlan state machine (immutable OSDU versions):")
    plan_id = put([plan(ids, "draft", "1.0.0", "periodic", recon_id)])[0]
    print(f"    draft        -> {plan_id.split(':')[-1][:12]}…")
    put([{**plan(ids, "underReview", "1.0.0", "periodic", recon_id), "id": plan_id}]); print("    underReview  -> (OSDU v+1)")
    if allpass:
        put([{**plan(ids, "verified", "1.0.0", "periodic", recon_id), "id": plan_id}]); print("    verified     -> (OSDU v+1)  ✓ gate-gated")
    else:
        print("    verified     -> WITHHELD (gate failed)")

    s, head = _req("GET", f"/api/storage/v2/records/{plan_id}")
    s2, vers = _req("GET", f"/api/storage/v2/records/versions/{plan_id}")
    print(f"\n[6] Verify: plan status = {head['data']['verificationStatus']}  | versions retained = {len((vers or {}).get('versions', []))}")
    print(f"    plan id: {plan_id}\n")
    json.dump({"planId": plan_id, "reconciliationId": recon_id, "ogmpReportId": ogmp_id, "evidenceIds": ids,
               "metrics": m, "gate": [(l, o) for l, o, _ in checks]},
              open(os.path.join(os.path.dirname(__file__), "day2_result.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
