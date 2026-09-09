#!/usr/bin/env python3
"""
Restore the claim #3 proof onto ANY OSDU platform from export/ alone.

Replays the export in dependency order: schemas first (reference-data, then master-data, then
work-product-component), then the record bodies. Only the head version of each record is
restored; the immutable version trail is history and cannot be replayed (it is preserved as
evidence in export/claim3/versions/).

  OSDU_BASE=https://<gateway> OSDU_PARTITION=<p> OSDU_TOKEN_FILE=<file> python3 restore_claim3.py [--dry-run]
  --schemas-only / --records-only  restrict the phase
  --keep-ids                       restore records under their original ids (default: yes)

Prerequisites on the target: a legal tag matching the records' `legal.legaltags`
(default `osdu-demo-legaltag`) and the ACL groups in `acl` must exist, or Storage will 400.
Override with LEGALTAG / ACL_OWNERS / ACL_VIEWERS env vars.
"""
import os, sys, json, glob, re

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from methane_lifecycle import _req, BASE, PART
EXPORT = os.path.join(HERE, "export"); C3 = os.path.join(EXPORT, "claim3")
SCH = os.path.join(EXPORT, "schemas-live"); RECS = os.path.join(C3, "records")
DRY = "--dry-run" in sys.argv
ORDER = ["reference-data", "master-data", "work-product-component"]
LEGALTAG = os.environ.get("LEGALTAG"); OWNERS = os.environ.get("ACL_OWNERS"); VIEWERS = os.environ.get("ACL_VIEWERS")

def phase_schemas():
    files = sorted(glob.glob(os.path.join(SCH, "ofp_wks_*.json")))
    files.sort(key=lambda f: next((i for i, g in enumerate(ORDER) if g in f), 9))
    created = updated = skipped = failed = 0
    for f in files:
        body = json.load(open(f)); kid = body["schemaInfo"]["schemaIdentity"]["id"]
        if DRY: print(f"  would POST {kid}"); continue
        s, txt = _req("POST", "/api/schema-service/v1/schema", body)
        if s in (200, 201): created += 1
        elif s == 400 and "already" in json.dumps(txt).lower():
            s2, _ = _req("PUT", "/api/schema-service/v1/schema", body)
            if s2 in (200, 201): updated += 1
            else: skipped += 1
        else: failed += 1; print(f"  FAIL {s} {kid}")
    print(f"  schemas: created={created} updated={updated} skipped={skipped} failed={failed} (of {len(files)})")
    return failed == 0

SRC_PART = json.load(open(os.path.join(C3, "_manifest.json")))["platform"]["partition"]

def remap(obj):
    """Record ids are partition-scoped (`<partition>:<group>--<Entity>:<key>`). When restoring
    into a different partition, rewrite the prefix on ids AND on every id reference inside data,
    or the graph's foreign keys point at records that do not exist there."""
    if PART == SRC_PART: return obj
    return json.loads(re.sub(rf'"{re.escape(SRC_PART)}:([A-Za-z0-9-]+--)', rf'"{PART}:\1', json.dumps(obj)))

def phase_records():
    files = sorted(glob.glob(os.path.join(RECS, "*.json")))
    by_group = {g: [] for g in ORDER}
    if PART != SRC_PART: print(f"  remapping record ids: {SRC_PART}: -> {PART}:")
    for f in files:
        r = remap(json.load(open(f))); g = next((g for g in ORDER if f":{g}--" in r["kind"]), "work-product-component")
        rec = {"id": r["id"], "kind": r["kind"], "acl": r["acl"], "legal": r["legal"], "data": r["data"]}
        if LEGALTAG: rec["legal"] = {**rec["legal"], "legaltags": [LEGALTAG]}
        if OWNERS or VIEWERS: rec["acl"] = {"owners": [OWNERS or rec["acl"]["owners"][0]], "viewers": [VIEWERS or rec["acl"]["viewers"][0]]}
        by_group[g].append(rec)
    total = ok = 0
    for g in ORDER:
        batch = by_group[g]; total += len(batch)
        if DRY: print(f"  would PUT {len(batch)} {g} records"); ok += len(batch); continue
        for i in range(0, len(batch), 100):
            chunk = batch[i:i + 100]
            s, j = _req("PUT", "/api/storage/v2/records", chunk)
            if s < 300: ok += len(chunk)
            else: print(f"  FAIL {g} chunk {i}: {s} {json.dumps(j)[:200]}")
        print(f"  {g}: {len(batch)} records")
    print(f"  records restored: {ok}/{total}")
    return ok == total

def main():
    print(f"### restore claim #3 -> {BASE} [{PART}]" + ("  (DRY RUN)" if DRY else ""))
    a = phase_schemas() if "--records-only" not in sys.argv else True
    b = phase_records() if "--schemas-only" not in sys.argv else True
    print("### done" if a and b else "### completed with failures")
    return a and b

if __name__ == "__main__": sys.exit(0 if main() else 1)
