# Claim #3 evidence bundle — Methane MRV (ISO 25624-1) + OFP data domains

Everything the claim #3 proof produced on the cimpl-stack "dev" OSDU, exported so the proof
outlives access to that platform. Nothing here needs a network to read, and the whole model
can be re-registered and re-loaded onto any other OSDU.

## Layout

| Path | What it is |
|---|---|
| `claim3/_manifest.json` | Index of everything: counts per kind, id → file map, integrity report, platform identity, and the records on the platform that are *not* part of this proof (`foreign`). |
| `claim3/records/` | Full body of every record belonging to the proof (342), head version. |
| `claim3/versions/` | Every immutable version body of every versioned record (240 records, 515 version bodies) — the Monitoring Plan trail, the attestation lifecycle, the reconciliations. |
| `schemas-live/` | All 158 `ofp` schemas **as registered on the platform**, wrapped as valid Schema Service POST bodies (`schemaInfo` + `schema`), plus `_index.json`. |
| `ofp/` | The five-domain OFP graph as exported per-domain by `ofp-domains/ofp_export.py`, plus the plan version summary. Superseded by `claim3/` but kept as the per-step artifact. |
| `*.json` (top level) | The per-step methane exports from `day4_export.py` (inventory, quantifications, reconciliations, OGMP reports, attestation, alert, timelines). |
| `_summary.json` | The proof's own summary: record ids, metrics, gate results, restatement figures, and the `ofp` section (domain counts, traversal, rules, kind map). |

## Verify it offline

```bash
python3 verify_export.py          # no network; 23 checks
```

Re-derives the headline numbers from the exported bodies rather than trusting the report:
Σ of the five source `EmissionStatement`s equals the bottom-up total (156,300 kg) and each one
re-computes as `E = EF × N × t`; the top-down statement annualizes 19.5 kg/h; divergence is
8.5% and within the 20% limit; the three gate runs scored 100 / 83.3 / 100 with exactly one
failing constraint (`SiteLevelReconciliation`); the plan trail runs draft → underReview →
verified → suspended → restated; the attestation runs issued → suspended → reissued and is
bound to a plan hash; the final plan version's four OFP links all resolve inside the export.

## Restore onto another OSDU

```bash
OSDU_BASE=https://<gateway> OSDU_PARTITION=<partition> OSDU_TOKEN_FILE=<file> \
  python3 restore_claim3.py --dry-run     # then without --dry-run
```

Registers the 158 schemas in dependency order (reference-data → master-data →
work-product-component), then PUTs the 342 records in the same order. If the target partition
differs from `osdu`, record ids **and** the id references inside `data` are remapped
automatically, so the graph's foreign keys still resolve.

Prerequisites on the target: a legal tag matching `legal.legaltags` (default
`osdu-demo-legaltag`) and the ACL groups must exist. Override with `LEGALTAG`, `ACL_OWNERS`,
`ACL_VIEWERS`.

## Caveats

- **Version history cannot be replayed.** OSDU assigns version numbers; a restore recreates
  each record at its head state. The trail is preserved as evidence in `claim3/versions/`, and
  the offline verifier reads it from there.
- **`foreign` records are not exported.** 39 pre-existing demo records on the platform
  (Acme/Beta) are listed in the manifest but were not part of this proof.
- **Orphan kinds.** The platform carries 158 `ofp` kinds, of which 41 are superseded orphans
  from earlier registration passes (see `../../ofp-schema-deploy/ORPHANED_KINDS.md`). They are
  exported for completeness; do not write records to them. The live graph is on the correct
  kinds.
- The site, its numbers and the LEI are synthetic, built to exercise ISO 25624-1's own worked
  anomaly. They are not measured data.
