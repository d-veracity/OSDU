#!/usr/bin/env python3
"""
Generate OSDU-NATIVE schema bodies for the OFP transaction-data (Emission Statement /
Emission Report family), modeled as OSDU `work-product-component` kinds.

Why work-product-component: OSDU's canonical groups are reference-data, master-data,
work-product, work-product-component, dataset. There is no `transaction-data` group in
OSDU; measurement/transactional records (e.g. WellLog) are modeled as
work-product-component (WPC). So OFP transactional records map to:
    ofp:wks:work-product-component--<Entity>:1.0.0

These are NEW kinds (not in ofp-schema-mapping.json), so they start at 1.0.0.
Property definitions come from the Hackolade standard models (Common Entities,
Recording, Reporting). Same conventions as the master/reference generator:
authority=ofp, source=wks, scope=INTERNAL, status=DEVELOPMENT, snake_case data keys,
self-contained schema (system props inlined).

Run:  python3 OSDU/ofp-schema-deploy/generate_transaction_schemas.py
Output: schemas/ (files) + manifest-transaction.json
"""
import json, glob, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("OFP_REPO_ROOT", os.path.join(HERE, "..", "..")))
MODELS = sorted(glob.glob(os.path.join(ROOT, "openfootprint/standard/models/*.hck.json")))
OUTDIR = os.path.join(HERE, "schemas")
os.makedirs(OUTDIR, exist_ok=True)

# Curated transactional record entities (Hackolade collectionName). Excludes *Type
# lookups (reference-data), calculation-config and vocab entities (master/reference).
TRANSACTION_ENTITIES = [
    # Emission Statement family (the core footprint records)
    "Emission Statement",
    "Emission Statement Per Standard",
    "Emission Statement Argument Value",
    "Emission Statement Parameter Value",
    "Emission Argument Value",
    "Recording Uncertainty Assessment",
    # Emission Report family (reporting records)
    "Emission Report",
    "Emission Report Collection",
    "Emission Report Period",
    "Emission Report Per Standard",
    "Emission Statement Per Report",
    "Emission Statement Aggregator",
    "Emission Reporting Boundary",
    "Reporting Assurance",
    "Organizational Boundary Assurance",
    # Allocations & intensity (reported, derived transactional values)
    "Activity Emission Allocation",
    "Organization Emission Allocation",
    "Emission Intensity Ratio",
]
VERSION = (1, 0, 0)

def norm(s):   return re.sub(r'[^a-z0-9]', '', (s or '').lower())
def snake(n):  return '_'.join(p.lower() for p in re.split(r'[\s_\-/]+', n.strip()) if p)
def pascal(n): return ''.join(p[:1].upper()+p[1:] for p in re.split(r'[\s_\-/]+', n.strip()) if p)

HCK_TYPE = {'string':'string','character':'string','text':'string','numeric':'number',
    'number':'number','decimal':'number','float':'number','double':'number','integer':'integer',
    'int':'integer','bigint':'integer','boolean':'boolean','bool':'boolean','date':'string',
    'datetime':'string','timestamp':'string','document':'object','object':'object','json':'object','array':'array'}

def prop_schema(p):
    t=(p.get('type') or 'string').lower(); js={'type':HCK_TYPE.get(t,'string')}
    nm=p.get('name','')
    if (t in ('date','datetime','timestamp') or re.search(r'datetime|date$|timestamp',nm.lower())) and js['type']=='string':
        js['format']='date-time'
    if p.get('description'): js['description']=p['description']
    return js

def nprops(c):
    p=c.get('properties'); return len(p) if isinstance(p,(list,dict)) else 0
hck={}
for f in MODELS:
    for c in json.load(open(f)).get('collections',[]):
        k=norm(c.get('collectionName'))
        if k not in hck or nprops(c)>nprops(hck[k]): hck[k]=c

SYSTEM_PROPS = {
    "id":{"type":"string","description":"Unique identifier of an OSDU record."},
    "kind":{"type":"string","description":"Schema kind (authority:source:entityType:version)."},
    "version":{"type":"integer","description":"Version number of this OSDU record."},
    "acl":{"type":"object","description":"Access control list.","properties":{
        "owners":{"type":"array","items":{"type":"string"}},"viewers":{"type":"array","items":{"type":"string"}}},
        "required":["owners","viewers"]},
    "legal":{"type":"object","description":"Legal compliance metadata.","properties":{
        "legaltags":{"type":"array","items":{"type":"string"}},
        "otherRelevantDataCountries":{"type":"array","items":{"type":"string"}},"status":{"type":"string"}},
        "required":["legaltags","otherRelevantDataCountries"]},
    "tags":{"type":"object","additionalProperties":{"type":"string"}},
    "createTime":{"type":"string","format":"date-time"},"createUser":{"type":"string"},
    "modifyTime":{"type":"string","format":"date-time"},"modifyUser":{"type":"string"},
}

mj,mn,pt = VERSION
matched, unmatched, manifest = [], [], []
for entity in TRANSACTION_ENTITIES:
    ent = hck.get(norm(entity))
    if not ent:
        unmatched.append(entity); continue
    etype = f"work-product-component--{pascal(entity)}"
    kid = f"ofp:wks:{etype}:{mj}.{mn}.{pt}"
    data_props, required = {}, []
    for p in ent.get('properties', []):
        k = snake(p.get('name',''))
        if not k: continue
        data_props[k] = prop_schema(p)
        if p.get('required') is True: required.append(k)
    data_obj = {"type":"object","properties":data_props,"additionalProperties":False}
    if required: data_obj["required"] = sorted(set(required))
    schema = {
        "$schema":"http://json-schema.org/draft-07/schema#",
        "$id": f"https://schema.dveracity.com/ofp/{etype}.{mj}.{mn}.{pt}.json",
        "x-osdu-schema-source": kid,
        "title": entity, "description": ent.get('description') or f"Open Footprint {entity} (transactional record).",
        "type":"object", "properties": {**SYSTEM_PROPS, "data": data_obj},
        "required": ["kind","acl","legal","data"], "additionalProperties": False,
    }
    body = {"schemaInfo":{"schemaIdentity":{"authority":"ofp","source":"wks","entityType":etype,
        "schemaVersionMajor":mj,"schemaVersionMinor":mn,"schemaVersionPatch":pt,"id":kid},
        "status":"DEVELOPMENT","scope":"INTERNAL","createdBy":"dVeracity","dateCreated":"2026-08-21T00:00:00Z"},
        "schema": schema}
    fname = kid.replace(':','_')+".json"
    json.dump(body, open(os.path.join(OUTDIR,fname),'w'), indent=2)
    matched.append((kid, len(data_props), len(required)))
    manifest.append({"id":kid,"file":fname,"properties":len(data_props)})

json.dump({"work-product-component":manifest}, open(os.path.join(OUTDIR,"manifest-transaction.json"),'w'), indent=2)
print(f"work-product-component (transaction-data) schemas: {len(matched)}/{len(TRANSACTION_ENTITIES)}")
for kid,n,r in matched: print(f"  {kid:62s} props={n:2d} req={r}")
if unmatched: print("UNMATCHED (no Hackolade collection):", *unmatched, sep="\n  ")
