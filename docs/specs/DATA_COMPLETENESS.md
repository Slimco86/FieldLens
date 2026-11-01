# Specification: Data completeness before agent aggregation

> **Spec type:** Product/feature. **Backlog:** TASK-046 (units/datum defaults and deterministic identity),
> TASK-047 (time-series storage and window API); equipment policy for TASK-036/TASK-041.
> **Date:** 2026-10-31. **Decision owner:** project owner.
> **Status:** Approved by the owner on 2026-10-31 (decisions in section 6). TASK-046 (DC-1..DC-6) integrated in 0.18.0; TASK-047 (DC-7..DC-11) pending.
> **Zero-Question Score:** 0 blocking.

## How to Read This Spec

Executors: ingestion (TASK-046), backend (TASK-047). QA: DC-1..DC-11. Requirements trace to
[INGESTION](INGESTION.md), [DATA_QUALITY](DATA_QUALITY.md) (demo policy amendment),
[PERFORATION_HISTORY](PERFORATION_HISTORY.md) and [LINKED_CHARTS](LINKED_CHARTS.md).

## 1. Outcome

Before any agent proposes entities, the deterministic layer is complete for the structured sources: depth
values are usable with documented defaults, wells and wellbores exist as resolved identities with evidence,
and log and production data are stored as queryable series, not only as summaries. Outcome score 3.

## 2. Scope

### IN scope
- Default units/reference for depths without a documented unit (meters, measured depth) as warnings, not blockers.
- Deterministic well and wellbore identity (names normalized by fixed rules, sidetracks distinct, parent links).
- Full-resolution storage of LAS curve samples and production series with a windowed, downsampled read API.

### OUT of scope
- Agent-proposed entities, equipment entities and the published model revision (FL-016/TASK-026).
- OCR (dropped by the owner); equipment extraction (TASK-036/TASK-041).
- Dedicated user correction UI (not planned for the demo).

## 3. Requirements

| ID | Type | Requirement | Score | Status | Check |
|---|---|---|---|---|---|
| DC-1 | Behavioral | On the real perforation and formation-pick tables each depth attribute carries `normalized_unit` `m`, is not `unsupported`, and the run has one `MISSING_UNIT` warning per file that states the assumption (meters, MD, reference unspecified) with the affected count. | 3 | [Validated: owner default] | `test_depth_defaults` |
| DC-2 | Edge | A unit stated by the source (LAS, WITSML uom, Compass table) always overrides the default; feet convert exactly (0.3048); the original text/unit stay stored. | 3 | [Validated] | `test_stated_unit_wins` |
| DC-3 | Negative | A defaulted depth beyond the wellbore's known trajectory/log MD range by more than 5% emits `SUSPICIOUS_VALUE` and never changes the value; with no range available no check is claimed. | 3 | [Assumed: verify 5%] | `test_depth_range_warning` |
| DC-4 | Behavioral | Rows in `well`/`wellbore` are created from the extracted record subjects by one deterministic rule shared with the retrieval identifier code: names normalized (`NO 15/9-F-11 B` -> well 15/9-F-11, wellbore B), sidetracks distinct with a parent link, field-level labels such as `Volve F` are not wells; each row lists supporting document/record counts; re-running is idempotent. | 3 | [Validated] | `test_identity_resolution` |
| DC-5 | Negative | F-12, F-12 A, F-1 and F-11 never merge; two spellings merge only when unambiguous; an ambiguous label stays unresolved with an `IDENTITY_MISMATCH` finding and no row; identities never cross projects. | 3 | [Validated] | `test_identity_scope` |
| DC-6 | Behavioral | A project-scoped read API lists resolved wells/wellbores with record counts per kind and links each record to its wellbore (service and endpoint); unresolved records are reported. | 3 | [Assumed: shape] | `test_identity_api` |
| DC-7 | Behavioral | LAS curve samples and production series are stored at full resolution: for every real LAS file the stored sample count equals `data_rows`, and first/last/min/max/null counts equal the per-curve summary; null sentinels become nulls, never zero. | 3 | [Validated] | `test_series_fidelity` |
| DC-8 | Non-behavioral | The window API returns at most `max_points` points using deterministic min/max-preserving downsampling; the full-resolution mode is capped; a 10,000-point window answers in under 300 ms (p95, measured on this host, reported). | 3 | [Assumed: verify] | `test_series_window` |
| DC-9 | Behavioral | Production series per wellbore and measure keep day precision and stated units, never zero-fill missing days, and carry the evidence locator of their source records; totals are not invented. | 3 | [Validated] | `test_production_series` |
| DC-10 | Edge | Series rows are written atomically with the run (an interrupted run leaves none visible), are superseded with the run, and cascade-delete with their document (hook for source removal). | 3 | [Validated] | `test_series_lifecycle` |
| DC-11 | Non-behavioral | Extraction of the real production workbook and LAS files with series storage stays within bounded memory and adds no more than 60 s wall time on this host; measured values are reported. | 3 | [Assumed: verify] | opt-in `-m local_data` test |

## 4. Failure behavior

Unknown stays unknown: a value without depth data is not given a default. A defaulted value is always flagged
and traceable to the rule that applied it. An identity that cannot be resolved produces a finding, not a guess.
A failed series write fails the run (never a partially visible series).

## 5. Implementation guidance

TASK-046 (ingestion): depth default and range-check rules in the perforation, pick and survey profiles (profile
version bump so existing runs are re-derived), the shared identity normalizer used by retrieval, `well`/`wellbore`
population as a post-extraction step, read API and DTOs. TASK-047 (backend): migration with typed series tables
(one row per curve with depth/value arrays plus metadata, and a production series representation), a series builder
as part of run finalization, the window endpoints and a typed service for later chart and agent tools
(`get_series_window`). Migrations are serialized: the second task to merge renumbers its migration onto the new
head. Shared-contract edits are additive and serialized by the orchestrator.

## 6. Owner decisions (2026-10-31)

- Depths without a unit default to meters (MD); this is a warning, not a blocker.
- Entity identity is deterministic where sources are structured; agents are only for ambiguity and unstructured content.
- OCR is dropped. Completion-equipment extraction (TASK-036/TASK-041) reads page images directly with a superficial,
  visual-level goal (type, material, sizes, structure); values are labelled model-read and unverified, never used in
  calculations; speed and performance take priority over detail; missed details are acceptable.

## 7. Implementation notes (TASK-046, 0.18.0)

- Defaults: perforation/pick depths get `normalized_unit` `m` and the reference text `assumed MD/TVD/TVDSS (default)`; one
  `MISSING_UNIT` warning per file; `MISSING_REFERENCE` is non-blocking when defaults apply (blocking only when no usable
  depth exists); easting/northing without a CRS is a separate `*_crs_missing` finding that blocks only placement; TWT,
  dip, azimuth, blanks and ER/FP-flagged picks are not defaulted.
- DC-3: the range is the maximum MD across survey and log records of the same wellbore; only the deep end is checked
  (105%), TVD is not checked, and a wellbore without its own range (for example a pilot or sidetrack with no survey) is
  never checked.
- Identity: parent links are naming-based (`parent_basis` `name_suffix`), not a verified drilling relationship;
  production-workbook `H`/`AH` suffixes alias to the observed base wellbore (owner demo policy), other suffixes stay
  distinct; unqualified labels with no qualified source stay unresolved.
