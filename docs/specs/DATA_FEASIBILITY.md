# Specification: Select an evidence-compatible historical demo dataset

> **Spec type:** Research/discovery.
> **Load-bearing frameworks:** F1 outcome, F6 ambiguity, F2 acceptance.
> **Supporting:** F3 scope, F4 executor context, F5 access/data failures.
> **Date:** 2026-10-27. **Author:** main agent. **Decision owner:** project owner.
> **Status:** DRAFT; acquisition choices and limits await owner confirmation.
> **Backlog ID:** FL-002. **Delivery state:** blocked on engineering sample access.
> **Approved revision / integration:** not yet approved or integrated.
> **Zero-Question Score:** 0 unowned questions; three owned decisions still block approval.

## How to Read This Spec

Owner: outcome, scope, open tensions and ambiguity audit. Researcher/ingestion
executor: scope, criteria, contracts and failures. QA: criteria and adversarial
checks. This covers project AC-1 and inputs to AC-3 through AC-9, not application
implementation or a claim that those criteria have passed.

## Notation Key

`[Validated]` means owner/source-confirmed, not implemented. `[Assumed: verify]`
requires owner approval. `[Unknown: TBD]` is an owned blocker. H/M/L are
high/medium/low confidence judgments, not measurements. Criterion score 3 means
an explicit observable pass/fail check. Owned blockers do not make this executable.

## 1. Outcome Statement

After the audit, the owner can accept or reject a specific, hashed 3-5-wellbore
sample for the required historical demo using a complete evidence-coverage matrix
whose missing/conflicting entries are explicit.

Verification: inspect the manifest and coverage matrix against DF-1 through DF-9.
Outcome score: 3. A negative feasibility finding is a valid research result, but
does not close G1 or mark FL-002 done.

## 2. Scope

### IN Scope

- `[Validated: owner, 2026-10-27]` Inspect real samples before detailed architecture.
- `[Assumed: verify, M]` Start with F-12/shared files, then F-14/F-5 from the
  [candidate list](../data/VOLVE_PILOT_CANDIDATES.csv); keep F-1 C and
  exact F-11-family wellbores as reserves, not automatic additions.
  The list now has 33 paths, including a separately deferred large EDM export.
- `[Validated: project scope]` Cover surveys, installed equipment, historical
  perforations/state, production, depth logs, seabed and formations; preserve
  source scope, references, effective dates and extraction completeness.
- `[Assumed: verify, M]` Initial acquisition ceiling: 25 MiB per engineering file,
  100 MiB total, one download/parser at a time; stop for approval before exceeding
  either ceiling. The already-inspected metadata catalog is not an engineering file.

### OUT of Scope

Application ingestion/DB/API/scene code (FL-004 onward), full seismic/PI/RMS/OW
acquisition, reservoir simulation, arbitrary-format support, trained extraction
models, automatic account creation, paid compute, paid Meta evaluation and
publishing originals. Those actions are not necessary to document this audit.
Meta protocol validation remains FL-003; default audit work spends zero API credit.

### Scope Dependencies

Official listing access or an owner-supplied authorized copy is required for
content inspection. Agent host activation is required before delegating execution,
not for main-agent planning. No running database or Docker is needed for discovery.

### Open Scope Tensions

Required dated history may be absent from the first reports. Inspect referenced
operations before choosing an expansion; missing history must not become a
synthetic "real" demo. Owner decides cohort/budget changes before more acquisition.

## 3. Acceptance Criteria

| ID | Type | Pass condition / check | Score | Annotation |
|---|---|---|---|---|
| DF-1 | Dependency | Each acquired file has acquisition URL or owner-provided origin, retrieval date, exact relative path, byte count, SHA-256, license/attribution status and immutable local original; mirror provenance is distinguished from verified official bytes. | 3 | [Validated: provenance rules] |
| DF-2 | Behavioral | For every candidate wellbore, the matrix contains survey, equipment, perforation/history, production and depth-log rows; shared seabed and formation rows also exist. Each row is `supported`, `partial`, `missing` or `conflicting`, with source locators or an explicit gap. | 3 | [Validated: all required evidence families] |
| DF-3 | Behavioral | Every proposed supported family has inspected headers plus at least three representative records, or all records if fewer, with original values/units and exact page/table/cell/XML/LAS-line locators. Coverage totals and uninspected pages/records are recorded separately. | 3 | [Assumed: verify sampling threshold] |
| DF-4 | Negative | No family is `supported` solely from filenames, catalog tags, simulator schedules, neighboring-well metadata or an LLM assertion. Planned/as-built and well/wellbore records remain distinct. | 3 | [Validated: engineering rules] |
| DF-5 | Edge case | The audit explicitly tests the F-12-folder/F-11-B-filename mismatch, a missing reference and an undated perforation interval; affected claims are unresolved/blocked, never reassigned, zero-filled or given invented dates. Synthetic negative fixtures are labeled synthetic. | 3 | [Validated: observed mismatch and required negative cases] |
| DF-6 | Behavioral | For each proposed historical demo window, the matrix separates physical MD coverage, open/isolated access and evidenced wellbore/interval flow; effective/report/import dates and precision are explicit. Missing initial history or event ordering is not a verified zero or an invented sequence. | 3 | [Validated: PH-1 through PH-9 semantics] |
| DF-7 | Behavioral | A `ready` recommendation includes owner-approved file/format/window selection, coordinate/depth transforms and source-precision-based tolerances, and independent checks of at least one real trajectory and one dated interval-state/length sequence. Any missing required family yields `blocked`, not `ready`. | 3 | [Validated: G1 and project AC-1/3] |
| DF-8 | Non-behavioral | Actual downloaded bytes, parser/version, per-file elapsed time, peak process RSS, page/record coverage and failures are recorded; approved acquisition limits are not exceeded, and paid API calls equal zero. | 3 | [Assumed: verify byte limits; validated zero-paid-call default] |
| DF-9 | Dependency / negative | Before recommending equipment feasibility, one selected pilot configuration has source-linked installed casing/tubing sizes and MD placement, compatible survey/depth references, and at least one located discrete completion device with evidenced type, axial length and OD. Catalog dimensions require a verified model/variant match; drilling-only assemblies, design-only records and generic placeholders cannot satisfy this criterion. | 3 | [Assumed: verify exact threshold at G1; owner identifies technical equipment evidence as essential] |

Complexity: medium, nine criteria. Completion requires all criteria for the
accepted manifest, owner approval, and verified documentation integration.
The static candidate list is not DF-1 evidence of acquired files.

## 4. Context and Decisions

Executor: main agent for this bounded discovery; `fieldlens-ingestion` for a later
approved parsing audit, with geospatial questions returned to the orchestrator.
No worker has been assigned. Before delegation record base commit, branch,
absolute worktree, owned files, actual profile/model/tools, permitted local input
directory and memory/time limits. No nested delegation or shared DB is needed.

`MD` is distance along the bore; `TVD` is vertical depth from a declared datum.
`TWT` is seismic two-way travel time, not depth. A candidate path is a discovery
lead; an accepted manifest contains inspected bytes and evidence. A formation
surface is interpreted context, not necessarily a reservoir boundary/volume.

Decisions and dependencies:

| Item | Status / rationale |
|---|---|
| Data-first sequencing | [Validated: owner] Avoid final contracts based on invented source schemas |
| Official access | [Validated: authenticated listing installed]; [Unknown: TBD by owner/provider before pilot acquisition] Catalog exposes only `information_schema`; advertised volume returns missing-schema 404. Do not reinstall, alter permissions or provision services without approval |
| Licensing | [Validated: published license inspected] Conditional use/sharing permitted; per-file provenance, third-party rights and publication review still required |
| Cohort and numerical fixtures | [Unknown: TBD by owner + orchestrator before G1 closure] Candidate filenames do not establish compatibility |
| Host | [Validated: observed] Python 3.12 available, 7.6 GiB WSL RAM; no application environment established |
| Meta | [Validated: owner] Key ready and public-data processing permitted; no bounded live test approved here |

Audit output contract: a versioned manifest with file ID/hash/path/origin/license;
candidate and reconciled wellbore IDs; source configuration/revision; original
units/CRS/depth/north reference; effective/report times and precision; parser and
locator method; extraction coverage; expected records; contradictions; selected
demo window; numerical tolerance and derivation evidence. Store unknown values
as explicit unknowns, not default measurements.

Coverage rows key by `(file_id, wellbore_id or shared_layer_id, evidence_family,
configuration_revision, historical_window)`. Record both source and derived
claims; a parser rerun must not overwrite original evidence. This is an audit
record shape, not a finalized database schema, migration or application API.

Owner approves access, cohort and publication. Orchestrator owns audit integration
and design decisions; QA independently checks fixtures when assigned. Deadline
remains November 4, 21:00 EST; no cloud expenditure is implied.

## 5. Failure Conditions

| Type | Deviation signal | Action |
|---|---|---|
| Authorization | Sign-in/terms acceptance or paid service required | Stop acquisition; owner completes access or supplies an authorized copy |
| Data identity | Header disagrees with directory, or base and sidetrack IDs collapse | Quarantine attribution; retain both candidates and resolve from source evidence |
| Data semantics | Perforations have no effective dates or simulator-only history | Mark historical coverage partial/missing; inspect explicitly selected operation reports; G1 stays blocked |
| Spatial model | Missing CRS/datum/north reference, or depth layer is actually TWT | Block affected alignment; no assumed transform or flat-plane replacement |
| Resources | Approved byte limit exceeded, parser failure or incomplete text extraction | Stop affected file, record partial/failure, retain originals; request revised limits/parser choice |

Worst misinterpretation: a matrix of filenames could appear complete while
containing no engineering evidence. DF-3/4/7 require content locators and real
independent fixtures, preventing that result from being called ready.

## 6. Ambiguity Audit

| Question | Owner / deadline | Resolution |
|---|---|---|
| Which access route and local sample location? | Owner/provider, before pilot acquisition resumes | [Unknown: TBD]; sign-in succeeded, but published data volume is not visible; an authorized local copy remains an alternative |
| Approve cohort, sampling/byte limits and DF-9 threshold? | Owner, before pilot acquisition/G1 closure | [Unknown: TBD]; not inferred from lack of response |
| Which common historical window, reference mapping and tolerances? | Owner + orchestrator, after inspection and before G1 closure | [Unknown: TBD]; derive from source precision and coverage |

Zero-Question Score: 0 unowned; three owned decisions remain. Status stays draft.

## 7. Implementation Guidance

Use the [access handoff and findings](../VOLVE_DATA_DISCOVERY.md). After approval,
inspect file signatures and archive/XML boundaries before parsing; no macros,
external XML entities, remote conversions or document instructions are executed.
Preserve originals. Prefer native structured readers, then evaluate PDF text/table
quality before choosing OCR. Reviewed temporary analysis is not application code.

Checkpoints: (1) access and hashes; (2) first-well/shared-family coverage;
(3) remaining cohort and dated events; (4) independent fixtures and owner decision.
Record actual commands/results; no application test commands exist yet.

Handoff: documentation-only compatibility, proposed patch release; no code/schema
migration. File ownership is this spec, the candidate list and discovery report;
the main agent alone updates backlog/release metadata. No feature commit or
completed data audit is claimed in this draft.

Follow-up evidence: [three public mirrored equipment XML probes](../EQUIPMENT_DATA_FEASIBILITY.md)
were inspected under the owner's equipment-research request (7,776 bytes total).
They are outside the proposed pilot cohort; structural field/hash checks do not
pass DF-7/9, establish effective installation dates, or approve the full sample.

## Open Tensions

The owner chose real-data inspection first; the inspected probes now inform the
[architecture](../ARCHITECTURE.md) without pretending the pilot audit passed.
The completed [execution plan](../../plan/architecture-fieldlens-1.md) permits
approved source-independent foundation/analytic fixtures while pilot access is
resolved. Source mappings and real acceptance remain gated here; no required layer
is demoted and no draft spec grants implementation approval.

## Assumption Registry

| Assumption | Confidence / evidence | Invalidation signal |
|---|---|---|
| Metadata paths still match the official release | M, [Assumed: verify]; community index only | Listing path/bytes differ or file absent |
| The proposed cohort has compatible dated evidence | M, [Assumed: verify]; filenames and official identity clues | Missing operations, incompatible configurations or no common window |
| The initial limits cover a useful sample | M, [Assumed: verify]; original sizes unknown | Required file exceeds limit or selected subset exceeds total |

## Adversarial Self-Critique

1. **Report titles can hide the wrong bore.** Misattribution would create a
   convincing but false completion. Watch header/identifier conflicts.
2. **Sparse reports can look like complete history.** Earliest/latest filename
   dates do not establish continuity. Watch unsupported initial state and gaps.
3. **Readable PDF text can lose table associations.** Correct numbers linked to
   wrong units/rows corrupt geometry. Watch failed cell/page fixture comparisons.

## Revision Triggers

- Official paths/license differ: revise scope, acquisition list and DF-1.
- Candidate dates/identities cannot support the demo: revise cohort/window and DF-6/7.
- Required files exceed limits or need OCR: revise resource bounds and DF-8 before execution.
