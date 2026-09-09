#!/usr/bin/env python3
"""
Complete, self-contained export of the claim #3 (Methane MRV + OFP data domains) proof from
the live OSDU platform, so the proof survives losing the stack.

What it captures, beyond the per-step exports (day4_export.py, ofp-domains/ofp_export.py):
  1. schemas-live/    every `ofp` schema body AS REGISTERED on the platform (all kinds), so the
                      whole model can be re-registered on any OSDU without regenerating.
  2. claim3/records/  the full body of EVERY record belonging to this proof, discovered by
                      sweeping the Search API kind by kind (not from a hand-kept id list), so
                      records written later by the live console are captured too.
  3. claim3/versions/ every immutable version body of every versioned record (the Monitoring
                      Plan trail, the attestation, reconciliations, anything with >1 version).
  4. claim3/_manifest.json  counts per kind/group, the id->file index, the platform identity,
                      and a referential-integrity report (which `osdu:` references resolve).

Ownership test for "belongs to this proof": record id contains `:mrv01-` (the OFP domain graph,
deterministic ids) OR data.facilityId == "MRV-01" (the methane activity records) OR the id is
named in export/_summary.json. Everything else on the platform (pre-existing demo data) is
listed in the manifest as `foreign` but not exported.

Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.  Re-runnable; overwrites in place.
"""
import os, sys, json, re, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from methane_lifecycle import _req, BASE, PART

EXPORT = os.path.join(HERE, "export")
C3 = os.path.join(EXPORT, "claim3"); RECS = os.path.join(C3, "records"); VERS = os.path.join(C3, "versions")
SCH = os.path.join(EXPORT, "schemas-live")
for d in (C3, RECS, VERS, SCH): os.makedirs(d, exist_ok=True)

SITE = "MRV-01"
summary = json.load(open(os.path.join(EXPORT, "_summary.json")))
KNOWN = {m["id"] for m in summary.get("records", {}).values()}
for dom in (summary.get("ofp", {}).get("records") or {}).values():
    KNOWN |= {r["id"] for r in dom}

def safe(name): return re.sub(r'[^A-Za-z0-9._-]', '_', name)

def ours(rid, data):
    return (":mrv01-" in rid) or (rid in KNOWN) or ((data or {}).get("facilityId") == SITE)

# ---------------- 1. schema registry ----------------
def export_schemas():
    """GET /schema/{kind} returns the bare JSON Schema document, NOT a registrable body.
    Re-wrap each one with its schemaInfo (from the list endpoint) so the files are valid
    Schema Service POST bodies and the model can be re-registered elsewhere as-is."""
    s, j = _req("GET", "/api/schema-service/v1/schema?authority=ofp&limit=1000")
    infos = {i["schemaIdentity"]["id"]: i for i in (j or {}).get("schemaInfos", [])}
    kinds = sorted(infos)
    got, failed = 0, []
    for kid in kinds:
        s, doc = _req("GET", "/api/schema-service/v1/schema/" + kid.replace(":", "%3A"))
        if s != 200 or not isinstance(doc, dict): failed.append(kid); continue
        body = doc if "schemaInfo" in doc else {"schemaInfo": infos[kid], "schema": doc}
        json.dump(body, open(os.path.join(SCH, safe(kid) + ".json"), "w"), indent=1); got += 1
    json.dump({"platform": BASE, "partition": PART, "authority": "ofp", "count": got, "kinds": kinds,
               "failed": failed}, open(os.path.join(SCH, "_index.json"), "w"), indent=1)
    print(f"  schemas: {got}/{len(kinds)} bodies exported" + (f" ({len(failed)} failed)" if failed else ""))
    return kinds

# ---------------- 2. sweep every record, kind by kind ----------------
def sweep(kinds):
    mine, foreign, per_kind = {}, [], {}
    for kid in kinds:
        s, j = _req("POST", "/api/search/v2/query", {"kind": kid, "limit": 1000, "returnedFields": ["id", "kind", "data.facilityId"]})
        if s >= 300: print(f"    search failed for {kid}: {s}"); continue
        results = (j or {}).get("results", []); total = (j or {}).get("totalCount", 0)
        if total > len(results): print(f"    NOTE {kid}: {total} total, {len(results)} returned (raise limit)")
        for r in results:
            rid = r["id"]
            if ours(rid, r.get("data")): mine[rid] = r["kind"]; per_kind[kid] = per_kind.get(kid, 0) + 1
            else: foreign.append({"id": rid, "kind": r["kind"]})
    return mine, foreign, per_kind

# ---------------- 3. full bodies + every version ----------------
def export_records(mine):
    index, versioned, missing = {}, {}, []
    for rid, kind in sorted(mine.items()):
        s, rec = _req("GET", f"/api/storage/v2/records/{rid}")
        if s != 200: missing.append({"id": rid, "status": s}); continue
        fn = safe(rid) + ".json"; json.dump(rec, open(os.path.join(RECS, fn), "w"), indent=1)
        index[rid] = {"kind": rec["kind"], "version": rec["version"], "file": f"records/{fn}"}
        s, vj = _req("GET", f"/api/storage/v2/records/versions/{rid}")
        vlist = (vj or {}).get("versions", []) if s == 200 else []
        if len(vlist) > 1:
            bodies = []
            for v in vlist:
                s, vb = _req("GET", f"/api/storage/v2/records/{rid}/{v}")
                if s == 200: bodies.append(vb)
            vfn = safe(rid) + ".versions.json"
            json.dump({"id": rid, "kind": kind, "versions": vlist, "bodies": bodies}, open(os.path.join(VERS, vfn), "w"), indent=1)
            index[rid]["versions"] = len(bodies); index[rid]["versionFile"] = f"versions/{vfn}"
            versioned[rid] = len(bodies)
    return index, versioned, missing

# ---------------- 4. referential integrity ----------------
def integrity(index):
    """Every `osdu:` reference inside exported record data must resolve to an exported record.
    A reference may carry a `:<version>` suffix (previousVersionId); strip it before matching,
    and check the named version was captured too."""
    refs, unresolved, dangling_versions = set(), [], []
    for meta in index.values():
        rec = json.load(open(os.path.join(C3, meta["file"])))
        for m in re.finditer(r'"(osdu:[A-Za-z0-9-]+--[A-Za-z0-9]+:[A-Za-z0-9._~:@+-]+)"', json.dumps(rec["data"])):
            refs.add(m.group(1))
    for r in sorted(refs):
        base, ver = r, None
        m = re.match(r'^(osdu:[A-Za-z0-9-]+--[A-Za-z0-9]+:[^:]+):(\d{10,})$', r)
        if m: base, ver = m.group(1), int(m.group(2))
        if base not in index: unresolved.append(r); continue
        if ver is not None:
            vf = index[base].get("versionFile")
            captured = json.load(open(os.path.join(C3, vf)))["versions"] if vf else [index[base]["version"]]
            if ver not in captured: dangling_versions.append(r)
    return len(refs), unresolved, dangling_versions

def main():
    print(f"### complete claim #3 export from {BASE} [{PART}]")
    kinds = export_schemas()
    if "--schemas-only" in sys.argv:
        print("  (--schemas-only: records untouched)"); return True
    print("  sweeping records kind by kind …")
    mine, foreign, per_kind = sweep(kinds)
    print(f"  records belonging to this proof: {len(mine)}  (foreign/pre-existing on the platform: {len(foreign)})")
    index, versioned, missing = export_records(mine)
    print(f"  exported {len(index)} record bodies; {len(versioned)} of them versioned "
          f"({sum(versioned.values())} version bodies)")
    if missing: print(f"  MISSING (GET failed): {missing}")
    nrefs, unresolved, dangling = integrity(index)
    print(f"  referential integrity: {nrefs} distinct osdu: references, {len(unresolved)} unresolved, "
          f"{len(dangling)} pointing at an uncaptured version")
    if unresolved: print("   unresolved:", *unresolved[:10], sep="\n     ")
    if dangling: print("   uncaptured versions:", *dangling[:10], sep="\n     ")
    manifest = {
        "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": {"base": BASE, "partition": PART},
        "proof": "claim #3 — Methane MRV (ISO 25624-1) + OFP data-domain grounding",
        "counts": {"schemas": len(kinds), "records": len(index), "versionedRecords": len(versioned),
                   "versionBodies": sum(versioned.values()), "foreignRecordsOnPlatform": len(foreign)},
        "recordsPerKind": {k: v for k, v in sorted(per_kind.items())},
        "versioned": versioned,
        "index": index,
        "integrity": {"references": nrefs, "unresolved": unresolved, "uncapturedVersions": dangling},
        "foreign": foreign,
        "restore": "Re-register schemas-live/*.json via Schema Service POST, then PUT claim3/records/*.json "
                   "(strip id/version to let the platform assign, or keep ids to preserve them).",
    }
    json.dump(manifest, open(os.path.join(C3, "_manifest.json"), "w"), indent=1)
    print(f"  -> {C3}/_manifest.json")
    return not unresolved and not dangling and not missing

if __name__ == "__main__": sys.exit(0 if main() else 1)
