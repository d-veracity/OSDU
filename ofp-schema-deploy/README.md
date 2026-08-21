# OFP → OSDU schema deployment

Deploys the Open Footprint (OFP) entity model onto an OSDU platform as
`ofp`-authority schemas in the OSDU **Schema Service**.

## What's here

| File | Purpose |
|---|---|
| `generate_schemas.py` | Generates OSDU draft-07 schema bodies from the OFP model. |
| `schemas/*.json` | Generated Schema Service POST bodies (one per kind). Regenerable. |
| `schemas/manifest.json` | Register order (reference-data before master-data), deduplicated. |
| `register_schemas.sh` | Posts the schemas to the Schema Service, staged and stop-on-error. |

## Sources the generator reads

These live in the **parent workspace (`~/dv`), outside this repo** — the generator
resolves them relative to two levels up, or `OFP_REPO_ROOT` if set. The generated
`schemas/` are committed and self-contained, so deploying from a fresh clone does not
require these sources; only regenerating does.

- `dVE/backend/src/adapters/ofp-schema-mapping.json` — the curated, deployed OFP
  entity set with canonical kind IDs and versions (e.g.
  `ofp:wks:master-data--EmissionFactor:4.0.0`).
- `openfootprint/standard/models/*.hck.json` — the authoritative Hackolade data model
  (property names, types, descriptions, required flags). The "Common Entities" model
  carries the full definitions; other models repeat entity names as stubs, so the
  generator keeps the richest collection per name.

## Kind convention

`authority:source:entityType:version` → `ofp:wks:<group>--<Entity>:<M.m.p>`
- `authority = ofp` (custom; confirmed accepted under `INTERNAL` scope)
- `source = wks`
- `<group>` = `master-data` or `reference-data`

## Schema shape

Self-contained OSDU record schema: system properties (`id`, `kind`, `version`, `acl`,
`legal`, `tags`, `create/modify*`) inlined + a `data` object holding the OFP entity
properties. `required: [kind, acl, legal, data]`. No external `$ref` (avoids
resolution failures on first deploy; can be refactored to `$ref` the `osdu` abstracts
later).

Data property keys default to **snake_case** (`KEY_STYLE=snake`) to match the OFP
database and ELM models. Set `KEY_STYLE=pascal` for OSDU-house-style names.

## Deploy

Run from the repo root (`OSDU/`):

```bash
# 1) (re)generate — needs the parent-workspace sources; override with OFP_REPO_ROOT
python3 ofp-schema-deploy/generate_schemas.py

# 2) register (needs a bearer token with service.schema-service.editors)
export OSDU_TOKEN_FILE=/path/to/token          # file containing the bearer token
export OSDU_BASE=https://104.43.134.183.nip.io # target platform
export OSDU_PARTITION=osdu

bash ofp-schema-deploy/register_schemas.sh test     # one entity, confirm end-to-end
bash ofp-schema-deploy/register_schemas.sh refdata  # 20 reference-data kinds
bash ofp-schema-deploy/register_schemas.sh all      # everything, dependencies first
```

## ⚠️ Irreversibility

OSDU schemas **cannot be deleted**. These register as `status: DEVELOPMENT`, which stays
mutable via `PUT`. Only promote a kind to `PUBLISHED` after a test record validates —
a PUBLISHED schema is frozen permanently and can only be superseded by a higher version.

## Prerequisites on the platform

- A bearer token whose identity is in `service.schema-service.editors`.
- `data-partition-id` header (default `osdu`).
- For loading records afterward: a legal tag (e.g. `osdu-demo-legaltag`) and ACL groups
  (`data.default.owners` / `data.default.viewers`).
