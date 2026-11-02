# Specification: Model-assisted classification and wellbore identity for PDFs without a native profile

> **Spec type:** Agent task (backend, then UI surfacing).
> **Load-bearing frameworks:** outcome, acceptance, failure conditions.
> **Date:** 2026-11-02. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Approved for implementation (loose first slice, owner 2026-11-02); dispatch after TASK-070 merges.
> **Backlog ID:** TASK-055. **Delivery state:** proposed -> ready after TASK-070.
> **Approved spec revision/date:** 2026-11-02. **Integration version:** pending.
> **Zero-Question Score:** 1 owned, non-blocking (section 6).

Slice of [PROCESSING_FLOW](PROCESSING_FLOW.md) stage 2 (D1-D3, D7, PF-4/PF-5). Replaces the
stub `ProcessingStep` in `backend/fieldlens/processing/steps.py` for documents without a native
profile. OCR stays out (D8, TASK-060).

## 1. Outcome Statement

After this increment, a user can select PDFs that have no native parser (for example the Volve
completion PDFs), see the estimate (pages, tokens, USD, remaining USD 5 cap), confirm, and the
model reads the pages and records for each document (a) a category or at least a descriptive tag
set, and (b) the wellbore(s) the document is about, each with page and quoted evidence. The
result appears in the Sources view as "model-read, unverified"; the document stops reading as an
unsupported dead end. Verification: stub-provider tests for all ACs, then one bounded live run
on 1-2 real completion PDFs inside the USD 5 cap, recorded in the ledger. Outcome score: 3.

## 2. Scope

### IN Scope

1. A model step (`ProcessingStep.run_document`) that reads a bounded page sample per document
   (first pages up to a configured bound, default 5 pages, never more than the confirmed
   estimate) and returns one validated JSON object: `category` (one of the existing eight
   `DocumentCategory` values, or null), `tags` (up to 5 short descriptive strings), and
   `identities[]` (`subject_kind` well|wellbore, `name_as_written`, `page`, `quote`).
2. **Loose acceptance rule (owner):**
   - classification success: a category is stored in `suggested_categories` (origin
     `model`), plus tags; user categories always win and are never overwritten;
   - classification failure or no confident category: falls back to the **others** bucket,
     i.e. category `general_report` with tag `unclassified` and a description tag when the
     model supplies one; this is not an error;
   - identity is the minimum: at least one wellbore identity with page and quote evidence;
   - no identity found: the document gets a **non-blocking warning** (issue "no wellbore
     identity found") and stays visible with its category/tags; other documents and the run
     are unaffected.
3. Identities are **proposals, not accepted facts** (`model_proposal`, "Model-read,
   unverified"). A proposal links to an existing wellbore only when its normalized name equals
   an existing wellbore key exactly; otherwise it stays unresolved for merge review (TASK-057
   alias path). Quote must appear in the page text read by the step; proposals whose quote is
   not found are dropped with a warning.
4. Persistence: proposals and the model's category/tags with run id, provider/model revision,
   page, quote, extraction method `model_classification`, prompt/schema version; a new
   migration (next free number at dispatch time) for `document_identity_proposal` unless the
   implementer proves `extraction_candidate` fits (decision recorded in the handoff). Results
   are project-scoped and cache-keyed by document revision and prompt version, so re-runs do
   not respend for unchanged inputs (cache hit reported in the run).
5. Provider: a live `PageProvider`/step over the existing Meta adapter (TASK-004/043,
   `assistant/meta.py`), Standard mode, bounded retries, refusal/truncation/malformed-output
   handled as per-document failures (retryable), spend recorded in the ledger. Stub provider
   path stays the default for tests.
6. UI (second step in the same lane): the Sources evidence panel shows the proposed category,
   tags and identities with page and quote, the "Model-read, unverified" label, the
   "no wellbore identity" warning, and replaces "unsupported" with "no native parser; model
   processing available" plus the Process action for run-less/unsupported documents.

### OUT of Scope

OCR; label-driven field extraction (trajectory/completion fields) beyond identity; auto-accepting
proposals; merge review UI (TASK-065); using proposals in engineering calculations; surface
location (D5); TASK-041 equipment candidates (dependency waived for this slice).

### Scope Dependencies

TASK-054 processing runs (done), TASK-070 storage integrity (must merge first: reliable reads),
TASK-004/043/005 provider adapter and live gate (done). Live run needs explicit orchestrator
authorization and a per-run cap (PROCESSING_FLOW D7).

## 3. Acceptance Criteria

| ID | Type | Given / when / then | Score | Test |
|---|---|---|---|---|
| AC-1 | Behavioral | Stub provider returns category + tags + one wellbore identity with quote: the document stores the category in suggested categories and tags, an unresolved or linked identity proposal with page/quote, and is not `unsupported`. | 3 | backend test |
| AC-2 | Behavioral | A user-assigned category exists: it remains the effective category; the model suggestion is stored separately. | 3 | backend test |
| AC-3 | Edge | Model returns no/invalid category: document gets `general_report` with tag `unclassified`; the run does not fail for it. | 3 | backend test |
| AC-4 | Edge | Model finds no identity: document gets the non-blocking warning, keeps category/tags, no proposal rows, run status still succeeded for the document. | 3 | backend test |
| AC-5 | Negative | An identity whose quote is not in the read page text is dropped and counted as a warning; nothing is stored as an accepted fact; no engineering calculation reads proposals. | 3 | backend test |
| AC-6 | Behavioral | Exact normalized name equals an existing wellbore key: proposal links to it; a near-miss stays unresolved. | 3 | backend test |
| AC-7 | Budget | The step never reads more pages than the confirmed estimate; an exceeded estimate stops the run with the existing budget failure; refusal, truncation, malformed JSON and provider error each give a typed retryable per-document failure and no partial identity rows. | 3 | backend test |
| AC-8 | Cache | Unchanged document revision and prompt version reuse the stored result with zero provider calls. | 3 | backend test |
| AC-9 | Security | Document text is passed as data inside delimiters; an injected instruction in a page cannot change the schema, call tools or alter other projects (the step has no tools). | 3 | backend test with hostile page text |
| AC-10 | UI | Evidence panel shows category/tags/identities with page+quote and the unverified label, the warning for no identity, and the Process action for unsupported/run-less documents; a11y checks pass. | 3 | Vitest + Playwright |
| AC-11 | Live | One bounded live run (<= 2 documents, per-run cap set by the orchestrator) records spend in the ledger and yields either an identity or the warning; no secrets or document text in logs. | 2 | live_meta marker, recorded result |

## 4. Context and Decisions

- Owner (2026-11-02): generic PDF processing is agentic via the Meta API and manually triggered
  with confirmation; loose first criteria as above; identity is the minimum; failure to
  classify falls back to "others"; missing identity is a non-blocking warning.
- "Others" maps to the existing category `general_report` with tag `unclassified` (assumed,
  avoids a taxonomy change; revisit if the owner wants a distinct value).
- Delegation: `fieldlens-rag` for the model step/prompt/schema/validation (Sonnet 5.5 / medium),
  `fieldlens-frontend` for the UI part, independent `fieldlens-qa`; own worktree, branch
  `feature/task-055-document-identity`, own `./dev` lane.
- Spend: the USD 5 total live cap is shared across all lanes (D7); default tests use the stub.

## 5. Failure Conditions

- Model refuses or returns malformed output: document failed, retryable, no partial rows.
- Identity quote not found: proposal dropped, warning, never stored as evidence.
- Provider outage or budget exhausted: run stops with the existing typed codes; nothing is
  marked successful.
- Worst misinterpretation: tagging a document "classified" from the filename or the upload
  hint. Category must come from page text with quote evidence; filenames and categories are
  hints only.

## 6. Ambiguity Audit

Owned, non-blocking: whether "others" should become a distinct category value (owner, decide
at the browser checkpoint). Default page bound (5) is a cost choice, adjustable via setting.

## 7. Implementation Guidance

Plug into `ProcessingStep.run_document` and the runtime provider selection
(`processing/runtime.py`); reuse `document_classification.suggested_categories/tags`; keep
prompt and schema versioned and testable offline. Handoff table per the
[workflow](../DEVELOPMENT_WORKFLOW.md) section 5.

## Open Tensions

None.

## Assumption Registry

- The first pages of a completion PDF usually contain the well/wellbore name (M): invalidated
  by live results; the page bound is configurable.

## Adversarial Self-Critique

A plausible but wrong wellbore name could pass if the quote exists on the page: it stays an
unverified proposal until reconciled; no calculation consumes it.

## Revision Triggers

Owner wants a distinct "others" category; provider output schema changes; OCR benchmark result.
