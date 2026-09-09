#!/usr/bin/env python3
"""
Generate OSDU schemas for the Methane MRV domain (architecture claim #3), grounded in
ISO 25624-1:2026 (Methane emissions in upstream O&G — Part 1: Quantification), which is
"in line with OGMP 2.0" and supports EU Reg 2024/1787.

Three sources:
  1. The 7 methane activity records from the dVeracity SysML v2 model
     (sysml/osdu-data-platform/03_types_items.sysml) -> work-product-component kinds.
  2. ISO 25624-1 reference-data, hand-authored from the standard:
       - MethaneSourceCategory      (Clause 6 source taxonomy)
       - MethaneQuantificationMethod (5.4: direct / engineering / simulation / EF)
       - MethaneMeasurementTechnology (Annex A recognized technologies)
  3. MethaneMonitoringPlan — the certifiable wrapper (5.1 + Annex B), the methane
     analog of the SCEP evidence pack; carries the reconciliation gate parameters
     (divergence limit 20%, Gold Standard coverage 95%, materiality 5%) and a
     verification state machine: draft -> underReview -> verified -> restated/suspended.

All kinds: authority ofp, source wks, scope INTERNAL, status DEVELOPMENT.
"""
import re, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("OFP_REPO_ROOT", os.path.join(HERE, "..", "..")))
SYSML = os.path.join(ROOT, "sysml/osdu-data-platform")
OUTDIR = os.path.join(HERE, "schemas")
os.makedirs(OUTDIR, exist_ok=True)

METHANE = {"MethaneDetectionEvent","EmissionQuantification","MethaneSourceInventory",
           "ReconciliationResult","OGMPReport","MethaneAlertEvent","LDARSurveyRecord"}

BASE_ATTRS = [("activityId","UUID"),("activityType","String"),
    ("reportingPeriodStart","Timestamp"),("reportingPeriodEnd","Timestamp"),
    ("dataSource","String"),("recordingType","OFPRecordingType"),("sensitivity","SensitivityLevel"),
    ("facilityId","UUID"),("location","GeoLocation"),("predecessorVersionId","UUID"),("modelVersion","String")]
ENVELOPE = {"osduKind","osduVersion","osduAcl","osduLegalTag"}
NUMBER = {"Real","MassTonnes","PressureMPa","LengthKm","FlowRateTPA","AreaKm2","DepthM","EnergyMWh",
    "DensityKgPerM3","VolumeM3","PercentValue","CO2eKg","ConcentrationPPM","WindSpeedMPS",
    "EmissionRateKgPerHour","ConfidenceScore"}

def parse_enums(p):
    t=open(p).read(); out={}
    for m in re.finditer(r'enum def (\w+)\s*\{(.*?)\}', t, re.S):
        body=re.sub(r'/\*.*?\*/','',m.group(2),flags=re.S)
        mem=[x.strip().rstrip(';') for x in body.split(';') if re.match(r'^\s*\w+\s*;?$', x.strip()+';')]
        mem=[x for x in mem if x]
        if mem: out[m.group(1)]=mem
    return out

def parse_items(p):
    t=open(p).read(); items={}
    for m in re.finditer(r'item def (\w+)\s*:>\s*OSDUActivityRecord\s*\{', t):
        i=m.end()-1; d=0; j=i
        while j<len(t):
            if t[j]=='{': d+=1
            elif t[j]=='}':
                d-=1
                if d==0: break
            j+=1
        blk=re.sub(r'/\*.*?\*/','',t[i+1:j],flags=re.S)
        items[m.group(1)]=[(a.group(1),a.group(2).split('::')[-1],bool(a.group(3)))
            for a in re.finditer(r'attribute (\w+)\s*:\s*([\w:]+)\s*(\[[^\]]*\])?', blk)]
    return items

def js_for(tn, enums):
    if tn in enums: return {"type":"string","enum":enums[tn]}
    if tn in NUMBER: return {"type":"number"}
    if tn=="Integer": return {"type":"integer"}
    if tn=="Boolean": return {"type":"boolean"}
    if tn=="Timestamp": return {"type":"string","format":"date-time"}
    return {"type":"string"}

SYS = {"id":{"type":"string"},"kind":{"type":"string"},"version":{"type":"integer"},
    "acl":{"type":"object","properties":{"owners":{"type":"array","items":{"type":"string"}},
        "viewers":{"type":"array","items":{"type":"string"}}},"required":["owners","viewers"]},
    "legal":{"type":"object","properties":{"legaltags":{"type":"array","items":{"type":"string"}},
        "otherRelevantDataCountries":{"type":"array","items":{"type":"string"}},"status":{"type":"string"}},
        "required":["legaltags","otherRelevantDataCountries"]},
    "tags":{"type":"object","additionalProperties":{"type":"string"}},
    "createTime":{"type":"string","format":"date-time"},"createUser":{"type":"string"},
    "modifyTime":{"type":"string","format":"date-time"},"modifyUser":{"type":"string"}}

def body(group, name, data_props, title, desc, extra=None):
    etype=f"{group}--{name}"; kid=f"ofp:wks:{etype}:1.0.0"
    schema={"$schema":"http://json-schema.org/draft-07/schema#",
        "$id":f"https://schema.dveracity.com/osdu/methane/{name}.1.0.0.json",
        "x-osdu-schema-source":kid,"x-dve-domain":"methane",**(extra or {}),
        "title":title,"description":desc,"type":"object",
        "properties":{**SYS,"data":{"type":"object","properties":data_props,"additionalProperties":False}},
        "required":["kind","acl","legal","data"],"additionalProperties":False}
    return kid,{"schemaInfo":{"schemaIdentity":{"authority":"ofp","source":"wks","entityType":etype,
        "schemaVersionMajor":1,"schemaVersionMinor":0,"schemaVersionPatch":0,"id":kid},
        "status":"DEVELOPMENT","scope":"INTERNAL","createdBy":"dVeracity","dateCreated":"2026-09-08T00:00:00Z"},
        "schema":schema}

# ---------- ISO 25624-1 reference data (hand-authored from the standard) ----------
ISO_SOURCE_CATEGORIES = ["flaring","unlitFlare","incompleteCombustion","fugitive","ventingPneumatic",
    "ventingCompressorCentrifugal","ventingCompressorReciprocating","ventingDehydrator","ventingTank",
    "ventingWellLiquidUnloading","ventingCasinghead","ventingWellCompletion","ventingLoadingUnloading",
    "other","emissionsToWater","emissionsSubsurface"]
ISO_METHODS = ["directMeasurement","engineeringCalculation","processSimulation",
    "genericEmissionFactor","specificEmissionFactor"]
ISO_TECHNOLOGIES = ["TDLAS","NDIR","FTIR","FID","GC-FID","OGI","MOX","catalytic","CRDS",
    "hyperspectral","LIDAR","QEPAS","openPath","SWIR"]
PLAN_STATUS = ["draft","underReview","verified","restated","suspended"]

def refdata(name, code_enum, title, clause):
    return body("reference-data", name, {
        "code":{"type":"string","enum":code_enum},"name":{"type":"string"},
        "description":{"type":"string"},"isoClause":{"type":"string"},
        "sensitivityNote":{"type":"string"}}, title,
        f"ISO 25624-1:2026 {clause} — {title}.", {"x-dve-standard":"ISO 25624-1:2026","x-dve-clause":clause})

def main():
    enums=parse_enums(os.path.join(SYSML,"01_types_enums.sysml"))
    items=parse_items(os.path.join(SYSML,"03_types_items.sysml"))
    manifest={"sysml-records":[],"iso-reference-data":[],"monitoring-plan":[]}
    def emit(group_key, kid, b):
        fn=kid.replace(':','_')+".json"; json.dump(b,open(os.path.join(OUTDIR,fn),'w'),indent=2)
        manifest[group_key].append({"id":kid,"file":fn}); print(f"  {kid}")

    print("SysML methane records:")
    for name in sorted(METHANE):
        attrs=items.get(name)
        if not attrs: print("  MISSING", name); continue
        dp={a:js_for(t,enums) for a,t in BASE_ATTRS}
        for a,t,arr in attrs:
            if a in ENVELOPE: continue
            j=js_for(t,enums); dp[a]={"type":"array","items":j} if arr else j
        kid,b=body("work-product-component",name,dp,name,
            f"OSDU methane MRV activity record ({name}), grounded on OFPActivityRecord; generated from the dVeracity SysML v2 model.",
            {"x-dve-sysml-source":f"sysml/osdu-data-platform/03_types_items.sysml#{name}"})
        emit("sysml-records",kid,b)

    print("ISO 25624-1 reference data:")
    for name,en,title,cl in [
        ("MethaneSourceCategory",ISO_SOURCE_CATEGORIES,"Methane source category","Clause 6"),
        ("MethaneQuantificationMethod",ISO_METHODS,"Methane quantification method","Clause 5.4"),
        ("MethaneMeasurementTechnology",ISO_TECHNOLOGIES,"Recognized methane measurement technology","Annex A")]:
        kid,b=refdata(name,en,title,cl); emit("iso-reference-data",kid,b)

    print("Monitoring plan (certifiable wrapper):")
    kid,b=body("work-product-component","MethaneMonitoringPlan",{
        "planId":{"type":"string"},"siteId":{"type":"string"},"assetId":{"type":"string"},
        "reportingBoundary":{"type":"string"},
        "reportingPeriodStart":{"type":"string","format":"date-time"},
        "reportingPeriodEnd":{"type":"string","format":"date-time"},
        "sourceInventoryIds":{"type":"array","items":{"type":"string"}},
        "siteMeasurementIds":{"type":"array","items":{"type":"string"}},
        "reconciliationResultId":{"type":"string"},
        "targetOgmpLevel":{"type":"string","enum":enums.get("OGMPLevel",["level4"])},
        "materialityThresholdPercent":{"type":"number"},
        "goldStandardCoveragePercent":{"type":"number"},
        "reconciliationDivergenceLimitPercent":{"type":"number"},
        "uncertaintyCoverageFactorK":{"type":"number"},
        "verificationStatus":{"type":"string","enum":PLAN_STATUS},
        "versionTrigger":{"type":"string","enum":["periodic","eventDriven","regulatory","corrective"]},
        "planHash":{"type":"string"},"previousVersionId":{"type":"string"},
        "activityType":{"type":"string"},"dataSource":{"type":"string"},"facilityId":{"type":"string"},
        "recordingType":{"type":"string"},"sensitivity":{"type":"string"}},
        "MethaneMonitoringPlan",
        "ISO 25624-1 Monitoring Plan (5.1 + Annex B): the certifiable methane MRV wrapper carrying reconciliation-gate parameters and a verification state machine.",
        {"x-dve-standard":"ISO 25624-1:2026","x-dve-clause":"5.1, Annex B, 8, 9, 11"})
    emit("monitoring-plan",kid,b)

    json.dump(manifest,open(os.path.join(OUTDIR,"manifest.json"),'w'),indent=2)
    n=sum(len(v) for v in manifest.values())
    print(f"\nwrote {n} schemas -> {os.path.relpath(OUTDIR,ROOT)}/")

if __name__=="__main__": main()
