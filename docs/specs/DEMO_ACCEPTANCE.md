# Specification: Fresh-import verification and three-minute demo delivery

> **Spec type:** Process/workflow. **Backlog:** FL-012.
> **Load-bearing frameworks:** F3, F4, F6. **Supporting:** F1, F2, F5.
> **Date:** 2026-10-28. **Decision owner:** project owner.
> **Status:** Selected cohort/fallback/review workflow confirmed; no application/rehearsal/submission verified.
> **Zero-Question Score:** 0 unowned design questions; G1/G2/G4/G5 remain live gates.

## How to Read This Spec

Owner: delivery/rights. QA: DM scenarios. Orchestrator: dependencies and checkpoints.
Covers every project AC-1 through AC-12; screenshots alone do not pass.

## Notation Key

`[Validated]` = owner-confirmed requirement; `[Assumed: verify]` = proposed execution
budget/checkpoint. H/M/L are confidence. AC score 3 = reproducible pass/fail.

## 1. Outcome Statement

A clean local installation demonstrates project creation, fresh upload and live
Meta reconstruction/review through evidence-backed scene/history/charts and cited
conversation, and the owner has a compliant
public-code package and recording no longer than three minutes.
Verification: DM-1 through DM-7. Outcome score 3.

## 2. Scope

### IN Scope

Fresh-import end-to-end, real source/Meta gates, performance/failure/accessibility
checks, local startup documentation, release candidate and recording checklist.

### OUT of Scope

Automatic public push/submission, redistribution of unapproved raw data, hosted
multi-user service, synthetic-as-real footage and guaranteed hackathon eligibility
without authenticated rules review.

### Scope Dependencies

FL-012-A integrates offline browser checks after all mandatory feature slices.
FL-012-B requires G1, live source chat FL-011-D, reconstruction FL-016-B and full
exploration FL-011-C. FL-012-C prepares release/recording after
FL-012-B; publication remains an explicit owner action under G4.

### Open Scope Tensions

A short recording may edit waiting time, but must not misrepresent cached data,
mocked answers or import latency as live behavior. Keep raw measured run evidence.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| DM-1 | Behavioral | From empty isolated DB/storage, create a project, upload the accepted manifest, inspect evidence, run reconstruction, review/publish eligible results and navigate wellbore -> equipment -> history -> both charts -> evidence -> cited answer without manual geometry edits; a second project stays isolated. | 3 | [Validated objective and publication policy] | Playwright `fresh-import.spec.ts` |
| DM-2 | Dependency | G1/DF-9, PW/RC, real trajectories/context/charts/history and MI/RG live criteria pass with source/model revisions, hashes and tested commit recorded; mocks are separately labeled. | 3 | [Validated] | acceptance evidence matrix |
| DM-3 | Non-behavioral | Combined scene passes project AC-9 and <=3 GiB aggregate API/DB/worker RSS target; local read p95 <=1 s over 20 requests during import; model latency reported separately. | 3 | [Assumed: verify RSS; existing AC-9] | combined performance run |
| DM-4 | Edge case | Interrupted import, conflicting data, missing history, rapid selection change, provider outage and exhausted budget show specified failure/partial states while preserving prior revisions. DQ-1..8 verify F-12 generic/unlocated equipment and real F-14 reference/F-12 interval discrepancies with blocked affected outputs. | 3 | [Validated: owner October 28] | Playwright `failure-paths.spec.ts`, `quality-issues.spec.ts` |
| DM-5 | Negative | Default suite has zero paid calls; scanned public release files/browser bundle contain no credentials/private data; unsupported generic geometry never appears as measured truth. | 3 | [Validated] | offline/network checks, release inventory review |
| DM-6 | Behavioral | All scene objects have keyboard-accessible selection/evidence paths, focus is visible/restored, dialogs are escapable, chart units/axes and evidence state are text-labeled, reduced motion works at 1280x720 and 1920x1080. | 3 | [Validated UX; assumed viewports] | browser accessibility scenarios |
| DM-7 | Dependency | Owner verifies remaining rules/rights, local startup instructions reproduce the candidate, recording duration <=180 s, and public-code/reuse inventory excludes unapproved originals. No upload/push occurs without permission. | 3 | [Validated] | release/rehearsal checklist |

Definition of done: all criteria pass, integration/version/changelog recorded,
and authorized delivery confirmed. A prepared package is not a published submission.

## 4. Context and Decisions

Executor: `fieldlens-qa` independently verifies stable candidate behavior and
reports defects; feature owners implement fixes. `fieldlens-task` runs known
commands, not repeated independent design reviews. Orchestrator owns release
metadata; owner alone approves publication and any scope change.

Fixture evidence record: tested Git SHA, runtime/lock/image versions, OS/browser/
GPU, source manifest SHA-256, DB/storage isolation, revision IDs, commands,
start/end times, results, live/stub status, usage/balance, frame/API/RSS metrics
and sanitized failure diagnostics. Use a local untracked artifact directory;
commit only source-safe summaries and approved synthetic fixtures.

Planned browser configuration uses one worker and explicit loopback URLs.
Default suite uses synthetic sources plus a deterministic provider stub; a
separate real-data/live profile cannot run without required paths/budget.
Do not mutate the accepted demo DB in failure/destructive migration tests.

Proposed 180-second recording allocation: 20 s problem/project/upload, 40 s
agent reconstruction/evidence/review, 25 s trajectories/installed equipment,
25 s historical intervals, 35 s seabed/formations and both charts, 25 s cited
conversation/tool action, 10 s limitations/source attribution.
If waiting is edited, disclose it and retain
the complete measured run. Do not spend the recording on generic scene animation.
Within the equipment/review/limitations segments, contrast F-14/F-5
source-dimensioned evidence with F-12's labelled generic/unlocated case and open
one real conflict with both citations. Do not add a separate monitoring dashboard
or exceed 180 seconds. This is observability of limitations, not a bypass of G1.

Submission checklist: indie track, public code repository, <=3-minute recording,
Meta use evidenced, third-party licenses/attribution, dataset/code-license separation,
no secrets, reproducible local setup, final rules/deadline confirmation.
Deadline is **2026-11-04 21:00 America/New_York (UTC-05:00)**, not UTC-04:00.

## 5. Failure Conditions

Any mandatory family/live gate fails -> no full-demo acceptance; report exact
failed criteria, keep unaffected work, and seek an owner source/scope decision.
Integration tip changes -> rerun affected integration checks before versioned
release; do not record previous SHA results as current.
Worst misinterpretation: a recorded replay with fabricated data cannot pass DM-1/2.

## 6. Ambiguity Audit

Local delivery is accepted; public hosting is not required. Recording duration,
publication permission and scope/evidence distinctions are explicit.
G4's authenticated rules review is owner-owned before final publication.

## 7. Implementation Guidance

Planned commands: `npm --prefix frontend run test:e2e`, backend/frontend focused
checks and build, plus explicitly authorized live gold run.
Record results and file/line reproducible failures rather than application fixes
in QA's read-only role. Release preparation is main-agent work.
No test/rehearsal/publication result exists yet. Classification follows actual
integrated feature/fix scope; recording-only/docs changes are patch, not a new app.

## Open Tensions

The eight-day schedule is a risk budget, not a promise of source access or quality.
Never hide missing mandatory scope to meet the recording deadline.

## Assumption Registry

G1 can supply complete required evidence (M). Live Meta remains available (M).
Remaining authenticated rules permit the chosen local recording/public-code package
(M; owner confirms G4). All are explicit release gates.

## Adversarial Self-Critique

Warm-cache demos can hide broken imports: require a fresh isolated run.
Feature-only performance can hide combined regressions: measure all layers together.
Public code can accidentally include raw sources: inspect the staged release inventory.

## Revision Triggers

Reopen on failed mandatory real-data acceptance, changed submission rules or a
release-candidate change after final combined/live verification.
