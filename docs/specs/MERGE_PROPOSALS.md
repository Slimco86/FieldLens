# Specification: AI identity-merge proposals and review (backend)

> **Spec type:** Product/feature + API contract + Agent task.
> **Load-bearing frameworks:** outcome, acceptance, scope, failure conditions.
> **Supporting:** ambiguity audit.
> **Date:** 2026-11-01. **Author:** agent:fieldlens-rag (lane TASK-057). **Decision owner:** owner.
> **Status:** Implementing (the parent decisions D1..D8 in [PROCESSING_FLOW.md](PROCESSING_FLOW.md) are approved; the
> contract below is the implementer's reading of PF-7/D6 and is open to owner amendment).
> **Backlog ID:** FL-016 / TASK-057 (slice FL-016-H). **Delivery state:** in_progress, backend slice only.
> **Approved spec revision/date:** PROCESSING_FLOW.md D6/D7, owner, November 1 2026. **Integration version:** pending.
> **Zero-Question Score:** 0 unowned; open items in "Open Scope Tensions".

Detail for PF-7 of [PROCESSING_FLOW.md](PROCESSING_FLOW.md) (stage 4, identity refinement). It extends the deterministic
resolver of TASK-046 (`fieldlens.identity`, rule in `identity/labels.py`) and never replaces it. Related: RC-2 in
[ASSET_RECONSTRUCTION.md](ASSET_RECONSTRUCTION.md), the agent boundaries in [AGENTIC_EXTRACTION.md](AGENTIC_EXTRACTION.md)
and the provider/budget rules in [META_INTEGRATION.md](META_INTEGRATION.md).

## 1. Outcome

After this increment the backend can, on explicit user action, find source names that probably denote one already
identified wellbore, ask a model to propose same-entity groups with alias evidence quotes, validate every proposal
server-side, persist it for review, and let the user accept, reject or revert each one. An accepted proposal changes
identity only through a persisted, revertible merge record that the deterministic resolver applies on every resolution.
Nothing merges silently, and a proposal that violates a deterministic guard cannot be accepted.
Verification: `backend/tests/merge_proposals` with the stub provider (no network, no spend).

## 2. Scope

**IN.** Candidate blocking over the resolver's output inside one project; deterministic guards; the model step behind the
existing `Provider` protocol and `WorkUnit` budget path; server-side validation of model output; persistence, list/get,
accept, reject, revert; run record with usage; spend estimate and explicit confirmation before a run.

**OUT.** Review UI (TASK-053). Merging different designators (renames, "Gudrun A-12" for "F-12") even with a quote: v1
forbids it, a later owner decision may allow it with explicit source-supported evidence. Merging well-level entities
(`well` rows are only ever changed by the resolver). Cross-project merges. Equipment and perforation entity merges
(RC-2 reconciliation inside reconstruction). Live model runs (D7: need orchestrator authorization; default tests use the
stub). Embedding or retrieval changes.

**Dependencies.** TASK-046 resolver (`resolve_project`, `current_subject_groups`), extraction harness provider/budget
interfaces, `BudgetLedger`/`WorkUnit`, `SourceReader` for quote verification.

## 3. Definitions

- **Target**: an existing resolved wellbore (`wellbore` row) that remains.
- **Member**: a name proposed to denote the target. Kind `label` (a raw source label that the resolver could not turn into
  a wellbore: `not_a_well`, `ambiguous`) or kind `wellbore` (another resolved wellbore, for example a
  different spelling of the block `15/09-F-12` for `15/9-F-12`, or, since TASK-061/D9, a block-less wellbore `F-12`
  beside the block-qualified `15/9-F-12`; the pair is proposed once, with the block-qualified wellbore as target).
- **Designator**: block (optional), well slot (`F-12`), suffix (`A`, `T2`, none). Parsed from a label by
  `merge_proposals.designator.extract_designator`; a label with no extractable slot has no designator.
- **Block** (blocking unit): one target plus the members whose designator is guard-compatible with it.
- **Merge record** (`identity_merge`): durable `source_key -> target_key` mapping applied by the resolver. Source key is a
  normalized label (`label`) or a wellbore key (`wellbore`).
- **Dataset fingerprint**: SHA-256 over the resolver version and the sorted resolved wellbore keys, unresolved label
  groups and current extraction run ids of the project. Stored on runs and proposals; it versions every retrieval of the
  proposal context.

## 4. Deterministic guards (G1..G8)

Evaluated at proposal time (a failure persists the proposal as `blocked`, not acceptable) and re-evaluated at accept time
(a failure returns 409 and changes nothing). The model cannot waive a guard.

| ID | Guard | Rule |
|---|---|---|
| G1 | scope | target and every member belong to the project; a `wellbore` member and the target are different rows; no member is the target |
| G2 | level | every member has a parseable designator; a field-level name (`Volve F`) or a well-level label that names no wellbore designator is never merged; `well` rows are never merged or re-parented by this flow |
| G3 | designator equality | well slot equal; suffix equal (both none or the same canonical suffix); blocks equal after numeric normalization (`15/09` = `15/9`); an unqualified label is compatible with any block. So `F-12` never merges with `F-12 A`, `F-12 B`, `F-14` or `F-11`; a bore never merges with another suffix |
| G4 | sidetrack preservation | a merge never changes `parent_wellbore_id` relationships by itself: the resolver re-derives parents by name suffix after the merge; a member with a suffix needs the same suffix on the target (G3), and no accepted merge may fold a sidetrack into its parent |
| G5 | planned vs as-built | a lexical marker (`plan`, `planned`, `prognosis`, `proposed` versus `as-built`, `as built`, `actual`, `final`, `drilled`) on any member or target name must be shared by all of them; mixed or one-sided markers fail. No planned/as-built state exists in the data model yet, so this is lexical and conservative |
| G6 | no chains | a source cannot already be an active target, a target cannot already be an active source, and a source has at most one active merge |
| G7 | evidence | for each merged member there is at least one evidence item. A `quote` item: the quote (a) is present in the cited document's text (NFKC, case-folded, whitespace-collapsed; bounded read), (b) contains a boundary-delimited spelling of the member and of the target (the short target alias only when the slot is unique among resolved wells in the project), and (c) names the target without a trailing sidetrack suffix. A `survey_match` item (no quote, no document id supplied by the model): the server's own candidate table says the member's and target's surveys come from different documents and are equal (`exact` or `stations_md`, see 5.1); it is stored as two evidence items (one per survey document, each with its content hash) |
| G8 | surface location | both parties' surface locations, when both exist, are not contradictory (>= 50 m apart; <= 5 m is "same"; missing on either side is "unknown" and neither blocks nor supports). A contradictory candidate is never placed in a block; a forced model reference is stored `blocked` and accept returns 409. G1..G6 are unchanged |

Accept-time additional checks: the proposal is `pending`; the target and any `wellbore` member still exist; the evidence
documents still exist with an unchanged content hash (otherwise `stale`); no other accepted merge conflicts (G6); G8 is
recomputed from current data.

## 5. Model step

Behind the existing `Provider` protocol, executed through `WorkUnit` (reservation, attempt bound, deadline, output cap,
cancellation, usage recorded per attempt). The default provider is the stub; there is no runtime default that calls Meta.
The app exposes no live provider: `app.state.merge_proposer` is `None` until a runner is configured, and run endpoints
return 503 `provider_unavailable` then.

- Input (bounded): per block, the target and members with opaque refs (`m1`..`mN`), names, kind, bounded document
  snippets that contain the name (document id, line, at most 240 characters). At most `max_blocks_per_call` blocks and
  `max_calls` calls per run; blocks beyond that are reported `deferred`. Source text is data, never instructions.
- Output: one JSON object `{"groups":[{"target","members","evidence":[{"member","document_id","quote"}],"rationale"}]}`,
  parsed strictly (closed schema, bounded lengths). No tools, no free text outside the JSON.
- Failure handling (explicit, never a silent partial): provider refusal, truncation, malformed/invalid JSON, auth,
  rate-limit/5xx after the single runner retry, timeout, budget or limit exhaustion and cancellation each end that call
  with a stable reason code; blocks of that call create no proposals; the run is `partial` or `failed` with the reason.
  Refusals and malformed output are never retried automatically. Interrupted calls keep their reservation liability.
- Validation order per proposed group: refs exist and are in the block, target is a `wellbore` ref, no duplicates, quotes
  verified (G7) -> dropped with a counted reason code on failure; then G1..G6 -> persisted `blocked` with the guard
  result on failure; otherwise `pending`.
- Pairs already `rejected` by the user are excluded from later blocking, so a rejection is not re-proposed.
- Usage: input/output tokens, provider calls and USD (from the ledger) are stored on the run, per call.

### 5.1 Candidate evidence table and re-planning (TASK-086)

Real data rarely names both spellings in one document: the unqualified `F-5` comes from a text survey (stations,
header, surface location), the qualified `15/9-F-5` from a PDF survey and trajectory XML. The model therefore also
receives, per block and candidate, a deterministic zero-cost table (`merge_proposals/content.py`): name similarity,
same slot, shared source families (record kinds), survey comparison (`exact` = same station count, MD range and hash of
md/incl/azi at 2 dp; `stations_md` = same count and MD range; `different`; `no_data`; surveys need >= 10 stations and
the same document never counts), surface-location comparison (`same`/`contradictory`/`unknown`), plus a bounded
project context (wellbore names). The model still decides; it may propose a pair on a verbatim quote or on
`survey_match`. The server verifies the claim against its own table, always stores `pending`, and never applies it.
Accept/Reject remain user-only. Evidence kind is exposed as `evidence_kind` (`quote` default) and shown in the review UI
as "Matching survey" instead of a quote.

Plan fingerprint (stored on the run's `dataset_fingerprint`; proposals keep the identity fingerprint) = identity
fingerprint + `GUARD_VERSION` + `PROMPT_VERSION` + `CONTENT_VERSION` + the evidence signature of every same-slot
candidate pair (rejected pairs included, so a rejection does not re-plan). A succeeded run with 0 proposals is reused
only when all match; otherwise the stage re-plans. Stage messages: "the model found no matches: ..." (ran, none),
"... re-checked because <evidence/guard/prompt changed>" and "no new matches to propose; <why reused>".
Output bound = configured 8192 + 1024 per block beyond 2; first attempt effort `medium` (owner decision: adequate
thinking budget to judge ambiguous pairs such as a `stations_md`-only match); one truncation retry (TASK-084) at
`minimal` effort with the doubled bound (16384 for <= 2 blocks, 18432 for 3, at most 20480 for 4), inside the same
reservation. Reservation 0.60 USD per call, deadline 240 s, at most 3 calls per run (worst case 1.80 USD reserved,
settled to actual). The 0.60 covers the first attempt's full spend plus the retry's upper bound at an assumed
frontier-class rate (about USD 3 in / 15 out per Mtok); the real Meta rate comes from the pricing row and was not
verified (no live call), and the estimate endpoint reports the bound from that row. Typical actual spend is a few cents.

## 6. Persistence (migration 0012_merge_proposals)

`merge_proposal_run` (state, reason, model, prompt/guard versions, dataset fingerprint, counts, per-call usage JSON),
`merge_proposal` (project, run, status `pending|accepted|rejected|reverted|blocked`, target wellbore id/key, guard result,
rationale, dataset fingerprint, decided_by, decided_at, decision note), `merge_proposal_member` (ordinal, kind, source key,
wellbore id, evidence items with document id, content hash, quote), `identity_merge` (active when `reverted_at IS NULL`;
partial unique index on `(project_id, source_key)`). All rows are project-scoped through composite keys.

Accept runs in one transaction: lock the proposal row, re-check state, guards and staleness, insert the merge records,
run `resolve_project` (idempotent rebuild that applies active merges), mark the proposal `accepted` with who/when.
Revert marks the merge records reverted and re-resolves, restoring the deterministic identities.
The resolver applies merges inside `current_subject_groups`, so the identity listing, `resolved_current` and links stay
consistent; merged links use basis `merge:accepted`.

## 7. API (all project scoped; mutations need the session guard)

| Method and path | Result |
|---|---|
| `POST /api/v1/projects/{id}/merge-proposals/estimate` | blocks, calls, USD upper bound; no spend |
| `POST /api/v1/projects/{id}/merge-proposals/runs` | body `{confirm:true}`; runs bounded model calls; returns the run |
| `GET /api/v1/projects/{id}/merge-proposals/runs` | runs with usage |
| `GET /api/v1/projects/{id}/merge-proposals?status=` | proposals with members, evidence, guard result, currentness |
| `GET /api/v1/projects/{id}/merge-proposals/{proposal_id}` | one proposal |
| `POST .../{proposal_id}/accept` `reject` `revert` | body `{decided_by?, note?}`; 409 for guard failure, stale, invalid transition |

## 8. Acceptance criteria

| ID | Type | Given / when / then | Score | Test |
|---|---|---|---|---|
| MP-1 | Behavioral | A label that spells a resolved wellbore differently (`Volve F 12`, `15/09-F-12`) is a guard-compatible member of that wellbore's block; `F-12` and `F-12 A`, `F-12` and `F-14`, `F-11 B` and `F-11 A` are never in one block | 3 | `test_blocking_respects_designators` |
| MP-2 | Negative | Guards G1..G6 fail for cross-designator, sidetrack, well-level, planned/as-built and chain cases, each with its own code | 3 | `test_guards` |
| MP-3 | Behavioral | A valid stub-provider proposal with quotes present in the cited document is persisted `pending` with both identities, quotes and the guard result | 3 | `test_stub_run_persists_pending_proposal` |
| MP-4 | Negative | Unknown refs, unknown documents, quotes absent from the source, quotes lacking either name, and invented targets are dropped and counted; no proposal is stored | 3 | `test_model_output_validation` |
| MP-5 | Negative | A model group that violates a guard is stored `blocked` and cannot be accepted (409, nothing changes) | 3 | `test_blocked_proposal_cannot_be_accepted` |
| MP-6 | Behavioral | Accept merges identities transactionally: the label's records link to the target wellbore, the decision stores who/when, re-resolution keeps the merge; reject changes nothing and is not re-proposed; revert restores the prior identities | 3 | `test_accept_reject_revert` |
| MP-7 | Failure | Refusal, truncation, malformed JSON, timeout, rate limit, budget exhaustion and cancellation each give an explicit run state and reason, no proposals for that call, usage recorded, no retry for refusal/malformed | 3 | `test_provider_failures` |
| MP-8 | Integrity | Prompt injection text inside a source document cannot add a tool, change guards or accept a proposal; run needs `confirm:true`; with no configured proposer the API returns 503 | 3 | `test_injection_and_confirm_gate` |
| MP-9 | Integrity | A superseded source (changed content hash) or a vanished target makes a pending proposal `stale` at accept | 3 | `test_stale_proposal` |

## 9. Failure conditions

Accepting a guard-blocked proposal; an accepted merge that is not persisted or not revertible; a quote not found in its
source; a model-supplied identifier used without existing in the project; a merge applied without a user decision;
a provider call without a reservation; a spend above the reservation; secrets, prompts or source bodies in logs or errors.

## 10. Open scope tensions

- Cross-designator renames with explicit source support (D6 wording "without source support") are deferred; v1 is stricter
  than D6. Owner: decide before TASK-053 UI copy is final.
- Planned/as-built has no data-model flag; G5 is lexical until reconstruction defines one.
- Live evidence: none collected. A bounded live check needs orchestrator authorization (D7); the handoff carries an estimate.

## 11. Traceability and evidence

| Spec item | Code | Tests |
|---|---|---|
| G1..G7 | `backend/fieldlens/merge_proposals/guards.py`, `designator.py`, `validation.py` | `backend/tests/merge_proposals/` |
| Model step | `merge_proposals/prompt.py`, `proposer.py` | same |
| Persistence/API | `merge_proposals/{tables,service,routes}.py`, `identity/merges.py`, migration `0012_merge_proposals` | same |

Evidence: `env -u MODEL_API_KEY uv run pytest backend/tests/merge_proposals` (26 tests, stub provider only, no network or Meta call; spend USD 0). Tests: `test_designators_and_guards_pure` (G1-G5), `test_blocking_is_guard_prefiltered`, `test_run_creates_pending_and_merges_nothing`, `test_accept_merges_transactionally_and_revert_restores`, `test_reject_persists_and_excludes_pair_from_later_blocking`, `test_invalid_output_is_dropped_and_counted` (5 drop codes), `test_guard_violating_proposal_is_blocked_and_cannot_be_accepted`, `test_vanished_member_blocks_accept`, `test_prompt_injection_in_source_cannot_merge`, `test_provider_failures_are_explicit` (refusal, truncated, malformed x2, timeout, auth), `test_rate_limit_is_retried_once_then_succeeds`, `test_budget_bound_stops_the_call`, `test_partial_run_keeps_good_calls`, `test_call_count_is_bounded`, `test_run_requires_confirmation_and_a_provider`, `test_no_candidates_run_makes_no_call`. Not covered: any live model behavior (needs D7 authorization).

TASK-086 evidence: `backend/tests/merge_proposals/test_survey_evidence.py` (11 tests, VOLVE-mirroring fixture, scripted fake provider, no Meta call, USD 0) covers EXPLORE_POLISH A-1..A-5: candidate table and three pending `survey_match` proposals, unsupported survey claim dropped, guards (different slot, block-qualified bore, planned, sidetrack, contradictory surface) still block, re-plan on prompt/guard/evidence change with none-found/recheck/reused messages, output sizing and truncation retry, accept giving the qualified bore a surface location. Real-data probe (read-only SELECT on the VOLVE project): `F-5`/`F-14` match `exact`, `F-12` `stations_md`; surface `unknown` (qualified bores have none).
