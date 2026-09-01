---
kind: logging_system
name: Observability and Logging Stack (Loki/Grafana/Prometheus + Azure Monitor + Application Insights)
category: logging_system
scope:
    - '**'
source_files:
    - software/components/observability/loki.yaml
    - software/components/observability/grafana.yaml
    - software/components/observability/prometheus.yaml
    - software/components/observability/jaeger.yaml
    - software/components/observability/kiali.yaml
    - bicep/modules/managed-cluster/main.json
    - charts/osdu-developer-base/templates/envoy-filter.yaml
    - src/Application_Insights.md
---

## What system/approach is used

This repository does not define an application-level logging framework inside the OSDU services themselves — the `src/` directory only contains placeholder `.gitignore` files for Java repos. Instead, the project ships a complete **observability/logging stack** that is deployed onto the AKS cluster via Helm/Kustomize manifests under `software/components/observability/`. The stack consists of:

- **Loki** (single-binary, v2.7.3) in the `istio-system` namespace as the log aggregation sink, configured with filesystem-backed storage (`/var/loki`) and schema v12.
- **Grafana** (v10.1.5) provisioned with Loki and Prometheus datasources, plus Istio dashboards mounted from ConfigMaps.
- **Prometheus** (scraping metrics from Kubernetes pods).
- **Jaeger** and **Kiali** for distributed tracing and service mesh visualization.
- **Azure Monitor / Log Analytics** diagnostic settings wired into the AKS Bicep module (`bicep/modules/managed-cluster/main.json`) to stream platform logs to Log Analytics or Event Hubs.
- **Application Insights** guidance for local Java development (`src/Application_Insights.md`), requiring the `applicationinsights-agent.jar` JVM agent and `APPINSIGHTS_LOGGING_ENABLED=true` environment variable.

The repo also includes an Envoy filter (`charts/osdu-developer-base/templates/envoy-filter.yaml`) that uses `request_handle:logInfo/logWarn/logError` to emit structured request headers and AAD token claim decisions at the ingress proxy layer.

## Key files and packages

- `software/components/observability/loki.yaml` — Loki StatefulSet, Service, ConfigMap (`config.yaml`, `runtime-config.yaml`), headless service, and persistent volume claims.
- `software/components/observability/grafana.yaml` — Grafana Deployment, Service, ConfigMap (`grafana.ini`, `datasources.yaml`, `dashboardproviders.yaml`), and bundled Istio dashboard JSONs.
- `software/components/observability/prometheus.yaml`, `jaeger.yaml`, `kiali.yaml` — additional observability components.
- `bicep/modules/managed-cluster/main.json` — AKS diagnostic settings (`logCategoriesAndGroups`, `logAnalyticsDestinationType`, `monitoringWorkspaceId`, `enableContainerInsights`, `syslogPort`).
- `charts/osdu-developer-base/templates/envoy-filter.yaml` — Lua-based Envoy filter using `logInfo`/`logWarn`/`logError` to log header inspection and AAD user-id extraction.
- `src/Application_Insights.md` — documentation for enabling Application Insights logging for local Java services via `-javaagent` and `APPLICATIONINSIGHTS_CONNECTION_STRING`.
- `web/index.ts` — minimal Bun static server that uses plain `console.log` for startup output.
- `ofp-schema-deploy/generate_schemas.py`, `generate_transaction_schemas.py` — Python scripts that use `print()` for build-time status output.

## Architecture and conventions

- **Log sink**: All application logs are expected to be emitted to stdout/stderr so that the Kubernetes container runtime can capture them; Loki is installed as the central log aggregator on the cluster.
- **Log retention**: Loki is configured with `reject_old_samples_max_age: 168h` (7 days) and no explicit retention deletion policy (`retention_period: 0`), relying on underlying PVC lifecycle.
- **Visualization**: Grafana is pre-provisioned with Loki and Prometheus datasources and Istio dashboards, giving a ready-to-use UI for both metrics and logs.
- **Platform diagnostics**: AKS resources expose diagnostic settings parameters (`diagnosticSettings[].logCategoriesAndGroups[]`, `monitoringWorkspaceId`, `enableContainerInsights`) that ship control-plane and node logs to Azure Log Analytics.
- **Ingress-side logging**: The Envoy Lua filter logs each request's headers and the outcome of AAD token claim parsing at `logInfo`/`logWarn`/`logError` levels, providing per-request context before requests reach backend services.
- **Local dev logging**: For Java services run locally, the documented convention is to attach the Application Insights Java agent JAR via `-javaagent` and set `APPINSIGHTS_LOGGING_ENABLED=true` plus `APPLICATIONINSIGHTS_CONNECTION_STRING`.

## Conventions and constraints

- Application code in this repo does not import a logging library; any console output goes through language defaults (`console.log` in TypeScript, `print()` in Python). Structured logging is therefore expected to come from the surrounding infrastructure (Envoy, container runtime, Azure Monitor) rather than from custom SDKs.
- Loki runs unauthenticated (`auth_enabled: false`) within the cluster; access to logs is gated by Grafana authentication (anonymous admin enabled in the default config) and network policies, not by Loki itself.
- Grafana logs are written to the console (`[log] mode = console`) via `grafana.ini`, keeping logs in the pod stream for the Kubernetes log collector.
- AKS diagnostic settings are parameterized through Bicep inputs (`logCategoriesAndGroups`, `logAnalyticsDestinationType`, `monitoringWorkspaceId`, `enableContainerInsights`, `syslogPort`); changing these values redeploys diagnostic pipelines to Log Analytics or Event Hubs.
- No repository-wide log level policy is enforced in code; log severity is expressed through Envoy's `logInfo`/`logWarn`/`logError` calls in the ingress filter and through standard stdout/stderr semantics elsewhere.