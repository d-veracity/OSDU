---
kind: build_system
name: Azure Developer CLI + Bicep/Helm/Kustomize Build & Release Pipeline
category: build_system
scope:
    - '**'
source_files:
    - azure.yaml
    - bicep/main.bicep
    - bicepconfig.json
    - .github/workflows/test.yml
    - .github/workflows/release.yml
    - .github/workflows/web.yml
    - src/docker-bake.hcl
    - src/Dockerfile-java
    - web/Dockerfile
    - docker-compose.yaml
    - version.json
    - scripts/pre-provision.ps1
    - scripts/post-provision.ps1
    - scripts/settings.ps1
    - ofp-schema-deploy/generate_schemas.py
    - ofp-schema-deploy/register_schemas.sh
---

## What system/approach is used

The repository builds and deploys an OSDU stamp on Azure using a layered, multi-tool pipeline:

- **Infrastructure-as-Code**: Azure Bicep (`bicep/main.bicep` plus reusable modules under `bicep/modules/`) compiled to ARM JSON (`azuredeploy.json`).
- **Application packaging**: Java services built with Maven inside a multi-stage Docker image (`src/Dockerfile-java`), orchestrated via `docker buildx bake` (`src/docker-bake.hcl`) which defines one target per service (partition, entitlements, legal, schema, storage, file, indexer, indexer-queue, search, crs-catalog, crs-conversion, unit). The web frontend is a Bun app built with `docker build-push-action` from `web/Dockerfile`.
- **Kubernetes deployment**: Helm charts under `charts/` for application manifests, Kustomize overlays under `software/` and `stamp/` for composing components into releases, and FluxCD Kustomization resources that drive GitOps reconciliation on AKS.
- **Orchestration entry point**: `azure.yaml` declares the project as an Azure Developer CLI (`azd`) template (`template: osdu-developer@0.0.1`) with provider `bicep`, pre/post-provision hooks in PowerShell (`scripts/pre-provision.ps1`, `scripts/post-provision.ps1`, `scripts/settings.ps1`).
- **CI/CD**: GitHub Actions workflows under `.github/workflows/` — `test.yml` validates/provisions infrastructure on PRs/schedule/dispatch; `release.yml` bumps version, compiles Bicep, generates changelog and publishes a GitHub Release artifact; `web.yml` builds/pushes the web image to GHCR; `documentation.yml`, `scorecard.yml`, `label.yml`, `greet.yml` are auxiliary.

## Key files and packages

| Area | Files |
|---|---|
| azd project root | `azure.yaml`, `parameters.json`, `parameters-template.json`, `parameters-eastus2*.json` |
| IaC | `bicep/main.bicep`, `bicep/main-minimal.bicep`, `bicepconfig.json`, `bicep/modules/*/main.bicep` |
| CI pipelines | `.github/workflows/test.yml`, `.github/workflows/release.yml`, `.github/workflows/web.yml`, `.github/workflows/documentation.yml`, `.github/workflows/scorecard.yml` |
| Docker images | `src/Dockerfile-java`, `src/docker-bake.hcl`, `web/Dockerfile`, `docker-compose.yaml` |
| Kubernetes | `charts/*/Chart.yaml`, `software/applications/*/kustomization.yaml`, `software/components/*/namespace.yaml`, `stamp/*/kustomize.yaml` |
| Versioning | `version.json` (single source of truth for release tag) |
| Schema build | `ofp-schema-deploy/generate_schemas.py`, `generate_transaction_schemas.py`, `register_schemas.sh` |
| Dev scripts | `scripts/pre-provision.ps1`, `scripts/post-provision.ps1`, `scripts/settings.ps1`, `scripts/template.yaml` |

## Architecture and conventions

### Infrastructure build flow
1. `azd provision` reads `azure.yaml`, runs `preprovision` hook, then invokes `az bicep build bicep/main.bicep --outfile azuredeploy.json` and deploys to the configured resource group.
2. On CI, `test.yml` first runs PSRule against `parameters.json`, then `az deployment group validate` / `what-if`, then provisions via `azd provision --no-prompt`, waits for Flux compliance (`Compliant` state within 45 min), and finally tears down the resource group and purges deleted Key Vaults/App Configurations.
3. `release.yml` uses `anothrNick/github-tag-action` to bump `version.json`, rebuilds `azuredeploy.json`, commits both back to the repo, generates a changelog via `mikepenz/release-changelog-builder-action`, and creates a GitHub Release with `azuredeploy.json` as an artifact.

### Application image build flow
- Each Java service is a separate `docker-bake.hcl` target sharing `Dockerfile-java`. The builder stage installs Maven, copies only the service's `SERVICE_PATH` into `/app/src`, runs `mvn clean install` with optional `-pl` module selection (`INCLUDE_MODULES_OPT`) and optional test skipping (`SKIP_TESTS=true`), then locates the Spring Boot jar.
- The runtime stage pulls a minimal CBL-Mariner base, installs Azul JDK 17, downloads the Application Insights Java agent (versioned via `APPLICATIONINSIGHTS_VERSION` env var), copies the built JAR and any `EXTRA_FILES` (e.g. CRS catalog JSON, Apache SIS setup), sets JVM heap defaults (`InitialRAMPercentage=25`, `MaxRAMPercentage=50`), and launches via `java -javaagent:... -jar app.jar`.
- Multi-platform builds are controlled by the `BUILD_ARM` variable: default `auto` produces `linux/amd64`; setting it to `true` adds `linux/arm64`.
- The web app uses a single-stage Bun image (`oven/bun:1`), installs dependencies with `bun install --frozen-lockfile`, and runs `index.ts` on port 8080.

### Kubernetes packaging convention
- Helm charts live under `charts/` and follow the standard `Chart.yaml` + `templates/` layout with `_helpers.tpl` partials.
- Kustomize overlays under `software/applications/` and `software/components/` compose individual YAML manifests into named applications; `stamp/` provides top-level `kustomize.yaml` entries that aggregate them.
- FluxCD is the delivery mechanism: the AKS cluster has a `flux-system` Kustomization that watches this repo and reconciles `stamp/` and `charts/` changes.

### Versioning strategy
- A single `version.json` at the repo root holds `{"release": "<tag>"}`. The release workflow updates it via `github-tag-action` and commits it alongside the generated `azuredeploy.json`.
- Helm chart versions are managed per-chart via each chart's own `Chart.yaml` `version` field.
- Container images are tagged by branch/ref through `docker/metadata-action` (web workflow tags `main` and `latest`).

### Conventions and constraints
- All infrastructure deployments go through `azd` — direct `az deployment` calls are bypassed in normal flows.
- Bicep analyzers are enabled in `bicepconfig.json` with specific rules set to warning or off (`no-hardcoded-env-urls`, `explicit-values-for-loc-params`, `no-unnecessary-dependson` disabled; `no-unused-vars`, `prefer-interpolation`, `secure-parameter-default`, `simplify-interpolation` warn).
- CI secrets/vars required: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_PRINCIPAL_ID`, `EMAIL_ADDRESS`, `AZD_INITIAL_ENVIRONMENT_CONFIG`, `AZURE_LOCATION`, `AZURE_ENV_NAME`.
- The test workflow enforces a 45-minute timeout waiting for Flux compliance before failing the Verify job.
- Cleanup jobs always run (`if: always()`) and delete the resource group plus purge soft-deleted Key Vaults and App Configurations.
- The OFP schema build is a separate concern: Python scripts generate draft-07 JSON bodies from Hackolade models and a shell script registers them against the OSDU Schema Service.
- Local development uses `docker-compose.yaml` to run the Bun web server on port 8000.