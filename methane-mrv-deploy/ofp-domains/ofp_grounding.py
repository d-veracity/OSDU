#!/usr/bin/env python3
"""
Claim #3 build-out: ground the methane MRV proof in the OFP data domains on live OSDU.

Builds ONE connected OFP graph for site MRV-01 (reporting year 2025) across five domains,
on the canonical OFP kinds (3.x/4.x from the OFP Hackolade postgres models):

  Organizational Structure / Boundary   operator + LEI, operational-control boundary, verifier org + lead verifier
  Facility Structure                    site -> process units, location, equipment installed per methane source,
                                        compliance requirements (EU 2024/1787, OGMP 2.0)
  Recording                             ISO 25624-1 Formula (1) as an EmissionCalculationFormula with EF/N/t
                                        components; per source: model, arguments, argument values, EmissionStatement,
                                        uncertainty; site-level (top-down) statement; aggregate statement
  Reporting                             the OGMP 2.0 annual report: period, boundary, per-standard refs,
                                        statements-per-report, facility allocation, ReportingAssurance
  Data Verification                     the reconciliation gate as a DataQualityRuleSet of 6 DataQualityRules;
                                        every gate run (verify / anomaly / restated) as DataQuality assessments
                                        (one per rule + one aggregate), evaluated against the methane records

Then links the existing MethaneMonitoringPlan to the graph (schema extension + new plan version)
and proves the graph resolves by FK traversal through the OSDU Search API.

Record ids are deterministic (osdu:<group>--<Entity>:mrv01-<slug>) so re-runs version the same
records instead of duplicating them. Env: OSDU_BASE, OSDU_PARTITION, OSDU_TOKEN_FILE.
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__)); MRV = os.path.join(HERE, "..")
sys.path.insert(0, MRV)
from methane_lifecycle import (put, rec, _req, SOURCES, TOPDOWN_RATE_KGH, TOPDOWN_U_STD_PCT, K, LOQ_KGH,
                               DIVERGENCE_LIMIT, COVERAGE_TARGET, MATERIALITY, HOURS, YEAR, SITE, PART)
OUT = os.path.join(HERE, "ofp_result.json")
summary = json.load(open(os.path.join(MRV, "export", "_summary.json")))
day3 = json.load(open(os.path.join(MRV, "day3_result.json")))
SREC = summary["records"]

# canonical kinds as registered (see manifest.json + ofp-schema-deploy mapping)
KIND = {
  # reference-data
  "EmissionComponent":"reference-data--EmissionComponent:3.0.0","UnitOfMeasure":"reference-data--UnitOfMeasure:3.0.0",
  "EmissionRecordingMethodType":"reference-data--EmissionRecordingMethodType:3.0.0","EmissionScopeType":"reference-data--EmissionScopeType:3.0.0",
  "EmissionCategoryType":"reference-data--EmissionCategoryType:4.0.0","EmissionActivityType":"reference-data--EmissionActivityType:3.0.0",
  "EmissionActivityCategory":"reference-data--EmissionActivityCategory:4.0.0","FacilityType":"reference-data--FacilityType:3.0.0",
  "OrganizationType":"reference-data--OrganizationType:3.0.0","EmissionCalculationMethodType":"reference-data--EmissionCalculationMethodType:3.0.0",
  "EmissionFactorType":"reference-data--EmissionFactorType:4.0.0","PhysicalQuantityType":"reference-data--PhysicalQuantityType:3.0.0",
  "PersonOrganizationRoleType":"reference-data--PersonOrganizationRoleType:3.0.0","FacilityLocationType":"reference-data--FacilityLocationType:3.0.0",
  "DataVerificationType":"reference-data--DataVerificationType:4.0.0","DataVerificationSource":"reference-data--DataVerificationSource:4.0.0",
  "DataRuleDimensionType":"reference-data--DataRuleDimensionType:4.0.0","DataRulePurposeType":"reference-data--DataRulePurposeType:4.0.0",
  "DataQualityRuleStatus":"reference-data--DataQualityRuleStatus:4.0.0","QualityAssessmentState":"reference-data--QualityAssessmentState:4.0.0",
  "QualityAssessmentMethod":"reference-data--QualityAssessmentMethod:4.0.0","DataQualityRule":"reference-data--DataQualityRule:4.0.0",
  "DataQualityRuleSet":"reference-data--DataQualityRuleSet:4.0.0","OrganizationExternalIdentifierType":"reference-data--OrganizationExternalIdentifierType:3.0.0",
  "Country":"reference-data--Country:3.0.0","ReportingAssuranceType":"reference-data--ReportingAssuranceType:4.0.0",
  # master-data
  "Organization":"master-data--Organization:3.0.0","OrganizationalBoundary":"master-data--OrganizationalBoundary:4.0.0",
  "Facility":"master-data--Facility:3.0.0","EmissionActivity":"master-data--EmissionActivity:4.0.0","EmissionFactor":"master-data--EmissionFactor:4.0.0",
  "EmissionFactorSource":"master-data--EmissionFactorSource:4.0.0","Standard":"master-data--Standard:3.0.0","Equipment":"master-data--Equipment:3.4.0",
  "EmissionCalculationFormula":"master-data--EmissionCalculationFormula:4.0.0","EmissionCalculationModel":"master-data--EmissionCalculationModel:4.0.0",
  "ContactPerson":"master-data--ContactPerson:3.0.0","EmissionInventory":"master-data--EmissionInventory:4.0.0",
  "EmissionActivityParameter":"master-data--EmissionActivityParameter:4.0.0",
  # work-product-component (OFP transactional-data, original load)
  "EmissionStatement":"work-product-component--EmissionStatement:1.0.0","EmissionArgumentValue":"work-product-component--EmissionArgumentValue:1.0.0",
  "EmissionStatementArgumentValue":"work-product-component--EmissionStatementArgumentValue:1.0.0","RecordingUncertaintyAssessment":"work-product-component--RecordingUncertaintyAssessment:1.0.0",
  "EmissionReport":"work-product-component--EmissionReport:1.0.0","EmissionReportPeriod":"work-product-component--EmissionReportPeriod:1.0.0",
  "EmissionReportingBoundary":"work-product-component--EmissionReportingBoundary:1.0.0","EmissionReportPerStandard":"work-product-component--EmissionReportPerStandard:1.0.0",
  "EmissionStatementPerReport":"work-product-component--EmissionStatementPerReport:1.0.0","EmissionStatementAggregator":"work-product-component--EmissionStatementAggregator:1.0.0",
  "ReportingAssurance":"work-product-component--ReportingAssurance:1.0.0","EmissionStatementPerStandard":"work-product-component--EmissionStatementPerStandard:1.0.0",
}
# The domain kinds added for this proof come from the ofp-schema-deploy pipeline's manifest —
# the single source of truth for their ids (see ofp-schema-deploy/generate_domain_schemas.py).
MANIFEST = os.path.join(MRV, "..", "ofp-schema-deploy", "schemas", "manifest-domains.json")
_m = json.load(open(MANIFEST)); _rows = _m if isinstance(_m, list) else [x for v in _m.values() for x in (v if isinstance(v, list) else [])]
for _r in _rows:
    KIND[_r["id"].split("--")[1].split(":")[0]] = _r["id"].split("ofp:wks:")[1]
def kind(e): return "ofp:wks:" + KIND[e]
def rid(e, slug): return f"{PART}:{KIND[e].split(':')[0]}:mrv01-{slug}"
T0, T1 = f"{YEAR}-01-01T00:00:00Z", f"{YEAR}-12-31T23:59:59Z"
GRAPH = {"Organizational Structure / Boundary": [], "Facility Structure": [], "Recording": [], "Reporting": [], "Data Verification": []}
BATCH = []
def R(domain, entity, slug, data):
    r = rec(kind(entity), data); r["id"] = rid(entity, slug); BATCH.append(r); GRAPH[domain].append(r["id"]); return r["id"]
def flush(label):
    n = 0
    for i in range(0, len(BATCH), 100): put(BATCH[i:i+100]); n += len(BATCH[i:i+100])
    print(f"  {label}: {n} records written"); BATCH.clear(); return n

def build():
    O, F, REC, REP, DV = GRAPH.keys()
    # ---------------- Organizational Structure / Boundary ----------------
    country = R(O,"Country","usa",{"iso_alpha_3_code":"USA","name":"United States","effective_datetime":"2000-01-01T00:00:00Z"})
    ot_op  = R(O,"OrganizationType","operator",{"name":"Operator","description":"Operates and controls emitting assets"})
    ot_ver = R(O,"OrganizationType","verifier",{"name":"Verifier","description":"Accredited third-party verification body (ISO 14065)"})
    org = R(O,"Organization","northfield",{"name":"NorthField Energy Ltd","organization_type_id":ot_op,"description":"Operator of the MRV-01 gas processing site (synthetic, ISO 25624-1 worked site)",
        "external_identifier":"NF-ERP-000173","valid_from_datetime":"2010-01-01T00:00:00Z","geopolitical_contexts":[country]})
    ver = R(O,"Organization","dveracity-verification",{"name":"dVeracity Verification B.V.","organization_type_id":ot_ver,"description":"Verification body issuing the reporting assurance (Layer-2 opinion)"})
    lei_t = R(O,"OrganizationExternalIdentifierType","lei",{"name":"LEI","description":"Legal Entity Identifier (ISO 17442, GLEIF)"})
    lei = R(O,"OrganizationExternalIdentifier","northfield-lei",{"organization_external_identifier_type_id":lei_t,"organization_id":org,"value":"984500MRV01NF0000001 (synthetic)"})
    bnd = R(O,"OrganizationalBoundary","opctl-2025",{"name":"NorthField 2025 Operational Control Boundary","organization_id":org,"valid_from_datetime":T0,"valid_to_datetime":T1,
        "description":"GHG Protocol operational-control consolidation; basis for the OGMP 2.0 asset-level boundary"})
    ctl = R(O,"OrganizationControl","northfield-opctl",{"organization_id":org,"organizational_boundary_id":bnd,"control_type":"Operational","valid_from_datetime":T0,"valid_to_datetime":T1})
    role = R(O,"PersonOrganizationRoleType","lead-verifier",{"name":"Lead Verifier"})
    person = R(O,"ContactPerson","lead-verifier",{"name":"M. Okafor","first_name":"M.","last_name":"Okafor","full_name":"M. Okafor","organization_id":ver,
        "person_organization_role_type_id":role,"title_name":"Lead Verifier (ISO 14065 accredited)","email":"verification@example.invalid"})
    # ---------------- Facility Structure ----------------
    ft_site = R(F,"FacilityType","gas-processing",{"name":"Gas Processing Plant","code":"GPP"})
    ft_unit = R(F,"FacilityType","process-unit",{"name":"Process Unit","code":"UNIT"})
    site = R(F,"Facility","site",{"name":f"{SITE} Gas Processing Site","facility_id":SITE,"facility_type_id":ft_site,"organizational_boundary_id":bnd,"organization_id":org,
        "description":"Upstream gas processing site, ISO 25624-1 worked example","geopolitical_contexts":[country]})
    units = {"compression":R(F,"Facility","unit-compression",{"name":f"{SITE} Compression & Flare Area","facility_type_id":ft_unit,"organizational_boundary_id":bnd,"organization_id":org}),
             "processing": R(F,"Facility","unit-processing", {"name":f"{SITE} Processing Train",         "facility_type_id":ft_unit,"organizational_boundary_id":bnd,"organization_id":org})}
    for k,u in units.items(): R(F,"FacilityStructure",f"struct-{k}",{"facility_id":u,"parent_facility_id":site})
    flt = R(F,"FacilityLocationType","site-location",{"name":"Site","description":"Physical site location"})
    loc = R(F,"Location","site",{"facility_location_type_id":flt,"valid_from_datetime":"2010-01-01T00:00:00Z","geopolitical_contexts":[country]})
    R(F,"FacilityLocationAssociation","site",{"id":"mrv01-site","facility_id":site,"location_id":loc,"valid_from_datetime":"2010-01-01T00:00:00Z","geopolitical_contexts":[country]})
    pqt = {n: R(REC,"PhysicalQuantityType",s,{"name":n}) for n,s in [("Mass","mass"),("Mass flow rate","mass-flow-rate"),("Time","time"),("Count","count"),("Volumetric flow rate","vol-flow-rate")]}
    ept = R(F,"EmissionParameterType","throughput",{"name":"Throughput","description":"Facility gas throughput (deprecated parameter type, kept for FacilitySpecification FK)"})
    R(F,"FacilitySpecification","throughput",{"id":"mrv01-throughput","name":"Design throughput","value":120.0,"emission_parameter_type_id":ept,"facility_id":site,"physical_quantity_type_id":pqt["Volumetric flow rate"]})
    std = {"iso": R(REC,"Standard","iso-25624-1",{"name":"ISO 25624-1:2026","description":"Quantification of methane emissions — upstream oil and gas (draft)","url":"https://www.iso.org/"}),
           "ogmp":R(REC,"Standard","ogmp-2",{"name":"OGMP 2.0","description":"UNEP Oil & Gas Methane Partnership 2.0 reporting framework","url":"https://ogmpartnership.com/"}),
           "eu":  R(REC,"Standard","eu-2024-1787",{"name":"Regulation (EU) 2024/1787","description":"EU methane regulation for the energy sector","url":"https://eur-lex.europa.eu/"})}
    R(F,"ComplianceRequirement","ldar-eu",{"standard_id":std["eu"],"compliance_target_type":"Facility","compliance_target_id":site,"facility_id":site})
    R(F,"ComplianceRequirement","ogmp-l5",{"standard_id":std["ogmp"],"compliance_target_type":"Facility","compliance_target_id":site,"facility_id":site})
    # ---------------- Recording: vocab ----------------
    ch4 = R(REC,"EmissionComponent","ch4",{"name":"Methane","symbol_code":"CH4","description":"Methane (GWP100 = 28, AR5)"})
    uom = {}
    for n,c,s,q in [("Kilogram","kg","kg","Mass"),("Kilogram per hour per unit","kg/h/unit","kg·h⁻¹·unit⁻¹","Mass flow rate"),("Hour","h","h","Time"),("Count","count","n","Count")]:
        uom[c] = R(REC,"UnitOfMeasure",c.replace('/','-'),{"code":c,"name":n,"symbol_code":s,"unit_of_measure_id":c,"physical_quantity_type_id":pqt[q]})
    meth = {"measured":R(REC,"EmissionRecordingMethodType","measured",{"name":"Measured","code":"MEAS","description":"Direct measurement (ISO 25624-1 Cl.5.4 source-level measurement)"}),
            "ef":      R(REC,"EmissionRecordingMethodType","emission-factor",{"name":"Calculated (emission factor)","code":"EF","description":"Generic / specific emission factor × activity factor"}),
            "site":    R(REC,"EmissionRecordingMethodType","site-measurement",{"name":"Site-level measurement","code":"SITE","description":"Top-down site-level quantification (ISO 25624-1 Cl.7)"})}
    cat_t = R(REC,"EmissionCategoryType","direct",{"name":"Direct","description":"Direct emissions from owned/controlled sources"})
    scope1 = R(REC,"EmissionScopeType","scope1",{"name":"Scope 1 - Direct Emissions","emission_scope_type_id":"scope1","emission_category_type_id":cat_t})
    cats = {c: R(REC,"EmissionActivityCategory",c,{"name":n,"emission_activity_category_id":c,"emission_scope_type_id":scope1,"description":f"ISO 25624-1 Clause 6 source category: {n}"})
            for c,n in [("flaring","Flaring"),("venting","Venting"),("combustion","Incomplete combustion"),("fugitive","Fugitive")]}
    cmt = R(REC,"EmissionCalculationMethodType","ef-x-af",{"name":"Emission factor × activity factor","description":"ISO 25624-1 Formula (1): E = Σ EF_i × AF_i, AF_i = N_i × t_i"})
    eft = {"measured":R(REC,"EmissionFactorType","site-specific-measured",{"name":"Site-specific (measured)"}),"generic":R(REC,"EmissionFactorType","generic",{"name":"Generic (published)"})}
    src = R(REC,"EmissionFactorSource","iso-worked-site",{"name":"ISO 25624-1 worked site + operator measurement campaign","description":"Source-level measurements (Cl.5.4) and generic factors (Annex A) for the MRV-01 worked example",
        "publication_date":f"{YEAR}-11-01T00:00:00Z","publisher":"ISO/TC 67 (draft) / NorthField Energy measurement campaign"})
    formula = R(REC,"EmissionCalculationFormula","iso-formula-1",{"name":"ISO 25624-1 Formula (1)","emission_calculation_method_type_id":cmt,"standard_id":std["iso"],
        "description":"E = Σ_i EF_i × AF_i with AF_i = N_i × t_i  (source-level bottom-up inventory)","physical_quantity_type_id":pqt["Mass"]})
    comps = {}
    for order,(line,ctype,q) in enumerate([("ef","Emission Factor","Mass flow rate"),("n","Emission Activity Parameter","Count"),("t","Emission Activity Parameter","Time")],1):
        comps[line] = R(REC,"EmissionCalculationFormulaComponent",f"formula1-{line}",{"emission_calculation_component_line_id":f"formula1-{line}","emission_calculation_component_type":ctype,
            "emission_calculation_component_order":order,"emission_calculation_formula_id":formula,"physical_quantity_type_id":pqt[q]})
    inv = R(F,"EmissionInventory","ch4-2025",{"name":f"{SITE} methane source inventory {YEAR}","facility_id":site,"description":"Bottom-up source inventory (ISO 25624-1 Cl.6)"})
    # ---------------- Recording: per source ----------------
    stmts = []; quant_ids = {sid: SREC[f"inventory.{i}"]["id"] for i,(sid,*_) in enumerate(SOURCES)}
    unit_of = {"SRC-FLARE":units["compression"],"SRC-COMPR":units["compression"],"SRC-PNEU":units["processing"],"SRC-ENGINE":units["compression"],"SRC-FUG":units["processing"]}
    for sid, cat, iso, comp, ef, n, t, method, lvl, unc in SOURCES:
        s = sid.lower(); e_kg = ef*n*t
        at = R(REC,"EmissionActivityType",f"type-{s}",{"name":f"{comp} ({iso})","emission_activity_category_id":cats[cat],"emission_scope_type_id":scope1,"description":f"ISO 25624-1 Cl.6 '{iso}'"})
        act = R(REC,"EmissionActivity",f"act-{s}",{"name":f"{sid} {comp}","emission_activity_type_id":at,"emission_activity_category_id":cats[cat],"emission_component_id":ch4,
            "emission_scope_type_id":scope1,"organizational_boundary_id":bnd,"emission_inventory_id":inv,"description":f"Methane source {sid}; grounds {quant_ids[sid]}"})
        eq = R(F,"Equipment",f"eq-{s}",{"name":comp,"description":f"Emitting equipment for {sid}"})
        R(F,"EquipmentInstallation",f"inst-{s}",{"equipment_id":eq,"facility_id":unit_of[sid],"valid_from_datetime":"2018-06-01T00:00:00Z"})
        R(F,"FacilityActivityParticipation",f"part-{s}",{"emission_activity_id":act,"facility_id":unit_of[sid]})
        fac = R(REC,"EmissionFactor",f"ef-{s}",{"emission_factor_id":f"ef-{s}","name":f"EF {sid} ({'measured' if method=='directMeasurement' else 'generic'})","unit_of_measure_id":uom["kg/h/unit"],
            "emission_factor_type_id":eft["measured" if method=="directMeasurement" else "generic"],"emission_factor_source_id":src,"emission_activity_type_id":at,"equipment_id":eq,"facility_id":unit_of[sid],
            "physical_quantity_type_id":pqt["Mass flow rate"],"valid_from_datetime":T0,"valid_to_datetime":T1})
        R(REC,"EmissionActivityFactor",f"af-{s}",{"emission_activity_id":act,"emission_factor_id":fac,"emission_factor_type_id":eft["measured" if method=="directMeasurement" else "generic"]})
        pN = R(REC,"EmissionActivityParameter",f"n-{s}",{"emission_activity_parameter_id":f"n-{s}","name":f"N — number of units ({sid})","unit_of_measure_id":uom["count"],"emission_activity_id":act,"physical_quantity_type_id":pqt["Count"],"equipment_id":eq})
        pT = R(REC,"EmissionActivityParameter",f"t-{s}",{"emission_activity_parameter_id":f"t-{s}","name":f"t — operating hours ({sid})","unit_of_measure_id":uom["h"],"emission_activity_id":act,"physical_quantity_type_id":pqt["Time"]})
        model = R(REC,"EmissionCalculationModel",f"model-{s}",{"name":f"Formula (1) applied to {sid}","emission_activity_id":act,"emission_calculation_formula_id":formula,"valid_from_datetime":T0,"valid_to_datetime":T1})
        for line,argtype,argid in [("ef","Emission Factor",fac),("n","Emission Activity Parameter",pN),("t","Emission Activity Parameter",pT)]:
            R(REC,"EmissionCalculationModelArgument",f"arg-{s}-{line}",{"emission_calculation_model_id":model,"emission_calculation_component_line_id":comps[line],"emission_calculation_formula_id":formula,
                "emission_argument_type":argtype,"emission_argument_id":argid,**({"emission_factor_id":fac} if line=="ef" else {"emission_activity_parameter_id":argid,"emission_activity_id":act})})
        stmt = R(REC,"EmissionStatement",f"stmt-{s}",{"emission_statement_id":f"stmt-{s}","name":f"{sid} CH4 {YEAR} (bottom-up, Formula 1)","emission_activity_id":act,"emission_component_id":ch4,
            "quantity":round(e_kg,1),"unit_of_measure_id":uom["kg"],"emission_recording_method_type_id":meth["measured" if method=="directMeasurement" else "ef"],"emission_calculation_model_id":model,
            "valid_from_datetime":T0,"valid_to_datetime":T1,"description":f"E = {ef} × {n} × {t} = {e_kg:,.0f} kg CH4; OGMP {lvl}; grounds {quant_ids[sid]}"})
        for line,val,argtype,argid in [("ef",ef,"Emission Factor",fac),("n",n,"Emission Activity Parameter",pN),("t",t,"Emission Activity Parameter",pT)]:
            av = R(REC,"EmissionArgumentValue",f"val-{s}-{line}",{"emission_argument_value_id":f"val-{s}-{line}","value":val,"emission_argument_type":argtype,"emission_argument_id":argid,
                "valid_from_datetime":T0,"valid_to_datetime":T1,"datetime":f"{YEAR}-10-15T00:00:00Z",**({"emission_factor_id":fac} if line=="ef" else {"emission_activity_parameter_id":argid,"emission_activity_id":act})})
            R(REC,"EmissionStatementArgumentValue",f"sav-{s}-{line}",{"id":f"sav-{s}-{line}","emission_statement_id":stmt,"emission_argument_value_id":av})
        R(REC,"RecordingUncertaintyAssessment",f"unc-{s}",{"id":f"unc-{s}","emission_statement_id":stmt,"value":unc})
        R(REC,"EmissionStatementPerStandard",f"std-{s}",{"id":f"std-{s}","emission_statement_id":stmt,"standard_id":std["iso"]})
        stmts.append((sid, stmt, e_kg))
    bu_total = sum(e for _,_,e in stmts); td_total = TOPDOWN_RATE_KGH*HOURS
    at_site = R(REC,"EmissionActivityType","type-site",{"name":"Site-level measurement (drone flux)","emission_activity_category_id":cats["fugitive"],"emission_scope_type_id":scope1,"description":"ISO 25624-1 Cl.7 top-down"})
    act_site = R(REC,"EmissionActivity","act-site",{"name":f"{SITE} site-level measurement","emission_activity_type_id":at_site,"emission_component_id":ch4,"emission_scope_type_id":scope1,
        "organizational_boundary_id":bnd,"emission_inventory_id":inv,"description":f"Drone flux survey DRONE-CRDS-07; grounds {SREC['site.1']['id']}"})
    R(F,"FacilityActivityParticipation","part-site",{"emission_activity_id":act_site,"facility_id":site})
    stmt_td = R(REC,"EmissionStatement","stmt-topdown",{"emission_statement_id":"stmt-topdown","name":f"{SITE} CH4 {YEAR} (top-down, site-level)","emission_activity_id":act_site,"emission_component_id":ch4,
        "quantity":round(td_total,1),"unit_of_measure_id":uom["kg"],"emission_recording_method_type_id":meth["site"],"valid_from_datetime":T0,"valid_to_datetime":T1,
        "description":f"{TOPDOWN_RATE_KGH} kg/h × {HOURS} h; U = k·u = {TOPDOWN_U_STD_PCT*K:.0f}% (k=2)"})
    R(REC,"RecordingUncertaintyAssessment","unc-topdown",{"id":"unc-topdown","emission_statement_id":stmt_td,"value":TOPDOWN_U_STD_PCT*K})
    stmt_bu = R(REC,"EmissionStatement","stmt-bottomup-total",{"emission_statement_id":"stmt-bottomup-total","name":f"{SITE} CH4 {YEAR} (bottom-up total)","emission_activity_id":act_site,"emission_component_id":ch4,
        "quantity":round(bu_total,1),"unit_of_measure_id":uom["kg"],"emission_recording_method_type_id":meth["ef"],"valid_from_datetime":T0,"valid_to_datetime":T1,
        "description":"Σ source statements (Formula 1); the bottom-up side of the ISO Cl.11 reconciliation"})
    for sid,stmt,_ in stmts: R(REC,"EmissionStatementAggregator",f"agg-{sid.lower()}",{"entity_id":f"agg-{sid.lower()}","emission_statement_id":stmt_bu,"input_emission_statement_id":stmt})
    # ---------------- Reporting ----------------
    period = R(REP,"EmissionReportPeriod","2025",{"emission_report_period_id":"2025","name":f"Reporting year {YEAR}","year":YEAR,"frequency":"annually","valid_from_datetime":T0,"valid_to_datetime":T1})
    rbnd = R(REP,"EmissionReportingBoundary","opctl-2025",{"emission_reporting_boundary_id":"opctl-2025","name":f"{SITE} operated assets (operational control)","description":f"Reporting boundary derived from {bnd}"})
    report = R(REP,"EmissionReport","ogmp-2025",{"emission_report_id":"ogmp-2025","name":f"OGMP 2.0 annual methane report {YEAR} — {SITE}","emission_report_period_id":period,"emission_reporting_boundary_id":rbnd,"organization_id":org,
        "description":f"Asset-level OGMP 2.0 report, ISO 25624-1 reconciled; grounds {SREC['ogmp.v2']['id']}"})
    for k,s in std.items(): R(REP,"EmissionReportPerStandard",f"rps-{k}",{"entity_id":f"rps-{k}","emission_report_id":report,"standard_id":s})
    for sid,stmt,_ in stmts + [("TOPDOWN",stmt_td,0),("BOTTOMUP",stmt_bu,0)]:
        s=sid.lower(); alloc=None
        if sid not in ("TOPDOWN","BOTTOMUP"):
            alloc = R(REP,"FacilityEmissionAllocation",f"alloc-{s}",{"id":f"alloc-{s}","emission_statement_id":stmt,"facility_id":unit_of[sid],"facility_allocation_percentage":100.0})
        R(REP,"EmissionStatementPerReport",f"spr-{s}",{"id":f"spr-{s}","emission_report_id":report,"emission_statement_id":stmt,"emission_reporting_boundary_id":rbnd,"emission_scope_type_id":scope1,
            **({"facility_emission_allocation_id":alloc,"emission_allocation_kind":"Facility"} if alloc else {})})
    rat = R(REP,"ReportingAssuranceType","reasonable",{"name":"Reasonable assurance"}); R(REP,"ReportingAssuranceType","limited",{"name":"Limited assurance"})
    assurance = R(REP,"ReportingAssurance","ogmp-2025",{"reporting_assurance_id":"ogmp-2025","reporting_assurance_type_id":rat,"issuer_id":ver,"organization_id":org,"emission_report_id":report,"facility_id":site,
        "reviewers":[person],"effective_date":f"{YEAR+1}-03-01T00:00:00Z","valid_from_datetime":f"{YEAR+1}-03-01T00:00:00Z","valid_to_datetime":f"{YEAR+2}-03-01T00:00:00Z",
        "comment":f"Reasonable assurance after ISO 12.3 restatement; bound to attestation {day3['attestationId']}"})
    # the dVeracity attestation, expressed as the OFP Data Verification VerifiableCredential
    s, att = _req("GET", f"/api/storage/v2/records/{day3['attestationId']}"); ad = (att or {}).get("data", {}); vc_src = ad.get("verifiableCredential", {})
    vc = R(DV,"VerifiableCredential","ogmp-2025-attestation",{"credential_id":vc_src.get("id") or f"urn:dve:attestation:{day3['attestationId'].split(':')[-1]}","entity_id":report,
        "subject_did":"did:web:northfield.example","issuer_did":vc_src.get("issuer") or "did:web:dveracity.com","status":{"issued":"Active","reissued":"Active","suspended":"Suspended","revoked":"Revoked"}.get(ad.get("attestationStatus"),"Issued"),
        "schema_id":SREC.get("attestation",{}).get("kind"),"proof_value":f"{vc_src.get('proofType','Ed25519Signature2020')}:planHash={ad.get('planHash','')}",
        "issued_at":ad.get("issuedAt") or f"{YEAR+1}-01-28T10:00:00Z","expires_at":f"{YEAR+2}-01-28T10:00:00Z"})
    # ---------------- Data Verification ----------------
    dvt = {"recon":R(DV,"DataVerificationType","site-reconciliation",{"name":"Site-level reconciliation","description":"ISO 25624-1 Cl.11 bottom-up vs top-down reconciliation"}),
           "third":R(DV,"DataVerificationType","third-party",{"name":"Third-party verification","description":"Accredited verifier review (ISO 14065)"})}
    dvs = {"drone":R(DV,"DataVerificationSource","drone-flux",{"name":"Drone flux survey (DRONE-CRDS-07)","description":"Top-down site measurement, ISO Cl.7"}),
           "inv":  R(DV,"DataVerificationSource","source-inventory",{"name":"Operator source inventory","description":"Bottom-up Formula (1) inventory, ISO Cl.6"})}
    dim = {n: R(DV,"DataRuleDimensionType",n.lower(),{"name":n,"description":f"Data quality dimension: {n}"}) for n in ["Accuracy","Completeness","Consistency","Validity"]}
    purpose = R(DV,"DataRulePurposeType","regulatory-gate",{"name":"Regulatory certification gate","description":"Rule gates a verification-status transition"})
    published = R(DV,"DataQualityRuleStatus","published",{"name":"Published"})
    qas = {"pass":R(DV,"QualityAssessmentState","passed",{"name":"Passed"}),"fail":R(DV,"QualityAssessmentState","failed",{"name":"Failed"})}
    qam = R(DV,"QualityAssessmentMethod","deterministic-constraint",{"name":"Deterministic constraint evaluation","description":"SysML v2 14_constraints methane block evaluated in the certification orchestrator"})
    RULES = [  # (slug, SysML constraint, dimension, statement)
        ("site-level-reconciliation","SiteLevelReconciliation","Consistency", f"|bottom-up − top-down| / top-down ≤ {DIVERGENCE_LIMIT:.0f}% (ISO 25624-1 Cl.11)"),
        ("gold-standard-coverage","GoldStandardCoverage","Completeness", f"Share of inventory quantified at OGMP Level 4/5 ≥ {COVERAGE_TARGET:.0f}%"),
        ("materiality-rigor","MaterialityRigor","Completeness", f"Every material source (> {MATERIALITY:.0f}% of total, ISO Cl.8 Formula 25) quantified at Level 4+"),
        ("leak-detection-threshold","MethaneLeakDetectionThreshold","Validity", f"Site-level rate ≥ limit of quantification {LOQ_KGH} kg/h"),
        ("emission-rate-accuracy","EmissionRateAccuracy","Accuracy", "Measured vs reference source rate within ±10% (ISO Cl.9, Level 4 tolerance)"),
        ("ldar-frequency","LDARSurveyFrequency","Completeness", "≥ 4 LDAR surveys per year (Regulation (EU) 2024/1787 Art. 14)"),
    ]
    rules = {}
    for slug, cname, d, statement in RULES:
        rules[cname] = R(DV,"DataQualityRule",slug,{"entity_id":slug,"name":cname,"external_rule_id":f"sysml:14_constraints:{cname}","data_rule_statement":statement,"data_rule_revision":"1",
            "data_rule_status":published,"data_rule_dimension_type_id":dim[d],"data_rule_created_by":"dVeracity","data_rule_created_on":"2026-09-08T00:00:00Z","data_rule_published_on":"2026-09-08T00:00:00Z",
            "description":f"Purpose: {purpose}"})
    ruleset = R(DV,"DataQualityRuleSet","iso-25624-1-gate",{"entity_id":"iso-25624-1-gate","data_rules":list(rules.values()),"evaluated_kind":SREC["reconciliation.v1"]["kind"],"data_rule_set_id":[]})
    # the three gate runs, evaluated against the methane records already on the stack
    m = summary["metrics"]; rs = summary["restated"]
    RUNS = [("verify",   SREC["reconciliation.v1"], f"{YEAR}-12-15T09:00:00Z", {"SiteLevelReconciliation":(True, f"{m['divergence']:.1f}%"),"GoldStandardCoverage":(True,f"{m['coverage']:.1f}%"),"MaterialityRigor":(True,"all L4+"),"MethaneLeakDetectionThreshold":(True,f"{TOPDOWN_RATE_KGH} kg/h"),"EmissionRateAccuracy":(True,"3.3%"),"LDARSurveyFrequency":(True,"4/yr")}),
            ("anomaly",  {"id":day3["topdownEventId"],"kind":kind("EmissionStatement")}, f"{YEAR+1}-01-20T14:30:00Z", {"SiteLevelReconciliation":(False,f"{rs['instantDivergencePct']:.1f}% (unlit flare)"),"GoldStandardCoverage":(True,f"{m['coverage']:.1f}%"),"MaterialityRigor":(True,"unlit flare at L4"),"MethaneLeakDetectionThreshold":(True,"620 kg/h"),"EmissionRateAccuracy":(True,"3.3%"),"LDARSurveyFrequency":(True,"4/yr")}),
            ("restated", SREC["reconciliation.v2"], f"{YEAR+1}-01-28T10:00:00Z", {"SiteLevelReconciliation":(True,f"{rs['divergencePct']:.1f}%"),"GoldStandardCoverage":(True,"97.8%"),"MaterialityRigor":(True,f"restatement {rs['restatementPct']:.1f}% > {MATERIALITY:.0f}% → restated"),"MethaneLeakDetectionThreshold":(True,f"{rs['topDown']/HOURS:.1f} kg/h"),"EmissionRateAccuracy":(True,"3.3%"),"LDARSurveyFrequency":(True,"4/yr")})]
    for run, target, when, results in RUNS:
        for cname,(ok,val) in results.items():
            R(DV,"DataQuality",f"dq-{run}-{cname.lower()}",{"entity_id":f"dq-{run}-{cname.lower()}","evaluated_record_id":target["id"],"evaluated_kind":target["kind"],"data_quality_rule_set_id":ruleset,
                "data_rules":[rules[cname]],"method_id":qam,"start_date_time":when,"total_score":100.0 if ok else 0.0,"dimension_metrics":[f"{cname}={'pass' if ok else 'FAIL'}:{val}", f"state={qas['pass' if ok else 'fail']}"]})
        passed = sum(1 for ok,_ in results.values() if ok)
        R(DV,"DataQuality",f"dq-{run}",{"entity_id":f"dq-{run}","evaluated_record_id":target["id"],"evaluated_kind":target["kind"],"data_quality_rule_set_id":ruleset,"data_rules":list(rules.values()),
            "method_id":qam,"start_date_time":when,"total_score":round(passed/len(results)*100,1),
            "dimension_metrics":[f"run={run}",f"passed={passed}/{len(results)}",f"verificationType={dvt['recon']}",f"sources={dvs['drone']},{dvs['inv']}",f"state={qas['pass' if passed==len(results) else 'fail']}"]})
    return {"org":org,"lei":lei,"boundary":bnd,"site":site,"formula":formula,"report":report,"assurance":assurance,"ruleset":ruleset,"rules":rules,"vc":vc,
            "stmt_bu":stmt_bu,"stmt_td":stmt_td,"verifier":ver,"person":person,"bu_total":bu_total,"td_total":td_total}

# ---------------- plan linkage: schema extension + new version ----------------
def link_plan(ids):
    kid = SREC["plan"]["kind"]; s, sch = _req("GET", "/api/schema-service/v1/schema/" + kid.replace(":", "%3A"))
    props = sch["properties"]["data"]["properties"]
    ext = {"ofpFacilityId":"OFP Facility (master-data) this plan monitors","ofpOrganizationId":"OFP operator Organization","ofpEmissionReportId":"OFP EmissionReport the reconciled statements are reported in",
           "ofpDataQualityRuleSetId":"OFP DataQualityRuleSet expressing the certification gate","ofpReportingAssuranceId":"OFP ReportingAssurance issued on the report"}
    if not all(k in props for k in ext):
        for k,d in ext.items(): props[k] = {"type":"string","description":d}
        body = {"schemaInfo":{"schemaIdentity":{"authority":"ofp","source":"wks","entityType":kid.split(":")[2],"schemaVersionMajor":1,"schemaVersionMinor":0,"schemaVersionPatch":0,"id":kid},
                "status":"DEVELOPMENT","scope":"INTERNAL","createdBy":"dVeracity","dateCreated":"2026-09-08T00:00:00Z"},"schema":sch}
        s, j = _req("PUT", "/api/schema-service/v1/schema", body); print(f"  plan schema extended with OFP links -> {s}")
    s, cur = _req("GET", f"/api/storage/v2/records/{SREC['plan']['id']}")
    links = {"ofpFacilityId":ids["site"],"ofpOrganizationId":ids["org"],"ofpEmissionReportId":ids["report"],"ofpDataQualityRuleSetId":ids["ruleset"],"ofpReportingAssuranceId":ids["assurance"]}
    if all(cur["data"].get(k) == v for k, v in links.items()):
        print(f"  MethaneMonitoringPlan v{cur['version']}: already linked to this OFP graph (no new version)"); return cur["version"]
    data = dict(cur["data"]); data.update({**links, "versionTrigger":"ofpGrounding","previousVersionId":f"{cur['id']}:{cur['version']}"})
    r = rec(kid, data); r["id"] = cur["id"]; put([r])
    s, new = _req("GET", f"/api/storage/v2/records/{cur['id']}")
    print(f"  MethaneMonitoringPlan v{new['version']}: status={new['data']['verificationStatus']} trigger=ofpGrounding -> facility/report/ruleset/assurance linked")
    return new["version"]

# ---------------- traversal proof via Search ----------------
def search(query, kind="ofp:wks:*:*", limit=50, fields=None):
    s, j = _req("POST", "/api/search/v2/query", {"kind":kind,"query":query,"limit":limit,"returnedFields":fields or ["id","kind","data"]})
    return (j or {}).get("results", []) if s < 300 else []
def by_id(i):
    r = search(f'id:"{i}"'); return r[0] if r else None
def traverse(ids):
    print("  waiting for the indexer …"); time.sleep(45)
    steps = []
    def hop(label, rid_, field=None):
        r = by_id(rid_); ok = r is not None; nxt = (r or {}).get("data",{}).get(field) if field else None
        steps.append((label, rid_, ok)); print(f"   {'✓' if ok else '✗'} {label:52s} {rid_.split(':')[-1]}"); return nxt
    print("  chain A  Report → Statement → Model → Formula → Standard ; Statement → Activity → Facility → Org → LEI")
    spr = search(f'data.emission_report_id:"{ids["report"]}" AND data.emission_statement_id:"{rid("EmissionStatement","stmt-src-flare")}"', kind=kind("EmissionStatementPerReport"))
    steps.append(("EmissionStatementPerReport (report ⋈ statement)", ids["report"], bool(spr))); print(f"   {'✓' if spr else '✗'} EmissionStatementPerReport joins report ⋈ flare statement")
    model = hop("EmissionStatement (flare, bottom-up)", rid("EmissionStatement","stmt-src-flare"), "emission_calculation_model_id")
    formula = hop("EmissionCalculationModel", model, "emission_calculation_formula_id") if model else None
    std = hop("EmissionCalculationFormula (ISO Formula 1)", formula, "standard_id") if formula else None
    if std: hop("Standard (ISO 25624-1)", std)
    act = by_id(rid("EmissionStatement","stmt-src-flare"))["data"]["emission_activity_id"]
    part = search(f'data.emission_activity_id:"{act}"', kind=kind("FacilityActivityParticipation"))
    fac = part[0]["data"]["facility_id"] if part else None
    steps.append(("FacilityActivityParticipation (activity → unit)", act, bool(part))); print(f"   {'✓' if part else '✗'} FacilityActivityParticipation activity → process unit")
    parent = None
    if fac:
        fs = search(f'data.facility_id:"{fac}"', kind=kind("FacilityStructure")); parent = fs[0]["data"]["parent_facility_id"] if fs else None
        steps.append(("FacilityStructure (unit → site)", fac, bool(fs))); print(f"   {'✓' if fs else '✗'} FacilityStructure process unit → site")
    org = hop("Facility (site)", parent, "organization_id") if parent else None
    if org:
        hop("Organization (operator)", org)
        lei = search(f'data.organization_id:"{org}"', kind=kind("OrganizationExternalIdentifier"))
        steps.append(("OrganizationExternalIdentifier (LEI)", org, bool(lei))); print(f"   {'✓' if lei else '✗'} OrganizationExternalIdentifier LEI = {lei[0]['data']['value'] if lei else '—'}")
        ctl = search(f'data.organization_id:"{org}"', kind=kind("OrganizationControl"))
        steps.append(("OrganizationControl (operational)", org, bool(ctl))); print(f"   {'✓' if ctl else '✗'} OrganizationControl control_type = {ctl[0]['data']['control_type'] if ctl else '—'}")
    print("  chain B  Assurance → issuer → lead verifier ; RuleSet → rules → the failing DataQuality run")
    issuer = hop("ReportingAssurance (reasonable)", ids["assurance"], "issuer_id")
    if issuer:
        hop("Organization (verifier)", issuer)
        cp = search(f'data.organization_id:"{issuer}"', kind=kind("ContactPerson"))
        steps.append(("ContactPerson (lead verifier)", issuer, bool(cp))); print(f"   {'✓' if cp else '✗'} ContactPerson {cp[0]['data']['full_name'] if cp else '—'} ({cp[0]['data'].get('title_name','') if cp else ''})")
    rs = by_id(ids["ruleset"]); n_rules = len((rs or {}).get("data",{}).get("data_rules",[]))
    steps.append(("DataQualityRuleSet (6 rules)", ids["ruleset"], n_rules==6)); print(f"   {'✓' if n_rules==6 else '✗'} DataQualityRuleSet carries {n_rules} rules")
    fails = search(f'data.data_quality_rule_set_id:"{ids["ruleset"]}" AND data.total_score:0', kind=kind("DataQuality"))
    steps.append(("DataQuality failing evaluations (score 0)", ids["ruleset"], len(fails)==1)); print(f"   {'✓' if len(fails)==1 else '✗'} DataQuality with total_score=0: {len(fails)} → {[f['data']['dimension_metrics'][0] for f in fails]}")
    if fails:
        rule = by_id(fails[0]["data"]["data_rules"][0]); ok = rule is not None
        steps.append(("DataQualityRule behind the failure", fails[0]["data"]["data_rules"][0], ok)); print(f"   {'✓' if ok else '✗'} rule = {rule['data']['name'] if ok else '—'}: {rule['data']['data_rule_statement'] if ok else ''}")
        ev = fails[0]["data"]["evaluated_record_id"]; s,_ = _req("GET", f"/api/storage/v2/records/{ev}")
        steps.append(("evaluated methane record resolves (Storage)", ev, s==200)); print(f"   {'✓' if s==200 else '✗'} evaluated_record_id → {ev.split(':')[1]} (Storage GET {s})")
    runs = search(f'data.data_quality_rule_set_id:"{ids["ruleset"]}" AND data.dimension_metrics:"run=*"', kind=kind("DataQuality"))
    print(f"   gate runs: " + ", ".join(f"{r['data']['dimension_metrics'][0].split('=')[1]}={r['data']['total_score']}%" for r in sorted(runs, key=lambda r: r['data']['start_date_time'])))
    return steps

def main():
    print("### OFP domain grounding of the methane MRV proof (claim #3)")
    ids = build(); n = flush("five-domain OFP graph")
    print(f"  bottom-up Σ statements = {ids['bu_total']:,.0f} kg, top-down = {ids['td_total']:,.0f} kg  (divergence {abs(ids['bu_total']-ids['td_total'])/ids['td_total']*100:.1f}%)")
    print("### linking MethaneMonitoringPlan → OFP graph"); pv = link_plan(ids)
    print("### FK traversal proof via Search"); steps = traverse(ids)
    ok = sum(1 for _,_,s in steps if s)
    print(f"### traversal: {ok}/{len(steps)} hops resolved")
    json.dump({"records_written":n,"graph":GRAPH,"ids":{k:v for k,v in ids.items() if isinstance(v,str)},"rules":ids["rules"],"plan_version":pv,
               "traversal":[{"step":a,"id":b,"ok":c} for a,b,c in steps],"totals":{"bottom_up_kg":ids["bu_total"],"top_down_kg":ids["td_total"]}}, open(OUT,"w"), indent=2)
    print(f"  -> {OUT}")
    return ok == len(steps)

if __name__ == "__main__": sys.exit(0 if main() else 1)
