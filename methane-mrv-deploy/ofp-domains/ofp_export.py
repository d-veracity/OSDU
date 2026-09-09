#!/usr/bin/env python3
"""
Export the OFP domain graph (from ofp_result.json) out of OSDU Storage into export/ofp/,
one JSON per record, plus the MethaneMonitoringPlan version trail, and add an `ofp` section
to export/_summary.json so the live console and the proof report can read it after the stack
is gone. Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); MRV = os.path.join(HERE, ".."); sys.path.insert(0, MRV)
from methane_lifecycle import _req
from ofp_grounding import KIND
EXPORT = os.path.join(MRV, "export"); OFP = os.path.join(EXPORT, "ofp"); os.makedirs(OFP, exist_ok=True)
res = json.load(open(os.path.join(HERE, "ofp_result.json")))
summary = json.load(open(os.path.join(EXPORT, "_summary.json")))

domains, n = {}, 0
for domain, ids in res["graph"].items():
    domains[domain] = {"count": len(ids), "kinds": {}, "records": []}
    for i in ids:
        s, r = _req("GET", f"/api/storage/v2/records/{i}")
        if s != 200: print(f"  MISSING {i} ({s})"); continue
        et = r["kind"].split("--")[1].split(":")[0]; domains[domain]["kinds"][et] = domains[domain]["kinds"].get(et, 0) + 1
        json.dump(r, open(os.path.join(OFP, i.replace(":", "_") + ".json"), "w"), indent=1)
        domains[domain]["records"].append({"id": i, "kind": r["kind"], "version": r["version"], "name": r["data"].get("name") or r["data"].get("entity_id") or r["data"].get("emission_statement_id")})
        n += 1
    print(f"  {domain:38s} {domains[domain]['count']:3d} records, {len(domains[domain]['kinds'])} kinds")

plan_id = summary["records"]["plan"]["id"]
s, vers = _req("GET", f"/api/storage/v2/records/versions/{plan_id}")
trail = []
for v in vers["versions"]:
    s, r = _req("GET", f"/api/storage/v2/records/{plan_id}/{v}")
    d = r["data"]; trail.append({"version": v, "status": d.get("verificationStatus"), "trigger": d.get("versionTrigger"), "ofpLinked": bool(d.get("ofpFacilityId"))})
json.dump(trail, open(os.path.join(OFP, "_plan_versions.json"), "w"), indent=1)

summary["ofp"] = {"records": n, "kinds": {e: "ofp:wks:" + k for e, k in KIND.items()}, "domains": {k: {"count": v["count"], "kinds": v["kinds"]} for k, v in domains.items()},
                  "ids": res["ids"], "rules": res["rules"], "traversal": res["traversal"], "totals": res["totals"],
                  "plan_versions": len(trail), "plan_trail": trail, "records": {k: v["records"] for k, v in domains.items()}}
json.dump(summary, open(os.path.join(EXPORT, "_summary.json"), "w"), indent=1)
print(f"exported {n} OFP records + {len(trail)}-version plan trail -> export/ofp/ ; _summary.json now carries an 'ofp' section")
