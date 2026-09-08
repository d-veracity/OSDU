#!/usr/bin/env python3
"""
Generate OSDU draft-07 schemas for the CCUS + SCEP domain, DIRECTLY from the dVeracity
SysML v2 model (sysml/osdu-data-platform/). This makes the deployed OSDU schemas formally
traceable to the architecture spec at dveracity.com/architecture/osdu.

Source of truth:
  - 03_types_items.sysml : the 17 activity records (item def X :> OSDUActivityRecord)
  - 01_types_enums.sysml  : enum members (→ JSON Schema `enum` constraints)

Records are modeled OSDU-native as work-product-component kinds (activity/measurement
records), authority `ofp` (proven accepted), grounding on OFPActivityRecord:
    ofp:wks:work-product-component--<RecordName>:1.0.0

OSDU envelope (id/kind/acl/legal/version) is the record envelope; the SysML
`osduKind/osduAcl/osduLegalTag/osduVersion` map there. All other inherited + own
attributes become `data`.
"""
import re, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("OFP_REPO_ROOT", os.path.join(HERE, "..", "..")))
SYSML = os.path.join(ROOT, "sysml/osdu-data-platform")
OUTDIR = os.path.join(HERE, "schemas")
os.makedirs(OUTDIR, exist_ok=True)

# ---- domain membership (from 03_types_items.sysml section headers) ----
CCUS = {"CO2CaptureRecord","CO2TransportRecord","CO2InjectionRecord","CO2StorageRecord",
        "ContainmentAssessment","CO2PlumeObservation","SiteClosureRecord"}
SCEP = {"StructureMapRecord","ContainmentIntegrityAssessment","ActivityLineageRecord",
        "InterpretationActivity","CO2MassBalanceRecord","MMVEventRecord",
        "PreInjectionBaselineRecord","OFPAdjustmentRecord","CarbonClaimAdjustmentRecord",
        "SCEPVersionSnapshot"}
TARGET = CCUS | SCEP

# ---- inherited base attributes (envelope-excluded) ----
# OFPActivityRecord (documented) + OSDUActivityRecord (non-envelope) fields.
BASE_ATTRS = [
    ("activityId","UUID"), ("activityType","String"),
    ("reportingPeriodStart","Timestamp"), ("reportingPeriodEnd","Timestamp"),
    ("dataSource","String"), ("recordingType","OFPRecordingType"),
    ("sensitivity","SensitivityLevel"),
    ("facilityId","UUID"), ("location","GeoLocation"),
    ("predecessorVersionId","UUID"), ("modelVersion","String"),
]
ENVELOPE = {"osduKind","osduVersion","osduAcl","osduLegalTag"}

# ---- type mapping ----
NUMBER_TYPES = {"Real","MassTonnes","PressureMPa","LengthKm","FlowRateTPA","AreaKm2","DepthM",
    "EnergyMWh","DensityKgPerM3","VolumeM3","PercentValue","CO2eKg","ConcentrationPPM",
    "WindSpeedMPS","EmissionRateKgPerHour","ConfidenceScore"}
INT_TYPES = {"Integer"}
BOOL_TYPES = {"Boolean"}
STRING_TYPES = {"String","UUID","SHA256Hash","VersionString","GeoLocation"}
DATETIME_TYPES = {"Timestamp"}

def parse_enums(path):
    txt = open(path).read()
    enums = {}
    for m in re.finditer(r'enum def (\w+)\s*\{(.*?)\}', txt, re.S):
        name, body = m.group(1), m.group(2)
        # members are bare identifiers ending in ; (skip doc comments)
        body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
        members = [x.strip().rstrip(';') for x in re.split(r';', body) if x.strip() and re.match(r'^\w+$', x.strip().rstrip(';'))]
        members = [x for x in members if x]
        if members: enums[name] = members
    return enums

def parse_items(path):
    """Return {RecordName: [(attrName, typeName, isArray)]} for item defs :> OSDUActivityRecord."""
    txt = open(path).read()
    items = {}
    i = 0
    for m in re.finditer(r'item def (\w+)\s*:>\s*OSDUActivityRecord\s*\{', txt):
        name = m.group(1)
        # capture the balanced block
        start = m.end() - 1
        depth = 0
        j = start
        while j < len(txt):
            if txt[j] == '{': depth += 1
            elif txt[j] == '}':
                depth -= 1
                if depth == 0: break
            j += 1
        block = txt[start+1:j]
        block = re.sub(r'/\*.*?\*/', '', block, flags=re.S)   # strip doc comments
        attrs = []
        for a in re.finditer(r'attribute (\w+)\s*:\s*([\w:]+)\s*(\[[^\]]*\])?', block):
            aname, atype = a.group(1), a.group(2).split('::')[-1]
            is_arr = bool(a.group(3))
            attrs.append((aname, atype, is_arr))
        items[name] = attrs
    return items

def js_for(typename, enums):
    if typename in enums:
        return {"type": "string", "enum": enums[typename]}
    if typename in NUMBER_TYPES: return {"type": "number"}
    if typename in INT_TYPES: return {"type": "integer"}
    if typename in BOOL_TYPES: return {"type": "boolean"}
    if typename in DATETIME_TYPES: return {"type": "string", "format": "date-time"}
    # UUID/String/SHA256Hash/VersionString/GeoLocation + any unresolved → string
    return {"type": "string"}

SYSTEM_PROPS = {
    "id":{"type":"string"}, "kind":{"type":"string"}, "version":{"type":"integer"},
    "acl":{"type":"object","properties":{"owners":{"type":"array","items":{"type":"string"}},
        "viewers":{"type":"array","items":{"type":"string"}}},"required":["owners","viewers"]},
    "legal":{"type":"object","properties":{"legaltags":{"type":"array","items":{"type":"string"}},
        "otherRelevantDataCountries":{"type":"array","items":{"type":"string"}},"status":{"type":"string"}},
        "required":["legaltags","otherRelevantDataCountries"]},
    "tags":{"type":"object","additionalProperties":{"type":"string"}},
    "createTime":{"type":"string","format":"date-time"},"createUser":{"type":"string"},
    "modifyTime":{"type":"string","format":"date-time"},"modifyUser":{"type":"string"},
}

def build(name, own_attrs, enums):
    domain = "ccus" if name in CCUS else "scep"
    data_props = {}
    # inherited base first, then own attributes
    for aname, atype in BASE_ATTRS:
        data_props[aname] = js_for(atype, enums)
    for aname, atype, is_arr in own_attrs:
        if aname in ENVELOPE: continue
        js = js_for(atype, enums)
        data_props[aname] = {"type":"array","items":js} if is_arr else js
    kid = f"ofp:wks:work-product-component--{name}:1.0.0"
    schema = {
        "$schema":"http://json-schema.org/draft-07/schema#",
        "$id": f"https://schema.dveracity.com/osdu/{domain}/{name}.1.0.0.json",
        "x-osdu-schema-source": kid,
        "x-dve-sysml-source": f"sysml/osdu-data-platform/03_types_items.sysml#{name}",
        "x-dve-domain": domain,
        "title": name,
        "description": f"OSDU {domain.upper()} activity record ({name}), grounded on OFPActivityRecord. Generated from the dVeracity SysML v2 model.",
        "type":"object",
        "properties": {**SYSTEM_PROPS, "data": {"type":"object","properties":data_props,"additionalProperties":False}},
        "required": ["kind","acl","legal","data"],
        "additionalProperties": False,
    }
    body = {"schemaInfo":{"schemaIdentity":{"authority":"ofp","source":"wks",
        "entityType":f"work-product-component--{name}","schemaVersionMajor":1,"schemaVersionMinor":0,"schemaVersionPatch":0,
        "id":kid},"status":"DEVELOPMENT","scope":"INTERNAL","createdBy":"dVeracity","dateCreated":"2026-09-07T00:00:00Z"},
        "schema": schema}
    return kid, body

def main():
    enums = parse_enums(os.path.join(SYSML, "01_types_enums.sysml"))
    items = parse_items(os.path.join(SYSML, "03_types_items.sysml"))
    manifest = {"ccus": [], "scep": []}
    print(f"enums parsed: {len(enums)} | item records parsed: {len(items)}")
    made = 0
    for name, attrs in items.items():
        if name not in TARGET: continue
        kid, body = build(name, attrs, enums)
        fname = kid.replace(':','_') + ".json"
        json.dump(body, open(os.path.join(OUTDIR, fname), 'w'), indent=2)
        dom = "ccus" if name in CCUS else "scep"
        manifest[dom].append({"id":kid,"file":fname,"record":name,
            "dataProps":len(body["schema"]["properties"]["data"]["properties"])})
        made += 1
        print(f"  {dom.upper():4s} {kid:60s} data props={body['schema']['properties']['data']['properties'].__len__()}")
    json.dump(manifest, open(os.path.join(OUTDIR,"manifest.json"),'w'), indent=2)
    print(f"\nwrote {made} schemas ({len(manifest['ccus'])} CCUS + {len(manifest['scep'])} SCEP) to {os.path.relpath(OUTDIR, ROOT)}/")
    missing = TARGET - set(items)
    if missing: print("MISSING from SysML:", missing)

if __name__ == "__main__":
    main()
