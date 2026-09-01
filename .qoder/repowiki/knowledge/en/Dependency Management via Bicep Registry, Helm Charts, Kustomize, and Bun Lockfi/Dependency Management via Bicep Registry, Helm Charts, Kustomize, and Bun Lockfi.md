---
kind: dependency_management
name: Dependency Management via Bicep Registry, Helm Charts, Kustomize, and Bun Lockfile
category: dependency_management
scope:
    - '**'
source_files:
    - bicep/main.bicep
    - bicep/modules/app-configuration/version.json
    - bicep/modules/private-endpoint/version.json
    - bicep/modules/storage-account/version.json
    - charts/osdu-developer-service/Chart.yaml
    - charts/istio-ingress/Chart.yaml
    - software/apps/kustomization.yaml
    - software/components/kustomization.yaml
    - web/package.json
    - web/bun.lockb
    - web/Dockerfile
    - .github/dependabot.yml
    - src/docker-bake.hcl
---

## What system/approach is used

This repository manages dependencies across three distinct layers:

1. **Infrastructure-as-Code (IaC) modules** — The `bicep/` tree composes Azure resources by importing reusable modules from the **Azure Verified Modules (AVM) public registry** using the `br/public:avm/...` reference syntax with pinned semantic versions (e.g. `registry:0.9.1`, `vault:0.12.1`, `user-assigned-identity:0.4.1`). Each module directory under `bicep/modules/*` ships its own `version.json` declaring the published version and `pathFilters` that control what gets shipped to the registry.
2. **Kubernetes application packages** — Deployments are expressed as **Helm charts** under `charts/` (one chart per OSDU service/component) and as **Kustomize overlays** under `software/` and `stamp/`. Helm charts declare their own package metadata in `Chart.yaml`; Kustomize overlays compose base manifests without a lockfile of their own.
3. **Runtime application dependency** — The only source code with a traditional package manifest is the minimal Bun-based web server in `web/`, which uses `package.json` plus a `bun.lockb` lockfile and installs dependencies with `bun install --frozen-lockfile` inside its Dockerfile.

There is no Java `pom.xml` / `gradle` file at this repository root; the Java services referenced by `src/docker-bake.hcl` live in external repositories (see `src/core/repos`, `src/lib/repos`, `src/reference/repos`) and are pulled in as Git submodules or referenced by path during image builds.

## Key files and packages

- `bicep/main.bicep` — Root assembly that pins AVM modules by exact version (e.g. `br/public:avm/res/container-registry/registry:0.9.1`, `br/public:avm/res/key-vault/vault:0.12.1`, `br/public:avm/res/kubernetes-configuration/flux-configuration:0.3.5`).
- `bicep/modules/*/version.json` — Per-module version declarations consumed by the Bicep registry publishing pipeline.
- `charts/<chart>/Chart.yaml` — Helm chart metadata for each OSDU component (airflow-dags, blob-upload, istio-ingress, osdu-developer-service, etc.).
- `software/apps/kustomization.yaml` and `software/components/kustomization.yaml` — Kustomize composition files that assemble base + overlay manifests.
- `web/package.json` + `web/bun.lockb` — Node/Bun dependency manifest and lockfile for the landing-page server.
- `web/Dockerfile` — Enforces reproducible installs via `bun install --frozen-lockfile`.
- `.github/dependabot.yml` — Configures Dependabot to scan GitHub Actions workflows daily and label PRs with `dependencies`.
- `src/docker-bake.hcl` — Declares the set of Java service images built from `Dockerfile-java` (partition, entitlements, legal, schema, storage, file, indexer, search, crs-catalog, crs-conversion, unit), all pushed to `${REGISTRY}`.

## Architecture and conventions

- **Bicep modules are version-pinned**: Every `module <name> 'br/public:avm/...'` invocation includes an explicit `:<version>` suffix. This prevents drift when upstream AVM modules evolve.
- **Local modules coexist with registry modules**: Custom logic lives in `bicep/modules/<feature>/main.bicep` and is imported via relative paths (`modules/blade_configuration.bicep`, `modules/keyvault_secrets.bicep`), while third-party infrastructure components come from the public AVM registry.
- **Container images are not vendored**: Images are built on demand by `docker buildx bake` against `src/Dockerfile-java` and pushed to an Azure Container Registry whose name is parameterized through `REGISTRY` (configured in the Bicep deployment). No `*.tar.gz` artifacts are checked in.
- **Helm/Kustomize are the deployment units**: Charts under `charts/` are the canonical packaging format for Kubernetes resources; Kustomize overlays under `software/` and `stamp/` layer environment-specific customizations on top of those charts.
- **Only one language-level lockfile is tracked**: `web/bun.lockb` is committed alongside `web/package.json`; there are no `node_modules/`, `vendor/`, or `go.sum` files in the repo.
- **Dependabot scope is limited**: The current configuration only watches `github-actions` in the repository root; it does not yet watch Helm charts, Bicep modules, or the Bun package ecosystem.

## Conventions and constraints

- **Pin every AVM module to a semver tag** — observed in every `module ... 'br/public:avm/...:<version>'` call throughout `bicep/main.bicep` and `bicep/modules/*`.
- **Publish local modules with a `version.json`** — each `bicep/modules/<feature>/version.json` declares the version string and `pathFilters` (typically `["./main.json"]`) so the Bicep registry knows what to ship.
- **Use `--frozen-lockfile` for deterministic installs** — the Bun Dockerfile runs `bun install --frozen-lockfile`, ensuring the container build matches `bun.lockb` exactly.
- **External Java services are not vendored here** — `src/core`, `src/lib`, `src/reference` contain only `.gitignore` and `repos` directories pointing to external Git repos; their dependencies are managed in those separate repositories.
- **No private npm/Bun registry is configured** — the Bun install step pulls from the default registry; authentication would need to be supplied via CI secrets if a private registry were introduced.
- **Helm chart versions are declared per-chart** — each chart's `Chart.yaml` carries its own version/metadata; there is no single monorepo-wide chart versioning file.