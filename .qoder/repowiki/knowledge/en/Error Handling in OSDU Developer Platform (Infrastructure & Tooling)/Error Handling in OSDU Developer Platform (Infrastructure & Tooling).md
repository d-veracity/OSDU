---
kind: error_handling
name: Error Handling in OSDU Developer Platform (Infrastructure & Tooling)
category: error_handling
scope:
    - '**'
source_files:
    - ofp-schema-deploy/register_schemas.sh
    - ofp-schema-deploy/generate_schemas.py
    - charts/osdu-developer-base/templates/envoy-filter.yaml
    - charts/osdu-developer-init/templates/schema-init.yaml
    - charts/osdu-developer-init/templates/partition-init.yaml
    - charts/osdu-developer-init/templates/user-init.yaml
    - charts/osdu-developer-init/templates/entitlement-init.yaml
    - charts/osdu-developer-init/templates/workflow-init.yaml
    - charts/airflow-dags/scripts/csv-dag.sh
    - bicep/modules/deploy-scripts/blob_upload.sh
    - bicep/modules/deploy-scripts/software-upload.sh
    - bicep/modules/script-share-csvdag/script.sh
    - bicep/modules/script-share-upload/script.sh
    - bicep/modules/software-upload/script.sh
    - web/index.ts
---

## Overview

This repository is an infrastructure and tooling assembly for the OSDU Developer Platform. It contains no application source code (no Go/Java services, no Node.js backend) — only Bicep IaC, Helm charts, Kustomize manifests, Bash/Python/TypeScript utility scripts, and a minimal Bun static web server. Consequently, error handling is expressed entirely through shell exit codes, HTTP status checks, Kubernetes Job failure semantics, and Envoy Lua logging.

## Shell Scripts: Fail-Fast with `set -e` / `set -euo pipefail`

Every operational script adopts strict error propagation:
- `ofp-schema-deploy/register_schemas.sh` uses `set -euo pipefail` and exits non-zero on any curl failure, unknown mode, or missing token (`exit 1`, `exit 2`).
- All Bicep module helper scripts (`bicep/modules/*/script.sh`, `bicep/modules/deploy-scripts/*.sh`, `charts/airflow-dags/scripts/csv-dag.sh`) start with `set -e` so that any failing command aborts the job immediately.
- Errors are surfaced via `echo "ERROR: ..."; exit <code>` patterns rather than custom error types.

## HTTP/API Error Handling

- **Schema registration** (`register_schemas.sh`): each POST to the Schema Service captures the HTTP status code via `curl -w "%{http_code}"`. A `2xx` response is treated as success; `400` containing "already present" is idempotently skipped; any other code prints the response body and exits `1`.
- **Init jobs** (`charts/osdu-developer-init/templates/{partition,user,entitlement,workflow}-init.yaml`): scripts capture `HTTP_STATUS_CODE` from curl responses and print `Error: Unexpected HTTP status code $HTTP_STATUS_CODE` before exiting non-zero.
- **Schema init job** (`schema-init.yaml`): runs `DeploySharedSchemas.py`; if its return code is non-zero, sets `currentStatus="failure"` and writes a ConfigMap message, then exits `1`.
- **Azure token acquisition** (`token.py` embedded in `schema-init.yaml`): catches MSAL exceptions, prints `Error getting token: {error_description}`, and exits `1`.

## Kubernetes Job Failure Semantics

All bootstrapping tasks are implemented as Kubernetes Jobs (`batch/v1.Job`) with explicit `activeDeadlineSeconds` and `restartPolicy: Never`. A non-zero exit code marks the Job as Failed, which is the primary failure signal consumed by Helm/Flux/Kustomize deployments. There are no liveness/readiness probes on these one-shot Jobs; failure is binary (success/failure).

## Envoy Lua Filter: Logging-Based Error Detection

The Istio `EnvoyFilter` (`charts/osdu-developer-base/templates/envoy-filter.yaml`) injects Lua code into the inbound HTTP pipeline to extract user/app identity from Azure AD JWTs. Instead of returning errors, it uses structured log levels:
- `logError` when no valid claim is found, no JWT metadata exists, no `aud` claim is present, or the issuer is unknown.
- `logWarn` for fallback paths (e.g., using `appid` instead of `unique_name`).
- `logInfo`/`logDebug` for normal flow tracing.
Errors here do not block requests but produce observable logs for operators to detect misconfiguration.

## Web Server: Minimal Error Responses

The Bun-based landing page server (`web/index.ts`) returns plain text `"Not Found"` with HTTP 404 for unrecognized paths. There is no global error handler; unhandled exceptions would bubble to Bun's default process-level handler.

## Python Generator: Print-Based Diagnostics

`ofp-schema-deploy/generate_schemas.py` does not raise exceptions for mapping mismatches; instead it accumulates unmatched entities in an `unmatched` list and prints them at the end. The script always exits `0` unless the filesystem raises an OS error.

## Conventions Observed

| Area | Convention |
|---|---|
| Shell scripts | Start with `set -e` (or `set -euo pipefail`); use `exit 1`/`exit 2` for failures; never swallow errors silently. |
| HTTP calls | Capture and inspect HTTP status codes; treat anything outside `2xx` as failure except known idempotent cases (e.g., "already present"). |
| Kubernetes Jobs | Use non-zero exit codes to signal failure; rely on `activeDeadlineSeconds` to bound runtime. |
| Envoy filters | Prefer structured logging (`logError`/`logWarn`/`logInfo`/`logDebug`) over request rejection. |
| Python utilities | Catch broad `Exception` blocks, print human-readable messages, and `exit(1)`; avoid raising typed exceptions up the stack. |
| Web server | Return explicit HTTP 404 for unknown routes; no centralized error middleware. |

## Constraints

- No application-layer error types, sentinel errors, or exception hierarchies exist because this repo contains no business logic services.
- Error propagation is strictly fail-fast at the script level; there is no retry or circuit-breaker logic in the provided scripts (retries would need to be added by callers such as Flux/Helm).