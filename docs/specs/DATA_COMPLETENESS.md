# Specification: Data completeness before agent aggregation

> **Spec type:** Product/feature. **Backlog:** TASK-046 (units/datum defaults and deterministic identity),
> TASK-047 (time-series storage and window API); equipment policy for TASK-036/TASK-041.
> **Date:** 2026-10-31. **Decision owner:** project owner.
> **Status:** Approved by the owner on 2026-10-31 (decisions in section 6); implementation not started.
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

## 7. Implementation notes: series storage (TASK-047, DC-7..DC-11)

- **Tables (migration `0008_series_storage`).** `series_axis` = one shared index per data block (a LAS
  `~A` section or one wellbore's production days; float64 `bytea`, production days are epoch days) plus the
  source line/row of every sample; `series_curve` = one float64 `bytea` value array per curve/measure with
  counts, first/last valid index, min/max, stated unit (`stated|missing|mixed`), NULL sentinel, SHA-256 of
  the stored bytes (the series revision) and evidence (anchor record ordinal, curve/data locators). NaN
  encodes a missing sample (parsers never emit NaN). Arrays are `STORAGE EXTERNAL`, so a window is a
  `substring`. Composite FKs scope everything to the project; rows cascade with the run, the document
  (`DELETE FROM series_axis WHERE project_id=.. AND document_id=..` is the source-removal hook) and the
  anchoring `extracted_record`.
- **Ingestion.** Profiles return samples in `ProfileOutput.series` (never in `extracted_record`); the runner
  writes them in the run-finalizing transaction (`series/builder.py`), after the fenced update, so an
  interrupted, killed, failed or fence-lost run leaves none. A new run of a document drops the series of its
  superseded runs; visibility also requires `superseded = false` and status `succeeded|partial`. LAS data
  lines are parsed once into float64 arrays (no per-token strings); a block above 30,000,000 cells is not
  stored and the run is `partial` with an explicit finding. LAS profile and production profile are v2.
- **Production.** One axis per wellbore label (never pooled), one curve per measure column of the daily
  sheet; days sorted stably by date (source row kept per sample, duplicates kept), absent days stay absent,
  blank/NULL cells are NaN, no unit is assumed (`missing`) except where the sheet states one.
- **API.** `GET /api/v1/projects/{id}/series` (filters `wellbore_label`, `kind`, `mnemonic`, `document_id`;
  `limit` 1..500 default 100, `offset`), `GET .../series/{series_id}`, `GET .../series/{series_id}/window`
  (`from`/`to` inclusive: numbers, or `YYYY-MM-DD` for date indexes; `max_points` 10..10,000 default 2,000;
  `resolution=downsampled|full`, full capped at 50,000 samples with a 422 above it). `no-store`, 404 across
  projects, 422 for malformed input. Downsampling `minmax-gap-v1` (see `series/downsample.py`) keeps each
  bucket's min and max, every null run's extent and the window endpoints, deterministically, and reports
  `gaps_omitted` when a fragmented window cannot represent every gap. `cache_key` = SHA-256 of series id,
  run id, series revision, window, `max_points`, resolution and algorithm.
- **Known limit.** Files the existing LAS profile cannot read as numeric rows (time-formatted TIME index,
  `WRAP YES`) yield no samples (`data_rows` = 0, explicit partial run); extending the profile is a parser
  decision outside this slice.
