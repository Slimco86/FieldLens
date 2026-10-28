# Specification: Versioned evidence and selection contracts

> **Spec type:** API contract. **Backlog:** FL-004, consumed by FL-005 through FL-012.
> **Load-bearing frameworks:** F2 acceptance, F4 context, F5 failures.
> **Supporting:** F1 outcome, F3 scope, F6 ambiguity.
> **Date:** 2026-10-27. **Decision owner:** project owner; technical owner: orchestrator.
> **Status:** Design proposal complete; owner approval required before implementation.
> **Zero-Question Score:** 0 unowned design questions; G1/G2/G5 remain execution gates.

## How to Read This Spec

Implementers: contracts in section 4; QA: section 3 and failure cases; owner:
scope, tensions and assumptions. This implements project AC-1/2/3/6/7/8/10.

## Notation Key

`[Validated]` is an owner-confirmed invariant, not a runtime result.
`[Assumed: verify]` is a proposed design/limit requiring owner approval.
H/M/L are confidence judgments. AC score 3 is binary-testable. Unless explicitly
validated, wire-format choices below are `[Assumed: verify, H; owner before FL-004]`.

## 1. Outcome Statement

Every API, projection, chart and tool can identify the same source-backed object
at the same revision/time without interpreting a filename or inventing metadata.
Verification: SC-1 through SC-6; outcome score 3.

## 2. Scope

### IN Scope

Identity, evidence, revision/time/selection, error and bounded read contracts.
Engineering truth and time separation are `[Validated: project requirements]`.

### OUT of Scope

Source-specific column/event mappings (FL-005/G1), formulas (FL-006/008),
UI rendering (feature owners), multi-tenant authorization and generic SQL tools.

### Scope Dependencies

FL-004 implements these declarations before downstream workers write shared
models. Consumers may use labeled synthetic fixtures, never claim G1 acceptance.

### Open Scope Tensions

Unknown source schemas versus stable APIs: retain original source records and
versioned adapter profiles; canonical contracts reject missing critical metadata.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| SC-1 | Behavioral | OpenAPI schemas generate strict TS types; representative valid request/results round-trip without lost IDs, units, time precision or evidence locators. | 3 | [Assumed: verify] | `test_contract_roundtrip` |
| SC-2 | Negative | A source/object/claim outside requested dataset revision cannot be returned through direct ID lookup, graph expansion, chart or source navigation. | 3 | [Validated] | `test_revision_scope` |
| SC-3 | Edge case | Unknown measurements carry no numeric zero default; nonfinite floats, invalid enums and unrecognized request fields receive 422 with a stable error code. | 3 | [Validated] | `test_invalid_contracts` |
| SC-4 | Behavioral | Changing revision, selected entity or as-of precision changes cache/context keys; a response with the old context cannot update the current view. | 3 | [Validated] | `test_context_keys` |
| SC-5 | Negative | A generic OD and catalog installation date are rejected as authoritative installed measurements; evidence class is independent of validation state. | 3 | [Validated] | `test_evidence_classes` |
| SC-6 | Non-behavioral | Collection results never exceed 200 rows; numeric display windows never exceed 5,000 points; invalid bounds fail rather than silently widen. | 3 | [Assumed: verify] | `test_read_bounds` |

Definition of done: all six tests against generated types and PostgreSQL pass;
no source-data/provider success is implied by synthetic round trips.

## 4. Context and Decisions

Executor: `fieldlens-backend`, coordinating generated client ownership through
the orchestrator. One worker edits `backend/fieldlens/contracts/`,
`frontend/src/api/generated.ts` and the migration head per integration.
Date: 2026-10-27. Shared truth rules come from the project specification.

### Core envelopes

| Record | Required fields and invariants |
|---|---|
| Dataset | UUID `dataset_id`, display name, nullable `active_revision_id` |
| Revision | UUID `revision_id`, dataset FK, nullable parent revision, manifest hash, UTC `created_at`, status `staging/ready/ready_with_issues/failed`; published content immutable |
| Source document | UUID `document_id`, dataset, source revision ID, SHA-256, bytes, original filename, media type, origin/rights metadata, server-owned storage key |
| Source record | UUID `record_id`, document/source revision, typed locator, original values, extractor name/version/profile, extraction coverage |
| Claim | UUID `claim_id`, subject UUID/type, attribute key, typed original value/unit, normalized value/unit when valid, source record IDs, validation/evidence class, optional superseded claim |
| Validation | `unreviewed/valid/conflicting/invalid/unsupported`; issues carry code, attribute/record IDs, severity and human explanation |
| Evidence class | `source_record/catalog_derived/derived/interpolated/generic`; no class implies validation |
| Coverage | `complete/partial/unknown`, inspected and total page/record counts where known, missing ranges and reasons |
| Quantity | Original value/unit/reference; normalized finite numeric value/unit only when conversion is validated; unknown result has `value:null` plus reason |
| Derived result | Algorithm/version, input claim IDs and revision IDs, parameters, tolerance/error bound, output artifact hash |

Use explicit typed claim-value variants, not arbitrary JSON accepted as engineering
truth. UUIDs are generated server-side; filenames and display labels are not IDs.
Revision membership has composite foreign keys so dataset/revision/subject joins
cannot cross scopes. Immutable blobs may be reused, but authorization/context
checks operate on document membership, not knowledge of a hash.

### Evidence locators

`locator.kind` selects a closed variant:

- `pdf`: 1-based page; optional table/cell identifier and normalized page
  rectangle `[x0,y0,x1,y1]` in top-left coordinates within `[0,1]`.
- `xlsx`: sheet name and A1 cell/range.
- `xml`: namespace URI, element path and source UIDs when present; attribute name
  for attribute claims. Never evaluate arbitrary user XPath.
- `text`: 1-based line range; CSV also includes logical record and column name;
  LAS includes section, mnemonic and data-line locator.
- `derivation`: algorithm result ID plus input claim IDs, not a fake source page.

All locators include document/source revision. Missing page boxes do not become
invented highlights: open the page and display the supported locator.

### Identity and physical references

Well and wellbore are distinct tables. Wellbore has well FK and nullable sidetrack
parent; reject cyclic parents. Aliases are explicit, source-backed mappings.
Case folding and whitespace normalization may aid exact lookup; punctuation and
sidetrack suffixes are retained. Ambiguous alias matches return candidates.

Survey records require MD, inclination, azimuth, original units, angle/north
reference, horizontal CRS, vertical/depth reference and source station IDs.
Equipment instances require a configuration relation; type/model/dimensions and
placement each have their own claims. Catalog model IDs never imply instance
presence, quantity, depth, orientation or effective dates.

### Historical and UI context

`AsOf` is a discriminated union:

- `instant`: RFC3339 timestamp with offset, normalized to UTC.
- `day`: ISO calendar date and explicit IANA timezone for the query.

Source events preserve the literal date/time, precision
`instant/day/month/year/unknown`, known timezone, and earliest/latest possible
effective bounds when derivable. Report, import and revision times are separate.
An unknown source timezone stays unknown. It cannot be silently equated to the
query timezone. Only an approved source profile resolves this mapping.

For an instant query, include events certainly effective by that instant and
mark potentially effective ambiguous events. For a day query, return a resolved
state only if it is invariant throughout that day; otherwise return the distinct
states/ambiguous ranges, not an arbitrary midnight or end-of-day state.
No enumeration of factorial event orders: interval constraints and conservative
unknown/conflicting results are acceptable; invented ordering is not.

`QueryContext = {dataset_id, revision_id, selected_entity_type,
selected_entity_id, as_of}`. Entity types are `field/well/wellbore/component/interval`.
Queries without an entity use explicit null entity fields, not an implicit bore.
Series keep measurement/acquisition time alongside this selection context.

State/result status: `resolved/partial/unknown/conflicting`. State result includes
intervals, physical coverage, access, scoped flow, quantity results, coverage and
evidence/derivations. An incomplete total is null; an independently justified
known-subset length is a separate labeled value, never the exact total.

### REST surface

All dataset reads below require `revision_id`; temporal endpoints also require
`as_of` and its precision. Requests use generated query/body schemas, not free SQL.
All paths begin `/api/v1`.

| Method/path | Request / result |
|---|---|
| `POST /datasets` | Name -> Dataset, HTTP 201 |
| `POST /datasets/{id}/imports` | Multipart files + typed manifest, optional parent revision/idempotency key -> revision/job IDs, HTTP 202 |
| `GET /datasets/{id}/revisions` | Cursor -> bounded revision summaries |
| `GET /jobs/{id}` | Persistent job/attempt/stage/progress/issues and typed result/artifact reference when complete; validate dataset/revision membership |
| `POST /jobs/{id}/cancel` | Idempotent cancellation request -> HTTP 202; terminal state unchanged |
| `GET /datasets/{id}/assets` | Context/filter/cursor -> bounded typed asset summaries |
| `GET /datasets/{id}/scene` | Context -> render origin, object IDs, layer/configuration manifests and bounded artifact URLs |
| `GET /datasets/{id}/equipment/{component_id}` | Context -> installed/catalog/generic attribute envelopes |
| `GET /datasets/{id}/wellbores/{bore_id}/perforations` | Context -> canonical temporal state result |
| `GET /datasets/{id}/series` | Context, entity and family `production/log` -> associated definitions, scope and units |
| `GET /datasets/{id}/series/{series_id}/points` | Time/depth bounds, display flag, limit -> points plus acquisition/decimation metadata |
| `POST /datasets/{id}/closest-approach` | Revision, two bore/survey IDs, MD bounds -> HTTP 200 cached distance/points/MDs/error/evidence, or HTTP 202 computation job ID |
| `GET /datasets/{id}/evidence/{claim_id}` | Revision -> claims, locators and derivations |
| `GET /datasets/{id}/documents/{document_id}/content` | Revision, validated HTTP Range -> original bytes; no arbitrary paths/URLs |
| `GET /datasets/{id}/artifacts/{artifact_id}` | Revision -> immutable render/series artifact bytes |
| `POST /datasets/{id}/assistant/requests` | Question + QueryContext -> assistant request ID, HTTP 202 |
| `GET /datasets/{id}/assistant/requests/{request_id}` | Revision -> pending/completed/failed/cancelled result, validated answer/citations/actions/usage |
| `POST /datasets/{id}/assistant/requests/{request_id}/cancel` | Revision -> cancellation request, HTTP 202 |
| `POST /datasets/{id}/assistant/actions/{action_id}/ack` | Revision/context + `applied/rejected/stale`, reason -> recorded acknowledgment |

Assistant requests use the persisted job infrastructure but execute async provider
I/O in a bounded API-owned task with a stored lease/terminal result. On API restart,
in-flight provider work becomes `interrupted`, not automatically replayed/billed.
The CPU worker never monopolizes provider execution or vice versa.

Uncached closest-approach calculations run in the persistent CPU queue, not the
API event loop. The UI polls the job; the assistant tool awaits the same typed
result only within its remaining deadline. Busy/expired computation returns an
explicit pending/timeout result, never a guessed or best-so-far exact distance.
Cancellation affects only jobs owned by that request, not unrelated imports.
Temporal interval projections are materialized at event boundaries during
ingestion; ordinary as-of reads select those projections rather than replaying
unbounded histories inside the API handler.

Successful read envelope: `{context, data, coverage, issues, provenance}`.
Pagination adds `{next_cursor}`; defaults 50, maximum 200. Cursor includes filters
and revision, and is validated on reuse. Numeric windows maximum 5,000 points;
full-resolution calculations run server-side and return small result objects.
Display decimation discloses method, original count and retained extrema/gaps.

Error envelope: `{error:{code,message,request_id,details}}`; sanitized details,
no secrets/source body. HTTP 413 limits, 415 unsupported media, 422 malformed
contract, 404 nonexistent/out-of-context object, 409 conflicting/stale context or
unready revision, 429 local capacity/budget pause, 503 provider/index unavailable.
Partial engineering results use the success envelope with explicit coverage/issues;
invalid requests and failed jobs do not return success-shaped empty arrays.

### Cache, tools and actions

Cache key: dataset/revision + selected entity + as-of value/precision/timezone +
query parameters + algorithm/survey/index version. Model, extractor, source or
normalization changes invalidate only derived projections, not original evidence.
Content hashes alone do not determine temporal cache eligibility.

Tools wrap these services using strict Pydantic argument/result models.
Allowed action types: `select_asset`, `focus_asset`, `show_chart`, `open_evidence`,
`set_as_of`, `set_layer_visibility`. Action includes UUID, expected context and
validated target; the client acknowledges only after applying it. A changed
context rejects stale actions. No arbitrary JS, SQL, XPath, URLs or filesystem IO.

## 5. Failure Conditions

Data: source identity/reference disagrees with canonical requirements -> retain
the source and block affected claims; request profile correction, not a default.
Process: two workers modify generated types/migration head -> stop the second
writer and serialize regeneration through the orchestrator.
Worst misinterpretation: schema-valid data is not automatically evidence-valid;
SC-2/3/5 test this explicitly.

## 6. Ambiguity Audit

Time precision, unknown values, correction identity, pagination and action
acknowledgment are defined above. Unknown source mappings remain G1 tasks owned
by ingestion/owner before those adapters are accepted. No unowned design question.

## 7. Implementation Guidance

Implement Pydantic discriminated unions and PostgreSQL constraints; export OpenAPI
to TS with `openapi-typescript`, not duplicate handwritten frontend contracts.
Planned checks: `uv run pytest backend/tests/contracts` and
`npm --prefix frontend run typecheck`. Foundation must first create these commands.
No implementation, tests or integration commits exist for this spec yet.
Proposed release classification on implementation: new feature, minor.

## Open Tensions

Strict source validation can leave an incomplete scene. Preserve the validated
subset and visible blockers; only the owner can accept a different pilot/scope.

## Assumption Registry

| Assumption | Confidence | Invalidation |
|---|---|---|
| REST and polling suffice for one local user | H | Measured interaction budget fails due to polling |
| Source profiles can supply reference/time mappings | M | G1 cannot establish essential references |
| Bounded point windows cover display needs | M | Approved chart requires more than 5,000 points without losing tested features |

## Adversarial Self-Critique

Revision membership can be missed in a helper query: watch cross-revision tests.
An exact number can hide partial coverage: watch null/known-subset contracts.
An issued action can be described as completed: watch missing client acknowledgments.

## Revision Triggers

Reopen affected contracts if G1 finds nonrepresentable time/reference semantics,
measured bounds fail AC-9, or a provider requires different action/replay semantics.
