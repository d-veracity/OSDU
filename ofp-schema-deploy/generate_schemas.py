#!/usr/bin/env python3
"""
Generate OSDU draft-07 schema bodies for the deployed OFP entity set.

Run from anywhere:  python3 openfootprint/osdu/generate_schemas.py

Sources:
  - dVE/backend/src/adapters/ofp-schema-mapping.json  -> the target kinds (canonical
    kind IDs + versions; this is the curated, deployed OFP subset)
  - openfootprint/standard/models/*.hck.json          -> authoritative property defs

Output (openfootprint/osdu/schemas/):
  - one <kindId>.json per entity: a full Schema Service POST body (schemaInfo + schema)
  - manifest.json: register order (reference-data before master-data), deduplicated

Design decisions:
  - authority=ofp, source=wks, scope=INTERNAL, status=DEVELOPMENT
    (authority 'ofp' proven accepted by the target platform; DEVELOPMENT stays mutable)
  - KEY_STYLE='snake' -> data property keys are snake_case, matching the OFP database
    and ELM models, so records exported from Postgres validate directly.
    Set KEY_STYLE='pascal' for OSDU-house-style names.
  - schemas are SELF-CONTAINED (system props inlined, no external $ref) to avoid
    $ref-resolution failures on first deploy. Refactor to $ref osdu abstracts later.

NOTE: several OFP DB tables map to a single kind (e.g. geospatial_location, location,
spatial_location -> ofp:wks:master-data--GeospatialLocation:3.0.0). Output is written
per kind, so duplicates collapse to one file; the manifest is deduplicated on write.
"""
import json, glob, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
# OFP sources (dVE, openfootprint/standard) live in the parent workspace, outside this
# repo. Default to two levels up (~/dv); override with OFP_REPO_ROOT for other layouts.
ROOT = os.path.abspath(os.environ.get("OFP_REPO_ROOT", os.path.join(HERE, "..", "..")))
MAPPING = os.path.join(ROOT, "dVE/backend/src/adapters/ofp-schema-mapping.json")
MODELS = sorted(glob.glob(os.path.join(ROOT, "openfootprint/standard/models/*.hck.json")))
OUTDIR = os.path.join(HERE, "schemas")
KEY_STYLE = os.environ.get("KEY_STYLE", "snake")   # 'snake' | 'pascal'
os.makedirs(OUTDIR, exist_ok=True)

def norm(s):   return re.sub(r'[^a-z0-9]', '', (s or '').lower())
def snake(name):
    parts = re.split(r'[\s_\-/]+', name.strip()); return '_'.join(p.lower() for p in parts if p)
def pascal(name):
    parts = re.split(r'[\s_\-/]+', name.strip()); return ''.join(p[:1].upper()+p[1:] for p in parts if p)
def key_of(name): return snake(name) if KEY_STYLE == "snake" else pascal(name)

HCK_TYPE = {
    'string':'string','character':'string','text':'string',
    'numeric':'number','number':'number','decimal':'number','float':'number','double':'number',
    'integer':'integer','int':'integer','bigint':'integer',
    'boolean':'boolean','bool':'boolean',
    'date':'string','datetime':'string','timestamp':'string',
    'document':'object','object':'object','json':'object','array':'array',
}

def prop_schema(p):
    t = (p.get('type') or 'string').lower()
    js = {'type': HCK_TYPE.get(t, 'string')}
    name = p.get('name','')
    if (t in ('date','datetime','timestamp') or re.search(r'datetime|date$|timestamp', name.lower())) and js['type']=='string':
        js['format'] = 'date-time'
    if p.get('description'): js['description'] = p['description']
    return js

# index Hackolade entities; on name collision keep the richest (most properties)
def nprops(c):
    p = c.get('properties'); return len(p) if isinstance(p,(list,dict)) else 0
hck = {}
for f in MODELS:
    for c in json.load(open(f)).get('collections', []):
        k = norm(c.get('collectionName'))
        if k not in hck or nprops(c) > nprops(hck[k]): hck[k] = c

mapping = json.load(open(MAPPING))['mappings']

SYSTEM_PROPS = {
    "id": {"type":"string","description":"Unique identifier of an OSDU record."},
    "kind": {"type":"string","description":"Schema kind (authority:source:entityType:version)."},
    "version": {"type":"integer","description":"Version number of this OSDU record."},
    "acl": {"type":"object","description":"Access control list.","properties":{
        "owners":{"type":"array","items":{"type":"string"}},
        "viewers":{"type":"array","items":{"type":"string"}}},"required":["owners","viewers"]},
    "legal": {"type":"object","description":"Legal compliance metadata.","properties":{
        "legaltags":{"type":"array","items":{"type":"string"}},
        "otherRelevantDataCountries":{"type":"array","items":{"type":"string"}},
        "status":{"type":"string"}},"required":["legaltags","otherRelevantDataCountries"]},
    "tags": {"type":"object","additionalProperties":{"type":"string"}},
    "createTime": {"type":"string","format":"date-time"},
    "createUser": {"type":"string"},
    "modifyTime": {"type":"string","format":"date-time"},
    "modifyUser": {"type":"string"},
}

def parse_kind(kid):
    a,s,e,v = kid.split(':'); mj,mn,pt = v.split('.'); return a,s,e,int(mj),int(mn),int(pt)

matched, unmatched = [], []
manifest = {"reference-data": [], "master-data": []}
seen_group = {"reference-data": set(), "master-data": set()}

for table, info in mapping.items():
    kid, entity = info['ofpId'], info['ofpEntity']
    a,s,etype,mj,mn,pt = parse_kind(kid)
    ent = hck.get(norm(entity))
    if not ent:
        unmatched.append((kid, entity)); continue
    data_props, required = {}, []
    for p in ent.get('properties', []):
        k = key_of(p.get('name',''))
        if not k: continue
        data_props[k] = prop_schema(p)
        if p.get('required') is True: required.append(k)
    data_obj = {"type":"object","properties":data_props,"additionalProperties":False}
    if required: data_obj["required"] = sorted(set(required))
    schema = {
        "$schema":"http://json-schema.org/draft-07/schema#",
        "$id": f"https://schema.dveracity.com/ofp/{etype}.{mj}.{mn}.{pt}.json",
        "x-osdu-schema-source": kid,
        "title": entity,
        "description": ent.get('description') or f"Open Footprint {entity} entity.",
        "type":"object",
        "properties": {**SYSTEM_PROPS, "data": data_obj},
        "required": ["kind","acl","legal","data"],
        "additionalProperties": False,
    }
    body = {"schemaInfo":{"schemaIdentity":{"authority":a,"source":s,"entityType":etype,
        "schemaVersionMajor":mj,"schemaVersionMinor":mn,"schemaVersionPatch":pt,"id":kid},
        "status":"DEVELOPMENT","scope":"INTERNAL","createdBy":"dVeracity","dateCreated":"2026-08-21T00:00:00Z"},
        "schema": schema}
    fname = kid.replace(':','_')+".json"
    json.dump(body, open(os.path.join(OUTDIR, fname),'w'), indent=2)
    matched.append((kid, entity, len(data_props), len(required)))
    g = "reference-data" if etype.startswith("reference-data") else "master-data"
    if kid not in seen_group[g]:
        seen_group[g].add(kid); manifest[g].append({"id":kid,"file":fname,"properties":len(data_props)})

json.dump(manifest, open(os.path.join(OUTDIR,"manifest.json"),'w'), indent=2)
uniq = len(manifest['reference-data']) + len(manifest['master-data'])
print(f"key style: {KEY_STYLE}")
print(f"output: {os.path.relpath(OUTDIR, ROOT)}/")
print(f"mapping rows: {len(mapping)} | matched: {len(matched)} | unmatched: {len(unmatched)} | unique kinds: {uniq}")
print(f"register order: {len(manifest['reference-data'])} reference-data, then {len(manifest['master-data'])} master-data")
if unmatched:
    print("UNMATCHED:", *[f'{k} ({e})' for k,e in unmatched], sep="\n  ")
