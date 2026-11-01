# Specification: Agent-assisted extraction of ambiguous source content with deterministic validation

> **Spec type:** Product/feature + Agent task.
> **Load-bearing frameworks:** outcome, acceptance, scope, context. **Supporting:** failure conditions, ambiguity audit.
> **Date:** 2026-10-30. **Author:** orchestrator (draft). **Decision owner:** project owner.
> **Status:** Approved by the owner on 2026-10-30 (section 6 records the decisions); implementation not started.
> **Backlog ID:** FL-022 (TASK-035 approval, TASK-036 extraction, TASK-038 activity log, TASK-040 Reconstruction view). **Delivery state:** TASK-036 integrated 0.20.0; TASK-041 next.
> **Approved spec revision/date:** r1, 2026-10-30. **Integration version:** pending.
> **Zero-Question Score:** 0 blocking. Non-blocking: multimodal entitlement is verified by the TASK-005 live smoke, and TASK-036 uses the stub until then.

> **Owner amendment, October 31:** the priority extraction target is production/completion equipment
> (tubing, casings/liners in service, packers, pumps, bearings) from the completion documents; drilling-side
> assemblies are out of scope. TASK-042 (live feasibility spike) and TASK-041 (extraction) follow the TASK-005
> live smoke; their acceptance criteria are added after the spike. The harness contract (AX-1..11) is unchanged.

> **Owner amendment, October 31 (demo, second pass):** OCR is dropped. For scanned completion pages the model reads
> page images directly and proposes a superficial, visual-level equipment structure; values are labelled model-read
> and unverified, are never used in calculations, and the AX-2 quote-in-span check applies only where a text layer
> exists. Speed and performance take priority over detail; missed details are acceptable. See DATA_COMPLETENESS.

> **Owner amendment, October 31 (dispatch, TASK-036/TASK-041):** AX-12..AX-15 below add the page-image tool, the
> visual-level equipment candidate and the speed budget. New runtime dependencies approved by the orchestrator:
> `pypdfium2` (Apache-2.0/BSD-3) and `Pillow` (HPND) for page rendering; no other new dependency.

## How to Read This Spec

Owner: outcome, scope, acceptance policy and spend (section 6). Implementer: scope, contract and ACs.
QA: negative/adversarial ACs and the worst-misinterpretation test. Builds on [ingestion](INGESTION.md)
(deterministic profiles come first), [Meta integration](META_INTEGRATION.md) (provider adapter, budget, MI-1..5),
[reconstruction](ASSET_RECONSTRUCTION.md) (consumes the result), [data quality](DATA_QUALITY.md) (surfaces it).

## Notation Key

`[Validated]` = owner/source confirmed; `[Assumed: verify]` = proposed, owner approves in TASK-035.
AC score 3 = binary and outsider-testable.

## 1. Outcome Statement

After this increment, whenever answering a specific question about an entity, measurement, fact or record needs
broader document context or multimodal input than a deterministic profile provides (an ambiguous table, free-text
report paragraph, unlabeled units, unclear well/wellbore subject, or scanned/legacy-Word content), the application
harness can ask the model for typed candidate claims. The model may read the source through allowlisted read-only
content tools (spans, tables, page images by locator, project retrieval). Every candidate carries its exact source
locator, is checked by deterministic validators, and ends as `accepted`, `rejected` or `flagged` with a visible
reason. Each work unit leaves a project-scoped activity log (steps, tool calls, candidates, validator outcomes,
usage) that the Reconstruction tab displays. Model output never becomes an accepted fact because the model said so,
never overrides a deterministically parsed value, and never runs without budget.
Verification: AX-1 through AX-11 with the offline stub provider on fixtures; live behavior is a separate gate.
Outcome score: 3.

## 2. Scope

### IN Scope

- `[Validated: owner, October 30]` Extraction should be as deterministic as possible; model judgement is for the
  ambiguities that deterministic parsing cannot resolve.
- `[Validated: owner, October 30]` Question-driven use: the model is invoked for a specific question about an
  entity, measurement, fact or record when broader document context or multimodal input is needed.
- `[Validated: owner, October 30]` Ambiguity classes: (a) table column/header/unit interpretation; (b) free-text
  statements of events, dates, depths and equipment attributes; (c) subject identity (which well/wellbore a passage
  is about); (d) text/images produced by approved scanned-PDF and legacy-Word profiles (TASK-030 locators).
- `[Validated: owner, October 30]` Read-only content tools for the model: read a text span, read a table, fetch a
  page image by locator, and search the project (TASK-011 retrieval). Page images enable multimodal questions.
  Tools are allowlisted, project-scoped, argument-validated and return only source content with locators.
- `[Assumed: verify, H]` A persisted, project-scoped agent activity log per work unit: question, steps, tool calls
  with argument/result summaries, candidates and validator outcomes, usage and stop reason. No hidden reasoning is
  stored. Shown in the Reconstruction tab (TASK-040; persistence in TASK-038).
- `[Assumed: verify, H]` A typed candidate-claim schema (value, unit as written, subject candidate, effective-time
  text with precision, evidence locator(s), extraction method `model_proposal`, prompt/model/version ids) reusing the
  existing evidence/locator/quantity contracts; persisted candidate states and reasons.
- `[Assumed: verify, H]` Deterministic validators: locator exists and the quoted text matches the source span; value
  and unit parse; unit/dimension and range plausibility; subject is a known project identity candidate (otherwise
  stays a candidate); date precision preserved; no conflict with a parsed value (a conflict is `flagged`, never
  resolved by the model). Validators are code, never a second model call.
- Display of candidates/states/reasons in the evidence and issue views (shared shell, FL-021).
- Offline stub provider tests; usage/budget recording through the existing adapter.

### OUT of Scope

- Reconstruction (relationships, entity merging, publication): FL-016 consumes accepted/flagged candidates.
- Retrieval/chat (FL-011) and equipment catalog research (FL-007).
- Replacing native parsers; model code/SQL/shell execution; any tool beyond the read-only content allowlist;
  autonomous web access (web research stays with equipment research, FL-007).
- Manual fact editor or review-based acceptance of model facts (a reviewer UI is deferred; flagged items stay flagged).
- Live provider spend: not authorized by this spec (see section 6, question 5).
- Contributor mode and any non-Standard provider mode (project rule).

### Scope Dependencies

TASK-004 (offline provider adapter and budget reservations), TASK-009 (native profiles producing the
deterministic records and the ambiguity signal) and TASK-011 (retrieval for the search tool) are hard prerequisites;
TASK-030 supplies scanned/Word text for class (d). Missing profiles mean those documents stay `unsupported`,
not model-read. Multimodal entitlement is unverified until the TASK-005 live smoke runs the image-input check.

### Open Scope Tensions

1. **How much may the model decide?** Proposed resolution: a candidate is `accepted` only when every validator in
   section 4 passes and no parsed value disagrees; otherwise `flagged`. Owner: project owner (section 6, Q2).
2. **Cost vs coverage.** Proposed: per-document and per-project caps from the MI-5 work-unit limits; exhaustion
   records partial coverage, not silent truncation. Owner: owner (Q5).

## 3. Acceptance Criteria

| ID | Type | Given / when / then or measured threshold | Score | Annotation | Test |
|---|---|---|---|---|---|
| AX-1 | Behavioral | For each ambiguity-class fixture, a run with the stub provider persists typed candidates, each with a locator that resolves to the source span and the quoted text matching it, plus model/prompt/version ids and usage. | 3 | [Assumed: verify] | `test_candidates_persisted` |
| AX-2 | Negative | A candidate whose locator does not exist, whose quoted text is not in the cited span, whose unit does not parse or is dimensionally wrong for the attribute, or whose value is out of plausible range is rejected with a machine-readable reason; nothing from it appears in accepted claims. | 3 | [Assumed: verify] | `test_validators_reject` |
| AX-3 | Negative | A candidate that disagrees with a deterministically parsed value for the same attribute/subject/time is `flagged` as a conflict and the parsed value remains unchanged and authoritative. | 3 | [Validated: owner rule, deterministic first] | `test_no_override_of_parsed` |
| AX-4 | Negative | Prompt-injection text inside a source ("ignore previous instructions", fabricated tool calls) changes no state, scope or tool use; only the typed candidate schema is accepted from the model; malformed/oversized/refused output yields an explicit failed attempt, not a partial success. | 3 | [Validated] | `test_hostile_source_text`, `test_malformed_output` |
| AX-5 | Behavioral | Subject-identity candidates not supported by an existing identity candidate stay unresolved; a wrong-folder/cross-well fixture keeps the actual source subject; MD is never treated as TVD; no CRS, date order or installed state is invented. | 3 | [Validated: same rules as IN-6/RC-3] | `test_identity_and_reference_rules` |
| AX-6 | Edge case | Cancel, process kill, provider timeout/429/5xx and budget exhaustion leave interrupted attempts that a fenced retry completes without duplicate candidates; exhaustion records the partial coverage and stop reason; interrupted work never appears successful. | 3 | [Validated: INGESTION IN-4 / META MI-3..5 patterns] | `test_extraction_recovery`, `test_budget_stop` |
| AX-7 | Behavioral | The UI shows each candidate's state, reason, validator outcome and a link to the exact source location; accepted, flagged and rejected are distinguishable without color alone; unresolved candidates are never rendered as accepted facts (draft-vs-accepted separation). | 3 | [Assumed: verify] | Vitest + Playwright on a fixture project |
| AX-8 | Non-behavioral | Default tests make zero external requests and spend no credits; re-running unchanged inputs with unchanged model/prompt versions reuses the cached result (no new provider call), and changing the source or prompt version invalidates it. | 3 | [Validated: AC-10; MI-2] | `test_no_network`, `test_extraction_cache_keys` |
| AX-9 | Negative | A stub-provider run that requests a tool outside the allowlist, a locator or document outside the project, an unbounded range, or more than the per-unit tool-call limit is refused with a recorded reason and no data from outside scope is returned; allowed tools return only content with locators, and a page-image request returns the image for that locator only. | 3 | [Validated: owner allows tools/multimodal; project tool rules] | `test_tool_allowlist_and_scope`, `test_tool_call_bound` |
| AX-10 | Behavioral | Each work unit persists an activity log (question, ordered steps, tool calls with summaries, candidates, validator outcomes, usage, stop reason) scoped to the project and source revision; the Reconstruction tab lists it with state and links to source locations, shows no hidden reasoning text, and interrupted/failed units are visibly not successful. | 3 | [Validated: owner Reconstruction-tab model] | `test_activity_log_persisted`; Vitest + Playwright (TASK-040) |
| AX-11 | Negative | Owner decision October 30: coordinates and trajectory values may be model-extracted only as a labeled backup. When no deterministic source for the subject exists, a candidate that passes every validator (quoted span matches; explicit units, horizontal CRS, vertical datum, depth reference and azimuth reference stated in the source or its cited context; plausible and monotonic MD/stations) is accepted with evidence class `model_proposal` and a visible "agent-extracted fallback" marker that propagates to every derived geometry, distance and tool result. A missing CRS/datum/reference is never assumed (the value stays flagged and the affected output blocked). Once a deterministic source exists, it wins and the fallback is superseded; a disagreement is flagged, never resolved by the model. | 3 | [Validated: owner; guardrails Assumed: verify] | `test_coordinate_fallback_labeled`, `test_fallback_requires_explicit_reference`, `test_deterministic_supersedes_fallback` |
| AX-12 | Behavioral | The page-image tool renders a project document page (1-based, bounds-checked, project-scoped) with pypdfium2 to an upright RGB image whose longest side is about 1600 px (configurable, hard cap 2,400 px); a page whose text or table orientation is rotated is corrected before sending (rotation flag, then a bounded deterministic orientation check); the image is cached by (blob hash, page, scale, rotation) and re-requests reuse it; the result carries the locator, never a filesystem path. | 3 | [Validated: TASK-042 findings] | `test_page_image_tool`, `test_page_image_cache`, `test_page_orientation` |
| AX-13 | Negative | A candidate produced from a page image without a text layer (`method = model_read`) is stored with evidence class `model_proposal`, `validation_state = unverified`, a visible "model-read, unverified" label and a page-level locator (document, page, optional region); the AX-2 quote-in-span check is skipped only for such image-only evidence, never for text-layer evidence; such values are never accepted as engineering facts, never feed a calculation (the calculation entry points reject them by marker) and never override a parsed value. | 3 | [Validated: owner, October 31] | `test_model_read_marked`, `test_model_read_not_in_calculations` |
| AX-14 | Non-behavioral | Speed budget: page triage (printed table of contents and keyword scoring over the text layer, no model call) selects at most N candidate pages per document (default 12, configurable); pages are read at effort `low` with bounded concurrency (default 3, configurable); the run records per-page latency, tokens and cost; a 12-page document completes in under 5 minutes wall time on this host in the stub-latency model and the live measurement is reported separately when run. | 3 | [Assumed: verify measured values] | `test_page_triage`, `test_concurrency_bound`, `test_run_timing_recorded` |
| AX-15 | Behavioral | Startup recovery and budget wiring: process start calls `recover_interrupted` for stale units, every provider reservation links the activity-log `cost_usd` to its BudgetLedger reservation, `step_key` is derived from (unit, tool/step name, canonical argument hash), and a cancelled unit stops further provider calls. | 3 | [Validated: TASK-038 QA deferrals] | `test_startup_recovery`, `test_step_key_scheme`, `test_cost_reservation_link` |

Definition of done: all ACs pass with recorded commands/results (stub provider, not live); independent QA; integration per
[workflow](../DEVELOPMENT_WORKFLOW.md). Live quality is measured later (section 6, Q5) and must not be claimed from stubs.

## 4. Context and Decisions

- Executor profile: `fieldlens-ingestion`, coordinating with `fieldlens-rag` for the harness/adapter interface; the
  worker must not delegate. Skills: `fieldlens-document-ingestion`.
- Decisions already made: native structured parsers first, then model judgement for ambiguity; the harness owns runs, validation,
  cancellation, recovery and budget; model tools never publish or bypass validation; documents are untrusted data.
- Pipeline: deterministic profile output with an ambiguity marker -> extraction work unit (bounded context from the cited
  spans only) -> provider adapter (stub offline) -> schema validation -> deterministic validators -> persisted candidate
  state -> issue/evidence views -> consumed by reconstruction (FL-016).
- Bounds: each work unit obeys MI-5 (<= 4 attempts, <= 6 tool calls, <= 90 s, <= 4,096 output tokens/attempt, <= USD 0.50
  reserved); project-level caps follow the approved budget policy. The 6-tool-call limit may prove tight for
  tool-using extraction; it stays the default and is tunable only by amending MI-5 with measured evidence. Tools are
  the read-only allowlist in section 2; the output is a typed object, not code.
- Disclosure `[Validated: owner, October 30]`: all documents are open source and shareable with third parties without
  restriction, so content, page images and tool results may go to the entitled provider. This authorization covers
  the Volve demo documents; any other source needs its own confirmation. Standard mode only; never Contributor mode.
- Contracts: candidate state (`candidate|accepted|rejected|flagged`), reason codes, validator results and
  `extraction_method = model_proposal` must be representable with existing `EvidenceClass`/`ValidationState`/`Locator`
  contracts. If a new enum value or table is needed, that is a shared-contract change with a single writer, registry
  entry, regenerated client and `check:contracts` (open item for TASK-035). Persistence via a migration; PostgreSQL tests.
- Historical semantics: effective time, report time and dataset revision stay separate; date precision is preserved as
  written; no same-day ordering is invented; the as-of context is part of every cache key.
- Delegation: one writer/branch; files `backend/fieldlens/ingestion/` (extraction), `backend/fieldlens/evidence/`
  (candidate states/issues), tests, migration;   frontend candidate display only through existing evidence components (TASK-034 restyles them later).
  Isolated database/ports per the dev-tooling lanes; budget reservation per MI-3; no live calls.
- Model routing: Sonnet 5.5 / medium `fieldlens-ingestion`; verify host resolution at dispatch (TASK-001 policy).
- Agent/UI effects: the extraction tools are read-only and mutate nothing; the UI shows validated IDs, states and the
  activity log only. These tools are separate from the exploration/chat tool set (FL-011).

## 5. Failure Conditions

1. **Plausible but wrong value accepted.** A fluent model output passes schema checks and is treated as fact. Prevent:
   acceptance requires the deterministic validators (AX-2/3/5); LLM confidence is never an input to acceptance.
2. **Silent override or fabrication.** The model "fixes" a parsed value, fills a missing unit/CRS/date or links an
   unverified subject. Prevent: AX-3/5; unknown stays unknown; affected outputs are blocked, unrelated records are not.
3. **Hostile or malformed source/output.** Injection, truncation, refusal or provider failure. Prevent: AX-4/6; failed
   attempts are persisted as failed, never as partial success.
4. **Runaway cost or repeated work.** Prevent: MI-5 limits, reservations (MI-3) and cache keys (AX-8).

Failures return to the implementer; QA re-verifies; the owner decides scope/budget questions. Worst misinterpretation
test: a stub that echoes a fixed candidate passes AX-1 but not AX-2/3/4/5, which use adversarial fixtures that a
pass-through implementation cannot satisfy.

## 6. Ambiguity Audit and Owner Decisions (TASK-035)

| # | Question | Owner decision `[Validated: owner, 2026-10-30]` |
|---|---|---|
| 1 | Ambiguity classes / when the model is used | Yes: question-driven, whenever a specific question about an entity, measurement, fact or record needs broader document context or multimodal input. Classes (a) tables/units and (b) free text both fit; (c) and (d) as in section 2. |
| 2 | Acceptance policy | Yes: accepted only if all validators pass and no parsed value conflicts; otherwise flagged; no reviewer-accept path. |
| 3 | Fields never model-extracted | Revised October 30: coordinates/trajectories come from deterministic parsers first. If no reliable deterministic source exists, a model-extracted value may be used as a labeled backup (AX-11): explicit reference metadata required, never assumed, visible "agent-extracted fallback" marker on all derived outputs, superseded by any later deterministic source. Values without a quotable source span are never accepted. |
| 4 | Contract change | Yes: one shared-contract change with a single writer (registry, regenerated client, `check:contracts`). |
| 5 | Live spend | Yes: none in TASK-036; later live measurement falls under the USD 150 budget and the TASK-020/028 allowances, authorized separately. |
| 6 | Disclosure | All documents are open source and shareable with third parties; the model may receive content or use the provided read-only tools. Recorded in section 4 (scope: Volve demo documents). |

Follow-on work from these decisions: TASK-038 (activity log, backend), TASK-040 (Reconstruction tab view) and a multimodal image-input
check in the TASK-005 live smoke (within its USD 1 allowance).

## 7. Implementation Guidance

Smallest approach: (1) define the candidate schema/states/reason codes and a migration; (2) the extraction work unit
and cache keys over the TASK-004 adapter with a fixture-driven stub provider; (3) the validators (locator/quote match,
unit/dimension, range, identity, conflict-with-parsed); (4) the read-only tool allowlist and page-image access, with
scope checks; (5) recovery/budget behavior; (6) the evidence/issue view. TASK-038 adds the activity log (backend: `backend/fieldlens/activity/`, migration 0006, read API
`/api/v1/projects/{project_id}/agent-units`; tests `backend/tests/activity`, named `*_ax10`) and TASK-040 its view. The step_key convention belongs to the TASK-036 harness; replaying a key returns the stored
step without comparing content, so a reused key with different content is ignored.
Start with one ambiguity class end to end (table/unit interpretation on a TASK-009 fixture), then add classes in order.
Do not claim proposed commands exist; record actual test commands and results at handoff.

### Implementation notes (TASK-036, stub provider only)

- **Code.** `backend/fieldlens/candidates/`: `harness.py` (unit and document run), `tools.py` (read_span, read_table,
  search_project, get_page_image), `pages.py` (pypdfium2 render, cache, orientation), `triage.py`, `validators.py`,
  `schema.py` (closed wire schema), `repository.py`/`routes.py` (read API `GET /projects/{id}/extraction-candidates`
  and `/documents/{id}/extraction-candidates`). Migration `0010_extraction_candidates`: `extraction_candidate`
  (typed JSONB `attributes` with a `kind` discriminator; TASK-041 adds a variant, no migration) and
  `agent_work_unit.reservation_id`. DB CHECKs make AX-13 structural (a `model_read` row is never `accepted`).
- **Contracts.** `EvidenceClass.model_proposal`, `ValidationState.unverified`, `contracts/candidates.py`.
- **Decisions.** A unit ends `failed` for refusal/malformed/oversized output, tool-allowlist violation or a hit limit
  (nothing persisted); transient provider errors end it `interrupted` with the reservation left open so a fenced retry
  resumes it; the unit is finalized before its reservation is settled. Warnings (a defaulted meter unit) never block.
  Subject mismatch with the document's own records leaves the candidate unattached and flagged.
- **Orientation.** Rotation flag, then text-layer character angles (reliable on synthetic pages). The ink-profile check
  for image-only pages is **opt-in**: on the real scanned PV-17/PV-21 pages it rotated already-upright pages by 180/270
  degrees, so the default sends image-only pages as pdfium renders them. A better scan orientation check is open.
- **Calculation guard.** `engineering/provenance.py`; `PerforationHistory.build` rejects marked records. The trajectory
  entry has no provenance input yet (open, for the reconstruction consumer).
- **Repair round (QA RETURN).** Values must be whole tokens of the quote (`3000` is not in `13000`); the unit must
  agree with the unit written next to the value in the quote (a conflict rejects, an absent claim uses and records the
  quote's unit); the meters default applies only when neither the quote nor the cited context states a unit, a context
  header such as `(ft)` supplies the unit, a claimed non-meter unit that nothing states is flagged; numbers parse
  strictly (mixed fractions for sizes, Unicode minus, an unambiguous decimal comma, everything else flagged
  `number_unparseable`); a subject must be supported by the document's parsed wellbore links or named in the cited
  span (for PDFs also on page 1, the cover/header); `page_read` fields (depth, sizes, notes) are verified against the
  text layer one by one, unsupported fields are removed and the candidate is flagged; parsed conflicts compare with
  the records at the cited lines, else with the whole parsed set of the wellbore/attribute (records at another
  effective time are not comparable).
- **AX-11 deferral.** The coordinate/trajectory fallback is NOT built: every coordinate, trajectory or survey-type
  candidate is `flagged` with `coordinate_fallback_unsupported`; there is no accept path until AX-11 exists.
- **Finalize then settle.** A unit is finalized before its reservation is settled; a failed settle or a crash between
  the two is repaired by the idempotent `settle_finished_units` sweep (harness `recover_interrupted` and app startup).
- **Cache of failures.** Failed and cancelled results are cached as final under their key; only a `retry` bump
  (`:rN`) re-runs. Identical repeated tool calls are separate steps (ordinal in `step_key`).
- **Residual risk (pdfium).** Rendering runs in-process under one lock with bounded size and concurrency but no render
  timeout; a pathological PDF could stall the render thread. Process isolation is a follow-up.
- **Orientation.** The model is told about the `rotation` parameter of `get_page_image`; TASK-041 passes explicit page
  lists and rotations for the known rotated F-14 schematic.
- Not done here: xlsx/xml locators for candidates, live behavior.

### Implementation notes (TASK-041, equipment candidates, stub provider only)

- **Code.** `candidates/equipment_prompt.py` (versioned prompt `eq-prompt-1`, effort `low`, closed schema, `rotation`
  hint, zero items on pages without equipment), `schema.py` (`WireEquipment`, closed EQ-8 taxonomy, no wellbore field),
  `equipment_validators.py`, `equipment.py` (page plans `eq-pages-1`, scope check, `EquipmentExtractor`), harness kind
  `equipment` (rotation and bound subject are part of the cache key; a unit accepts only its own candidate class),
  `contracts.candidates.EquipmentAttributes` and the `wellbore_id`/`category` read filters. No migration.
- **Always model-read.** Every equipment candidate is `model_read`, `unverified`, state `candidate` or `flagged`
  (`rejected` only for a locator that does not resolve, a document other than the unit's, or an item that cannot be on
  a text-layer page with no equipment vocabulary). The DB CHECKs make acceptance impossible; the calculation guard
  rejects the marker; no parsed value is compared with or changed.
- **Flag, not drop.** OD/ID outside 0.5 to 40 in, length <= 0, depth outside 0..15000 m or beyond the wellbore's known
  MD range plus 5 percent (`identity.resolver.known_md_max`, DC-3; TVD is not checked), id > od, top below bottom,
  a glued MD/TVD pair, an unparseable/ambiguous size (`95/8`), a missing size unit, a depth printed on another line than
  the item's label: stored with the printed text and a reason. A missing depth/length unit is meters (warning only).
- **Attachment.** The model never names the wellbore. A candidate attaches to the wellbore linked to its document by
  TASK-046 record links (exactly one), else to a caller-bound subject label that resolves through the identity rule and,
  where a text layer exists, is named on the page (a page naming another well wins); otherwise it stays unattached with
  a finding. PDFs have no record links today, so real runs need the caller-bound subject (open: a document-to-wellbore
  link for PDFs).
- **Pages.** Configured lists by content hash (F-14 FWR completion: 4, 29, 30, 35, 36 with p.36 rotated 90; F-5
  completion report: 48, 49; controls opt-in), then text-layer triage, then an opt-in blind sample. An image-only
  document with no list and no opt-in selects nothing and the run ends `failed: no_pages_selected`.
- **Wrong folder.** A document whose first three pages print well labels, none of them the expected subject, is
  excluded (recorded unit, state `failed`, reason `document_excluded_wrong_subject`, no model call); explicit exclusions
  are recorded too. A scanned document cannot be checked and is reported as unchecked.
- **Shared-validator hardening (TASK-036 QA follow-ups).** A unit word written away from its value flags
  `unit_away_from_value` instead of defaulting; page-item fields must sit on the label's line (`field_not_associated`);
  a cited page that names another well wins over the cover rule (`subject_page_names_other_well`); a glued `95/8`
  is `size_ambiguous`. Cache versions `validators-2`, `wire-2`.
- **Live (EQ-11).** `scripts/run_equipment_live.py` is the guarded runbook (`--allow-live`, `--spend-cap-usd`,
  `FIELDLENS_LIVE_META=1`); not run. Its code paths are tested offline.

### Implementation handoff and integration

| Field | Record before handoff / after integration |
|---|---|
| Feature commits / tested HEAD | pending |
| Verification | pending; stub provider only, label live vs offline |
| Execution usage | pending; actual model/effort evidence |
| Compatibility assessment | pending; new feature, possible shared-contract addition |
| Proposed version bump | minor, orchestrator allocates |
| Proposed changelog entry | FL-022: validated model-proposed extraction candidates |
| Related documentation | INGESTION.md, DATA_QUALITY.md cross-references |
| Residual blockers / owned resources | none yet |
| Integrated commit / final version | pending |
| Backlog status | ready |
