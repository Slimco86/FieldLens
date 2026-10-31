# MI-6 live Meta smoke evidence (TASK-005)

Date: 2026-10-31 (America/New_York morning, lane `task-005-live-meta-smoke`, base 8ad8dfc).
Class: **live** (real `https://api.meta.ai/v1` through the TASK-004 adapter), synthetic prompts only.
No keys, headers, field documents or opaque reasoning are recorded here. Reproduce with
`MODEL_API_KEY=... FIELDLENS_LIVE_META=1 [FIELDLENS_LIVE_META_PHASE=main|followup|followup2] uv run pytest backend/tests/assistant/test_meta_live_smoke.py -m live_meta`
(opt-in marker plus env var; refusal path proven offline by `test_meta_live_gate.py`).
The raw sanitized JSON stays in the lane (`.local/fieldlens/live_meta_*.json`, gitignored).

## Spend

Ceiling USD 1.00, enforced by a dedicated ledger period (`mi6-live-smoke`, cap and confirmed
balance 1.00) in the lane database; every call went through `WorkUnit` reservations
(USD 0.50) or a small manual reservation (embeddings probe, effort probes).

- Provider responses: 13 (2,630 input tokens, 9,169 output tokens of which almost all reasoning).
  Plus two rejected requests (404 unknown model, 404 embeddings) and one free `GET /models`.
- **Provider rates are not exposed by the API and are not recorded anywhere in the repo.** The
  ledger used the deliberately high placeholder `mi6-conservative-placeholder-1` (USD 5 per Mtok
  input, 25 per Mtok output, no cached discount). Estimated spend is therefore an **upper bound**:
  **USD 0.242375 settled + USD 0.025645 liable (the 404 probe, billed unknown) = USD 0.268020**
  of the USD 1.00 ceiling (USD 0.731980 uncommitted). The owner must read the real balance delta
  from the provider dashboard to reconcile; the usage objects carry no cost field.
- No retries occurred (1 attempt per work unit; the tool loop used 2 steps and 1 tool call).

## Results by item

1. **Model/mode/protocol/text.** `muse-spark-1.3` accepted on the Responses API, response `model`
   `muse-spark-1.3`, plain text `pong` (16 in / 175 out tokens, 1.8 s). `GET /models` lists:
   muse-image-1.0, muse-spark-1.1, 1.2, 1.2-contributor, 1.3, 1.3-contributor,
   muse-voice-transcribe-1.0, muse-wonder-1.0, sam-3.1. Standard mode is the non-`-contributor`
   id; the response exposes no `mode` (`reasoning.mode` null), so Standard is confirmed only by
   the model id used. **The default reasoning effort is `high`** and reasoning tokens count
   against `max_output_tokens`.
2. **Tool round trip.** Works: call (`function_call`), result (`function_call_output`), final
   answer containing the tool result; 2 steps, 1 tool call, 4.4 s. The API returns opaque
   `encrypted_content` reasoning items by default even with `store: false`; the adapter parsed
   and replayed 2 reasoning items and the provider accepted them. Typed `ProviderMalformed`
   handling was not triggered.
3. **Cancellation / error.** (a) Cancel fired 0.2 s into a call: the adapter raised
   `RequestCancelled` after the response arrived (the in-flight request is not aborted); the
   response was fully billed (19 in / 757 out), recorded as settled usage. (b) Unknown model id:
   HTTP 404 -> `ProviderMalformed("provider rejected the request (404)")`, not retried, 0.09 s;
   the reservation stays `liable` at its estimate because the adapter treats 4xx as possibly
   chargeable (needs `reconcile`). (c) Output exhausted by reasoning surfaced as the typed
   `ProviderTruncated` (status `incomplete`).
4. **Image input.** A stdlib-generated grayscale PNG with block digits `7305` was read
   correctly at 136x56 px (answer `7305`, effort high) and at 272x112 and 408x168 px with
   `reasoning.effort=minimal`. At 680x280 px the model produced **no answer**: reasoning consumed
   the whole output allowance at effort high with 1,024 tokens, at effort high with 4,096
   (4,094 reasoning tokens, 18.7 s, USD 0.104 placeholder) and at effort minimal with 1,024. A
   text-only control with the same prompt also truncated at effort high/1,024 once, so reasoning
   run-away at high effort is not image-specific, but large images were the only case failing
   even at minimal effort (one sample; unresolved). Image input tokens (usage minus 21-token
   text baseline): 12 (136x56), 42 (272x112), 92 (408x168), 242 (680x280); this fits
   about `round(w/28) * round(h/28) + 2`. Versus `provider_image_token_bound` 8192: the bound
   is very conservative for page-sized images (about 1,300x1,300 px would be 2,200 tokens).
   The bound was not validated above 680x280 px; FL-022 must measure a real page-size image
   with synthetic content before relying on it.
5. **Embeddings.** `POST /embeddings` with model `muse-spark-1.3`: HTTP 404, `NotFoundError`,
   empty body. No embedding model in `GET /models`. Conclusion for this key: **no embeddings
   endpoint**; local embeddings stay the plan (only one model id was probed).
6. **Usage/cost versus assumptions** (see below).

## Assumption corrections

| Assumption | Finding |
| --- | --- |
| Default reasoning is small; 4,096 output tokens suffices | Default effort `high` spends 170-4,094 reasoning tokens on trivial prompts; the 1,024 limit truncated 2 of 7 effort-high calls (text-only control and 680x280 image). The adapter cannot set `reasoning.effort`. API accepts `low` (172 reasoning tokens for `pong`) and `minimal` (14). Proposed: expose effort in `ProviderRequest`/payload (not done here; adapter change is outside this slice). |
| Estimate = 1 token per UTF-8 byte (text + tool JSON) is an upper bound | **Wrong for tools:** one 245-token estimate versus 552 billed input tokens (2.3x under) for a one-tool request; the second step billed 992. Text-only was safe (44 estimated, 16 actual). Provider adds hidden tool/system tokens (about 500). The reserved-cost bound can be exceeded by input underestimation; needs a per-tool overhead allowance (finding for the adapter owner). |
| `provider_image_token_bound` 8192 | Safe for measured sizes up to 680x280 (<= 242 tokens); unvalidated for page-size images. |
| SDK/provider cancel stops billing | Cancel is only checked before dispatch and after the answer; an in-flight request completes and bills. |
| Pricing revision known | No rates in repo or API; conservative placeholder used; real balance reconciliation is an owner action. |
| Cached input tokens usually 0 | Provider reported `cached_tokens` 113 (tool step) and 227 (repeat image prompt); actual cost is overstated by the placeholder (no cached discount). `cache_write_tokens` null. |
| MI-5 limits (<=4 attempts, <=6 tool calls, <=90 s, <=4,096 output, USD 0.50) | All respected; longest call 18.7 s, max 2 attempts in one unit, one tool call. USD 0.50 reservation far above single-call upper bounds (<= USD 0.11 placeholder). |
| Responses `incomplete` for truncation | Confirmed (`status: incomplete`, only a reasoning output item). |

Provider response top-level keys include `prompt_cache_*`, `tool_usage`, `access_programs`,
`moderation` (names only). No `cost`/billing field.

## Not covered

No web search tool, no Contributor ids, no streaming, no multi-image requests, no
page-size image, no rate-limit (429) or auth-failure case (the key was accepted), no
reasoning-replay rejection case, only one embeddings model name tried.

## Independent QA note (orchestrator, October 31)

The figures above describe the implementer's original run (request keys `mi6-1793467*`: 13 responses,
2,630 input / 9,169 output tokens, upper bound USD 0.268 at the placeholder rates). During independent QA a
second full live run happened by accident (the shell had `MODEL_API_KEY` inherited and the QA agent set the
opt-in): 7 responses, 2,054 input / 4,504 output tokens, about USD 0.123 settled plus 0.026 liable at the same
placeholder rates, under request keys `mi6-1793468188-*`. The lane ledger period `mi6-live-smoke` therefore holds
both runs (about USD 0.42 combined upper bound, under the USD 1.00 ceiling, which the ledger enforced). The QA
run overwrote the gitignored raw capture `live_meta_main_result.json`; the original run is verified from the
ledger rows. Real provider rates and balance are still unknown; the owner reconciles from the provider dashboard.

## Follow-up (TASK-043, offline)

The adapter changes derived from these findings (effort control, tool-aware input bound, explicit
cancel settlement, non-billable 4xx, reconcile helpers) are described in
`docs/specs/META_INTEGRATION.md`. They are verified with stub/fixture payloads only; the 4xx
non-billing rests on the owner's dashboard observation (billed requests equal the successful
responses), and none of it has been re-run live.

| Assumption | Status |
| --- | --- |
| 4xx rejections are not billed | `[Assumed: only 404 observed live; 405 by analogy]`. Only 404 (unknown model, embeddings) was observed; the adapter treats 404/405 as non-billable and keeps 400/413/422 and other 4xx liable until observed. |
