# Orphaned OFP kinds on cimpl-stack "dev" (do not use)

OSDU schemas cannot be deleted. On 2026-09-08 two registration passes for the methane-proof
domain entities bypassed this pipeline and hand-assigned versions/groups. They were superseded
the same day by `generate_domain_schemas.py` (kind id taken from the Hackolade collection's
own `id`; `transactional-data` → `work-product-component:1.0.0`). The superseded kinds remain
registered as DEVELOPMENT/INTERNAL with no records. Use `schemas/manifest-domains.json` for
the correct ids.

| superseded kind | correct kind |
|---|---|
| reference-data--{Country, DataQualityRuleStatus, DataRuleDimensionType, DataRulePurposeType, DataVerificationSource, DataVerificationType, EmissionParameterType, OrganizationExternalIdentifierType, QualityAssessmentMethod, QualityAssessmentState, ReportingAssuranceType}:1.0.0 | same name at **4.0.0** |
| reference-data--{Country, OrganizationExternalIdentifierType}:3.0.0 | same name at **4.0.0** |
| master-data--{DataQualityRule, DataQualityRuleSet}:1.0.0 | **reference-data**--…:4.0.0 (group per model) |
| master-data--{ComplianceRequirement, FacilityActivityParticipation, FacilityStructure, Location, OrganizationControl, OrganizationExternalIdentifier}:1.0.0 | same name at **4.0.0** |
| master-data--{FacilityActivityParticipation, FacilityStructure, Location, OrganizationExternalIdentifier}:3.0.0 | same name at **4.0.0** |
| master-data--EmissionParameterType:3.0.0 | **reference-data**--EmissionParameterType:4.0.0 |
| master-data--OrganizationPersonAssociation:1.0.0 | none — collection has no canonical id in the OFP model |
| master-data--{EmissionActivityFactor, EmissionCalculationFormulaComponent, EmissionCalculationModelArgument, EquipmentInstallation, FacilityLocationAssociation, FacilitySpecification}:1.0.0 | **work-product-component**--…:1.0.0 |
| work-product-component--{DataQuality, EmissionActivityFactor, EmissionCalculationFormulaComponent, EmissionCalculationModelArgument, EquipmentInstallation}:4.0.0 | same name at **1.0.0** |
| work-product-component--{FacilityEmissionAllocation, FacilityLocationAssociation, FacilitySpecification}:3.0.0 | same name at **1.0.0** |

41 kinds total. Stack count after cleanup of bodies: 158 = 89 (prior) + 28 (domain, correct) + 41 (orphans).
