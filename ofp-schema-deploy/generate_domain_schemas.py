#!/usr/bin/env python3
"""
Generate OSDU schema bodies for the OFP domain entities needed by the methane MRV proof
(claim #3) from the Data Verification, Organizational Structure / Boundary, Facility
Structure, Recording and Reporting domains — the ones NOT in ofp-schema-mapping.json.

Same pipeline as generate_schemas.py / generate_transaction_schemas.py:
  - property definitions: openfootprint/standard/models/*.hck.json (authoritative)
  - kind id: the Hackolade collection's own `id` (e.g.
    `ofp:wks:reference-data--DataVerificationType:4.0.0`). This is the same field the
    dVE mapping json took its `ofpId` from (analyze-ofp-schema.js: ofpId = ofpEntity.$id),
    so reference-data / master-data kinds keep the model's canonical version (4.0.0).
  - OSDU has no `transactional-data` group; as with the Emission Statement family, OFP
    `transactional-data--X` becomes `work-product-component--X:1.0.0` (new OSDU kind).
  - authority=ofp, source=wks, scope=INTERNAL, status=DEVELOPMENT, snake_case data keys,
    self-contained schema (system props inlined), arrays always declare `items`.
Entities whose collection carries no canonical id are reported and skipped, never
assigned a made-up id.

Run:  python3 OSDU/ofp-schema-deploy/generate_domain_schemas.py
Output: schemas/ (files) + schemas/manifest-domains.json
Register: OSDU_TOKEN_FILE=... ./register_schemas.sh domains
"""
import json, glob, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("OFP_REPO_ROOT", os.path.join(HERE, "..", "..")))
MODELS = sorted(glob.glob(os.path.join(ROOT, "openfootprint/standard/models/*.hck.json")))
OUTDIR = os.path.join(HERE, "schemas")
os.makedirs(OUTDIR, exist_ok=True)

# Curated domain entities (Hackolade collectionName) -> OFP domain, for the methane proof.
DOMAIN_ENTITIES = [
    # Data Verification domain (none deployed before)
    ("Data Verification Type",                 "Data Verification"),
    ("Data Verification Source",               "Data Verification"),
    ("Data Rule Dimension Type",               "Data Verification"),
    ("Data Rule Purpose Type",                 "Data Verification"),
    ("Data Quality Rule Status",               "Data Verification"),
    ("Quality Assessment State",               "Data Verification"),
    ("Quality Assessment Method",              "Data Verification"),
    ("Data Quality Rule",                      "Data Verification"),
    ("Data Quality Rule Set",                  "Data Verification"),
    ("Data Quality",                           "Data Verification"),
    ("Verifiable Credential",                  "Data Verification"),
    # Organizational Structure / Boundary
    ("Organization External Identifier Type",  "Organizational Structure"),
    ("Organization External Identifier",       "Organizational Structure"),
    ("Organization Person Association",        "Organizational Structure"),
    ("Country",                                "Organizational Structure"),
    ("Organization Control",                   "Organizational Boundary"),
    # Facility Structure
    ("Facility Structure",                     "Facility Structure"),
    ("Facility Location Association",          "Facility Structure"),
    ("Location",                               "Facility Structure"),
    ("Equipment Installation",                 "Facility Structure"),
    ("Facility Activity Participation",        "Facility Structure"),
    ("Facility Specification",                 "Facility Structure"),
    ("Compliance Requirement",                 "Facility Structure"),
    # Recording
    ("Emission Calculation Formula Component", "Recording"),
    ("Emission Calculation Model Argument",    "Recording"),
    ("Emission Activity Factor",               "Recording"),
    ("Emission Parameter Type",                "Recording"),
    # Reporting
    ("Reporting Assurance Type",               "Reporting"),
    ("Facility Emission Allocation",           "Reporting"),
]
TX_VERSION = (1, 0, 0)   # transactional-data -> work-product-component (new OSDU kind)

def norm(s):   return re.sub(r'[^a-z0-9]', '', (s or '').lower())
def snake(n):  return '_'.join(p.lower() for p in re.split(r'[\s_\-/]+', n.strip()) if p)

HCK_TYPE = {'string':'string','character':'string','text':'string','numeric':'number',
    'number':'number','decimal':'number','float':'number','double':'number','integer':'integer',
    'int':'integer','bigint':'integer','boolean':'boolean','bool':'boolean','date':'string',
    'datetime':'string','timestamp':'string','document':'object','object':'object','json':'object',
    'reference':'object','array':'array'}

def prop_schema(p):
    t=(p.get('type') or 'string').lower(); js={'type':HCK_TYPE.get(t,'string')}
    nm=p.get('name','')
    if (t in ('date','datetime','timestamp') or re.search(r'datetime|date$|timestamp',nm.lower())) and js['type']=='string':
        js['format']='date-time'
    if js['type']=='array':  # OSDU indexer requires 'items' on arrays
        js['items']={'type':'string'}
    if p.get('description'): js['description']=p['description']
    return js

# index Hackolade entities; on name collision keep the richest (most properties)
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

def resolve_kind(model_id):
    """Canonical model id -> OSDU kind id. transactional-data has no OSDU group -> WPC 1.0.0."""
    a,s,etype,v = model_id.split(':')
    group, name = etype.split('--',1)
    if group == 'transactional-data':
        mj,mn,pt = TX_VERSION; group = 'work-product-component'
    else:
        mj,mn,pt = (int(x) for x in v.split('.'))
    etype = f"{group}--{name}"
    return f"{a}:{s}:{etype}:{mj}.{mn}.{pt}", a, s, etype, group, mj, mn, pt

manifest = {"reference-data": [], "master-data": [], "work-product-component": []}
matched, unmatched, no_id = [], [], []
for entity, domain in DOMAIN_ENTITIES:
    ent = hck.get(norm(entity))
    if not ent: unmatched.append(entity); continue
    model_id = ent.get('id','')
    if not model_id.startswith('ofp:wks:') or '--' not in model_id:
        no_id.append(entity); continue
    kid,a,s,etype,group,mj,mn,pt = resolve_kind(model_id)
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
        "x-osdu-schema-source": model_id,          # the OFP model's canonical id
        "title": entity, "description": ent.get('description') or f"Open Footprint {entity} ({domain} domain).",
        "type":"object", "properties": {**SYSTEM_PROPS, "data": data_obj},
        "required": ["kind","acl","legal","data"], "additionalProperties": False,
    }
    body = {"schemaInfo":{"schemaIdentity":{"authority":a,"source":s,"entityType":etype,
        "schemaVersionMajor":mj,"schemaVersionMinor":mn,"schemaVersionPatch":pt,"id":kid},
        "status":"DEVELOPMENT","scope":"INTERNAL","createdBy":"dVeracity","dateCreated":"2026-09-08T00:00:00Z"},
        "schema": schema}
    fname = kid.replace(':','_')+".json"
    json.dump(body, open(os.path.join(OUTDIR,fname),'w'), indent=2)
    matched.append((kid, model_id, domain, len(data_props), len(required)))
    manifest[group].append({"id":kid,"model_id":model_id,"domain":domain,"file":fname,"properties":len(data_props)})

json.dump(manifest, open(os.path.join(OUTDIR,"manifest-domains.json"),'w'), indent=2)
print(f"domain schemas: {len(matched)}/{len(DOMAIN_ENTITIES)}  "
      f"(ref={len(manifest['reference-data'])} master={len(manifest['master-data'])} wpc={len(manifest['work-product-component'])})")
for kid,mid,dom,n,r in matched:
    flag = "" if kid==mid else "  <- model: "+mid
    print(f"  {kid:72s} {dom:26s} props={n:2d} req={r}{flag}")
if no_id:     print("SKIPPED (collection has no canonical ofp:wks id):", *no_id, sep="\n  ")
if unmatched: print("UNMATCHED (no Hackolade collection):", *unmatched, sep="\n  ")
