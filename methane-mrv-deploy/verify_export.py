#!/usr/bin/env python3
"""
Verify the claim #3 proof OFFLINE, from export/ alone — no OSDU, no network.

Re-derives the headline numbers and the lifecycle from the exported record bodies and checks
them against the claims made in the proof report. If the platform is gone, this is what shows
the evidence still hangs together.

  python3 verify_export.py
Exit 0 = every check passed.
"""
import os, sys, json, glob, re

HERE = os.path.dirname(os.path.abspath(__file__)); EXPORT = os.path.join(HERE, "export")
C3 = os.path.join(EXPORT, "claim3"); RECS = os.path.join(C3, "records"); VERS = os.path.join(C3, "versions")
GWP100, HOURS = 28.0, 8760

man = json.load(open(os.path.join(C3, "_manifest.json")))
records = {}
for f in glob.glob(os.path.join(RECS, "*.json")):
    r = json.load(open(f)); records[r["id"]] = r
def of_kind(entity):
    return [r for r in records.values() if f"--{entity}:" in r["kind"]]
def data(r): return r.get("data", {})

checks = []
def check(name, ok, detail): checks.append((name, bool(ok), detail)); return ok

# ---------- 1. the export is internally complete ----------
check("Export self-contained (manifest count == files on disk)",
      man["counts"]["records"] == len(records), f"{man['counts']['records']} claimed, {len(records)} files")
check("Referential integrity recorded clean",
      not man["integrity"]["unresolved"] and not man["integrity"]["uncapturedVersions"],
      f"{man['integrity']['references']} references, 0 unresolved")
check("Schema bodies exported for every registered kind",
      len(glob.glob(os.path.join(EXPORT, "schemas-live", "ofp_wks_*.json"))) == man["counts"]["schemas"],
      f"{man['counts']['schemas']} kinds")

# ---------- 2. bottom-up inventory re-computed from OFP EmissionStatements ----------
stmts = {data(r).get("emission_statement_id"): r for r in of_kind("EmissionStatement") if ":mrv01-" in r["id"]}
src = {k: v for k, v in stmts.items() if k and k.startswith("stmt-src-")}
bu_sum = sum(data(v).get("quantity", 0) for v in src.values())
bu_total_stmt = data(stmts.get("stmt-bottomup-total", {})).get("quantity")
check("Five source-level EmissionStatements present", len(src) == 5, f"{len(src)} statements")
check("Σ source statements == the bottom-up total statement",
      bu_total_stmt is not None and abs(bu_sum - bu_total_stmt) < 1, f"Σ={bu_sum:,.0f} kg vs total={bu_total_stmt:,.0f} kg")
check("Bottom-up total is the ISO Formula (1) figure (156,300 kg)", abs(bu_sum - 156300) < 1, f"{bu_sum:,.0f} kg")

# each source statement's quantity must equal EF x N x t from its own argument values
args = {}
for r in of_kind("EmissionArgumentValue"):
    m = re.search(r"mrv01-val-(src-[a-z]+)-(ef|n|t)$", r["id"])
    if m: args.setdefault(m.group(1), {})[m.group(2)] = data(r).get("value")
formula_ok, formula_detail = True, []
for sid, a in sorted(args.items()):
    st = stmts.get(f"stmt-{sid}")
    if not st or not all(k in a for k in ("ef", "n", "t")): formula_ok = False; continue
    expect = a["ef"] * a["n"] * a["t"]; got = data(st).get("quantity")
    if abs(expect - got) > 1: formula_ok = False
    formula_detail.append(f"{sid}: {a['ef']}x{a['n']}x{a['t']}={expect:,.0f}")
check("Every source statement re-computes as E = EF x N x t (ISO Formula 1)", formula_ok and len(args) == 5,
      "; ".join(formula_detail))

# ---------- 3. reconciliation ----------
td_stmt = data(stmts.get("stmt-topdown", {})).get("quantity")
check("Top-down site statement present (19.5 kg/h annualized)",
      td_stmt is not None and abs(td_stmt - 19.5 * HOURS) < 1, f"{td_stmt:,.0f} kg")
div = abs(bu_sum - td_stmt) / td_stmt * 100 if td_stmt else None
check("Reconciliation divergence at verification = 8.5% <= 20%", div is not None and abs(div - 8.5) < 0.2 and div <= 20,
      f"|BU-TD|/TD = {div:.1f}%")
recons = sorted(of_kind("ReconciliationResult"), key=lambda r: data(r).get("divergencePercent", 0))
restated = [r for r in recons if abs(data(r).get("divergencePercent", 0) - 6.81) < 0.05]
check("Restated reconciliation recorded at 6.8% (passed)", restated and data(restated[0]).get("reconciliationVerdict") == "passed",
      f"{len(recons)} ReconciliationResult records on the stack export")

# ---------- 4. the gate, as OFP Data Verification ----------
dq = [r for r in of_kind("DataQuality") if ":mrv01-dq-" in r["id"]]
runs = {}
for r in dq:
    dm = data(r).get("dimension_metrics", [])
    if dm and dm[0].startswith("run="): runs[dm[0].split("=", 1)[1]] = data(r).get("total_score")
check("Three gate runs recorded as DataQuality assessments", set(runs) == {"verify", "anomaly", "restated"}, str(runs))
check("Gate scores: verify 100%, anomaly 83.3% (5/6), restated 100%",
      runs.get("verify") == 100.0 and abs(runs.get("anomaly", 0) - 83.3) < 0.1 and runs.get("restated") == 100.0, str(runs))
failing = [r for r in dq if data(r).get("total_score") == 0.0]
check("Exactly one failing constraint evaluation, and it is SiteLevelReconciliation",
      len(failing) == 1 and "SiteLevelReconciliation" in data(failing[0])["dimension_metrics"][0],
      data(failing[0])["dimension_metrics"][0] if failing else "none")
rulesets = [r for r in of_kind("DataQualityRuleSet") if ":mrv01-" in r["id"]]
check("Rule set carries the 6 constraints as DataQualityRules",
      rulesets and len(data(rulesets[0]).get("data_rules", [])) == 6,
      f"{len(data(rulesets[0]).get('data_rules', [])) if rulesets else 0} rules")
# the evaluated record each assessment points at must itself be in the export
ev_ok = all(data(r).get("evaluated_record_id") in records for r in dq)
check("Every DataQuality assessment's evaluated record is in the export", ev_ok, f"{len(dq)} assessments")

# ---------- 5. lifecycle: the immutable plan trail ----------
plan_v = glob.glob(os.path.join(VERS, "*MethaneMonitoringPlan*.versions.json"))
trail = []
if plan_v:
    pv = json.load(open(plan_v[0])); trail = [b["data"].get("verificationStatus") for b in pv["bodies"]]
check("Monitoring Plan lifecycle draft -> underReview -> verified -> suspended -> restated",
      trail[:5] == ["draft", "underReview", "verified", "suspended", "restated"], " -> ".join(trail[:5]))
check("Plan versions are immutable and all captured", len(trail) >= 5, f"{len(trail)} versions in the export")
linked = [b for b in (pv["bodies"] if plan_v else []) if b["data"].get("ofpFacilityId")]
check("Final plan version links the OFP graph (facility/report/rule set/assurance)",
      linked and all(linked[-1]["data"].get(k) in records for k in
                     ["ofpFacilityId", "ofpOrganizationId", "ofpEmissionReportId", "ofpDataQualityRuleSetId", "ofpReportingAssuranceId"]),
      "all four OFP links resolve inside the export" if linked else "not linked")

# ---------- 6. attestation ----------
att = of_kind("MethaneAttestation")
att_v = glob.glob(os.path.join(VERS, "*MethaneAttestation*.versions.json"))
statuses = [b["data"].get("attestationStatus") for b in json.load(open(att_v[0]))["bodies"]] if att_v else []
check("Attestation lifecycle issued -> suspended -> reissued", statuses[:3] == ["issued", "suspended", "reissued"], " -> ".join(statuses[:3]))
check("Attestation is bound to a plan hash", att and data(att[0]).get("planHash"), (data(att[0]).get("planHash") or "")[:24] + "…" if att else "none")
vc = [r for r in of_kind("VerifiableCredential") if ":mrv01-" in r["id"]]
check("Attestation also expressed as an OFP VerifiableCredential", len(vc) == 1 and data(vc[0]).get("issuer_did"),
      data(vc[0]).get("issuer_did") if vc else "none")

# ---------- 7. the five OFP domains ----------
doms = man.get("recordsPerKind", {})
groups = {"reference-data": 0, "master-data": 0, "work-product-component": 0}
for k, n in doms.items():
    for g in groups:
        if f":{g}--" in k: groups[g] += n
check("OFP graph spans all three OSDU groups", all(v > 0 for v in groups.values()), str(groups))
check("Records span >= 60 distinct OFP kinds", len(doms) >= 60, f"{len(doms)} kinds carry records")

# ---------- report ----------
w = max(len(n) for n, _, _ in checks)
print(f"### offline verification of claim #3 from export/ ({len(records)} records, no network)\n")
for name, ok, detail in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<{w}}  {detail}")
passed = sum(1 for _, ok, _ in checks if ok)
print(f"\n### {passed}/{len(checks)} checks passed")
sys.exit(0 if passed == len(checks) else 1)
