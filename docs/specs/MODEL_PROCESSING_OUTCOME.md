# Specification: Re-processable, observable model processing (follow-up to TASK-055)

> **Spec type:** Agent task (backend, then UI).
> **Date:** 2026-11-02. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Approved for implementation (owner remarks 2026-11-02 after manual checks of 0.36.0).
> **Backlog ID:** TASK-072. **Depends on:** TASK-055, TASK-071. **Integration version:** pending (minor).

## 1. Outcome Statement

Owner's manual check of 0.36.0 found: (1) the project delete control sits below the project name;
(2) a model "re-process" reported Processed in a blink with no data; (3) after Processed there is no
way to request processing again; (4) there is no way to see what the model processing produced.
Cause of (2): the run used the stub provider. `.env` carried `PROCESSING_PROVIDER=meta`, but settings
are read with the `FIELDLENS_` prefix, so the unprefixed keys were ignored without any warning, the Meta
token rates were unset, and the UI did not say a stub had run.

After this increment: the delete control is inline with the project name; a document can be
re-processed at any time through estimate -> confirm; the Model processing panel always states which
provider and model produced a result (a stub run says plainly that no model was called and nothing is
extracted); the panel shows the outcome of each run for the document (status, provider/model, pages
read, tokens, USD, cache hit, time, warnings/failures) and the validated model answer (category, tags,
identities with quote) plus a bounded view of the raw model reply; misconfiguration of the live provider
is visible instead of silent.

## 2. Scope

### IN

1. **Inline delete (UI):** the project row shows the name and the delete icon button on one line
   (icon button with accessible name "Delete project <name>", visible focus, no overlap with long names:
   name truncates with ellipsis, button never shrinks).
2. **Re-process:** every PDF/model-processable document shows an action to process again whatever its
   state (never processed, processed, failed, no identity). It always goes through estimate -> confirm.
   Re-process **bypasses the result cache by default** (a deliberate fresh read; the estimate shows the real
   cost) and the dialog offers "Reuse the stored result if the document is unchanged (no model call)" as an
   explicit opt-in. The backend request carries `force` (bool, default false at the API; the UI sets it for
   documents that already have a result). A forced re-read stores a new result row; the latest by time is
   the current model read; earlier results remain in the history (project-scoped, purged with the project).
3. **Outcome visibility:** per document, the Model processing panel lists the document's processing runs
   newest first with: state, provider (stub or meta) and model, started/finished time, pages read, input and
   output tokens, USD actual, cache hit, failure code/message or warnings. The current result shows
   category, tags, identities with page+quote (already in 0.36.0) and, new, a collapsible bounded
   "Model reply (raw)" (first 8 KiB of the provider's text as stored; labeled untrusted data, rendered as
   plain text, never as HTML). The raw reply is stored on the result row (new nullable column,
   migration 0017) with the prompt/schema version and the page range read.
4. **Stub honesty:** when a run used the stub provider, the run line and the panel say "Stub provider: no
   model was called and no data is extracted. Set FIELDLENS_PROCESSING_PROVIDER=meta to use the live model."
   (no "Processed" success styling for a stub that extracted nothing: use a neutral "Stub run" state).
   The estimate dialog names the provider and model and states whether the run will spend money.
5. **Configuration visibility:** `GET` readiness/settings summary (an existing readiness or processing
   endpoint field, e.g. `processing_provider` info) tells the UI which provider is active and, if `meta`
   is requested but incomplete, why (missing key / rates / cap) without secret values. Startup logs one
   warning per unprefixed `PROCESSING_*`, `META_*` setting found in `.env` that will be ignored, naming the
   prefixed name to use. `scripts/init_env.py` and `.env.example` document the prefixed processing keys
   (`FIELDLENS_PROCESSING_PROVIDER`, `FIELDLENS_PROCESSING_RUN_CAP_USD`,
   `FIELDLENS_PROCESSING_META_INPUT_USD_PER_MTOK`, `FIELDLENS_PROCESSING_META_OUTPUT_USD_PER_MTOK`,
   `FIELDLENS_PROCESSING_MODEL_PAGES`) with no secret values. `init_env.py` must not overwrite existing
   values and must not print secrets.

### OUT

New extraction fields, OCR, auto-accepting proposals, changing budget policy, a settings editor UI, any live
Meta call in default tests, storing full page text.

## 3. Acceptance Criteria

| ID | Type | Given / when / then | Test |
|---|---|---|---|
| AC-1 | UI | Project row: name and delete icon share one line at 1280 and 390 px, long name truncates, button reachable by keyboard with the accessible name, no axe violations. | Vitest + Playwright |
| AC-2 | Behavioral | A document with a stored model read can be re-processed: the action exists in processed, failed and no-identity states; it opens estimate -> confirm; a forced run calls the provider again (stub-counting provider) and stores a new result row; the older row stays in history. | backend + UI test |
| AC-3 | Behavioral | `force=false` with unchanged inputs reuses the stored result with zero provider calls (existing AC-8 of TASK-055 unchanged); the dialog opt-in sends `force=false`. | backend test |
| AC-4 | Behavioral | The document panel shows the run history with provider/model, pages, tokens, USD, cache hit, time and failure/warnings; the raw reply is collapsed by default, plain text, bounded to 8 KiB with a truncation note, and escaped (hostile HTML in a reply renders as text). | Vitest |
| AC-5 | Behavioral | Stub run: the panel reads "Stub run" with the no-model/no-data text and the prefixed setting name; it is not styled as a successful extraction. | Vitest + backend |
| AC-6 | Config | `meta` requested but key/rates/cap missing: readiness/processing info reports `provider_misconfigured` with the missing item names (no values); the app still starts on the stub and says so (decision: fail-open to the stub with a visible warning, so the app stays usable). Process requests in that state are refused with a typed 409 `provider_misconfigured`, never silently run on the stub. | backend test |
| AC-7 | Config | An unprefixed `PROCESSING_PROVIDER` in `.env` yields one startup warning naming `FIELDLENS_PROCESSING_PROVIDER`; no secret values are logged. | backend test |
| AC-8 | Persistence | Migration 0017 upgrade/downgrade round trip; new column and any new table covered by project purge and its completeness test; head assertions updated. | migration + purge tests |
| AC-9 | Security | Raw reply and warnings are stored/rendered as data; no HTML injection; the document text is not copied into logs. | tests |

## 4. Decisions

- Re-process = forced fresh read by default: the owner's complaint was a no-op re-process.
- Explicit stub state instead of "Processed" so a no-model run cannot be mistaken for a real result.
- `meta` requested but incomplete is refused at request time (409), not silently stubbed.
- Raw reply stored (bounded) for observability; it is model output, untrusted, local only.

## 5. Failure Conditions

Misconfigured live provider silently running as stub; a forced re-read spending without a confirmed
estimate; the raw reply rendered as HTML; history lost on re-process.

## 6. Ambiguity Audit

Meta token rates are owner-supplied (not in the repo); the live provider cannot be used until they are set.
Not a blocker for this slice (stub-verified); recorded in the handoff.

## 7. Amendment (TASK-074): live processing needs no owner step

Cause of a live run failing as `provider_error: provider_unavailable`: the `processing-live` ledger
period had no confirmed starting balance, so `BudgetLedger.reserve` refused before any call, and the
reason was dropped from the failure text and never logged.

- At startup with a complete `meta` configuration the runtime makes that one period usable: after
  `ensure_period` it confirms the starting balance equal to the ledger cap
  (`FIELDLENS_BUDGET_LEDGER_CAP_USD`, default 150) with source "auto: processing-live, per-run user
  confirmation", also repairing an existing period whose balance is unset. An already confirmed
  balance is never changed; other periods (equipment/assistant) keep their explicit confirmation.
  The ledger still records every reservation and commit; the user's confirmation of the estimate is
  the spend authorisation. A paused period still blocks.
- `FIELDLENS_PROCESSING_RUN_CAP_USD` is optional (blank = no per-run cap); it is no longer required for
  `meta`. Remaining ceilings: `FIELDLENS_PROCESSING_TOTAL_CAP_USD` (default 5, <= 5, shared),
  `FIELDLENS_PROVIDER_MAX_RESERVED_USD` (per call, <= 0.50), the ledger cap, and the confirmed estimate.
- A failed document shows the safe ledger reason in `failure_message` (e.g. "provider error:
  provider_unavailable: the live processing budget period is paused ...") and the runner logs one
  warning per failed document: `run_id`, `document_id`, code and reason; never document text or a key.

