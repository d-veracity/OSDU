---
kind: configuration_system
name: 'Multi-Layer Configuration System: Azure App Config, Key Vault, Helm Values & Feature Flags'
category: configuration_system
scope:
    - '**'
source_files:
    - docs/src/feature_flags.md
    - bicep/main.parameters.json
    - bicep/main.bicep
    - bicep/modules/app-configuration/main.bicep
    - charts/osdu-developer-base/templates/kv-secrets.yaml
    - charts/osdu-developer-base/templates/config-map-values.yaml
    - charts/osdu-developer-base/values.yaml
    - software/applications/config-map-values.yaml
    - scripts/settings.ps1
    - scripts/pre-provision.ps1
    - scripts/post-provision.ps1
    - azure.yaml
---

## Overview

The OSDU Developer Platform uses a multi-layered configuration system that combines Azure infrastructure-as-code parameters, Kubernetes secrets/config maps, Helm values, and runtime feature flags. Configuration flows from environment variables through Azure Developer CLI (`azd`) into Bicep ARM templates, then into Azure services (App Configuration, Key Vault), and finally into Kubernetes workloads via Helm charts.

## Layer 1: Provisioning Feature Flags (Environment Variables)

Configuration begins as `azd` environment variables set before provisioning. The documented feature flags in `docs/src/feature_flags.md` define the complete surface:
- **Azure region/subscription**: `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION`
- **Entra ID app**: `AZURE_CLIENT_ID`, `AZURE_CLIENT_PRINCIPAL_OID`, `AZURE_TENANT_ID`
- **Infrastructure overrides**: `CLUSTER_INGRESS`, `VMSIZE_SYSTEM_POOL`, `VMSIZE_ZONE_POOL`, `VMSIZE_USER_POOL`, `ENABLE_NODE_AUTO_PROVISIONING`, `ENABLE_PRIVATE_CLUSTER`
- **Software selection**: `ENABLE_SOFTWARE`, `ENABLE_PRIVATE_SOFTWARE`, `ENABLE_OSDU_CORE`, `ENABLE_OSDU_REFERENCE`, `SOFTWARE_VERSION`, `SOFTWARE_REPOSITORY`, `SOFTWARE_BRANCH`
- **Experimental features**: `ENABLE_EXPERIMENTAL`, `ENABLE_ADMIN_UI`
- **VNET injection**: `VIRTUAL_NETWORK_GROUP`, `VIRTUAL_NETWORK_NAME`, `VIRTUAL_NETWORK_PREFIX`, `VIRTUAL_NETWORK_IDENTITY`, `AKS_SUBNET_NAME`, `AKS_SUBNET_PREFIX`, `POD_SUBNET_NAME`, `POD_SUBNET_PREFIX`

These are consumed by `bicep/main.parameters.json`, which maps each flag to a Bicep parameter using `${ENV_VAR}` substitution syntax. For example, `clusterSoftware.value.repository` reads from `SOFTWARE_REPOSITORY`. Scripts in `scripts/pre-provision.ps1` and `scripts/post-provision.ps1` read/write these variables via `azd env set/get` during provisioning hooks defined in `azure.yaml`.

## Layer 2: Azure Infrastructure Secrets & Configuration

Two Azure services hold sensitive and runtime configuration:

**Azure Key Vault** — Managed via `charts/osdu-developer-base/templates/kv-secrets.yaml`, which creates a `SecretProviderClass` that mounts Key Vault secrets into pods using the Azure CSI driver with workload identity authentication. Secrets mapped include `app-dev-sp-password`, `keyvault-uri`, `insights-key`, `system-storage`, `airflow-admin-username/password`, etc. The mapping is driven by `.Values.azure.clientId`, `.Values.azure.keyvaultName`, and `.Values.azure.tenantId`.

**Azure App Configuration** — Deployed via `bicep/modules/app-configuration/main.bicep`, which provisions an `Microsoft.AppConfiguration/configurationStores` resource with optional CMEK encryption, private link, RBAC, and diagnostic settings. A nested module `key_values.bicep` creates key-value pairs passed via the `keyValues` parameter array. At runtime, `charts/osdu-developer-base/templates/config-map-values.yaml` declares an `AzureAppConfigurationProvider` CRD that syncs keys matching selector `configmap-common-values` into a Kubernetes ConfigMap named `configmap-common-values`, using workload identity for auth.

## Layer 3: Helm Chart Values

Helm values flow through multiple files:
- `charts/osdu-developer-base/values.yaml` defines defaults under `azure.enabled`, `azure.tenantId`, `azure.clientId`, `azure.keyvaultName`, plus `resourceLimits` and optional `blobUpload`/`share` sections.
- `software/applications/config-map-values.yaml` provides a live `ConfigMap` containing a `values.yaml` blob that overrides base chart values at deploy time.
- `parameters.json` and `parameters-template.json` provide ARM deployment parameter defaults.

## Layer 4: Runtime Service Configuration

Per-service environment variables are generated from `scripts/template.yaml` by `scripts/settings.ps1`, which parses YAML structure and emits per-service `.env` files under `src/<group>/<service>/RUN_<service>.env` and `TEST_<service>.env`. Template placeholders use `%VAR%` syntax resolved from environment variables. The script also generates `.vscode/settings.json` with REST client environment variables (`TENANT_ID`, `CLIENT_ID`, `HOST`, `REFRESH_TOKEN`, `DATA_PARTITION`).

## Architecture Decisions

1. **Separation of concerns**: Infrastructure config (Bicep params) is distinct from runtime secrets (Key Vault) and application config (App Configuration → ConfigMap).
2. **Workload Identity**: Both Key Vault access and App Configuration sync use Kubernetes workload identity rather than service principals or managed identities attached to nodes.
3. **Feature-flag-driven provisioning**: All major deployment switches are exposed as `AZURE_*` / `ENABLE_*` / `SOFTWARE_*` environment variables, making deployments reproducible via `azd env`.
4. **Template-based code generation**: Service-level configs are not hand-edited; they are generated from `scripts/template.yaml` using PowerShell parsing, ensuring consistency across core/reference/experimental services.
5. **Label-scoped App Configuration**: Keys are filtered by label `configmap-common-values` so different environments can coexist in the same App Configuration store.

## Conventions

- Feature flags are documented centrally in `docs/src/feature_flags.md` and must be set via `azd env set` before provisioning.
- Sensitive values never appear in Helm values files; they come from Key Vault via CSI secret provider.
- Non-sensitive cluster-wide values are injected via `AzureAppConfigurationProvider` into a shared ConfigMap consumed by downstream charts.
- Per-service env files follow the naming pattern `<TASK>_<SERVICE>.env` (e.g., `run_partition.env`, `test_entitlements.env`).
- Bicep parameter files use `${ENV_VAR}` interpolation to bind `azd` environment variables to ARM template parameters.