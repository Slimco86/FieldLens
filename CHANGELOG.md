# Changelog

Human-readable changes by integration version. Versions use major.minor.patch:
breaking changes increment major, features minor, fixes/documentation patch.
See the [workflow](docs/DEVELOPMENT_WORKFLOW.md) for classification and merge rules.

## Unreleased

**Candidate: 0.2.0**, matching [VERSION](VERSION), pending integration.
Minor bump: new opt-in development-agent execution capability, not an application
API/schema change or a prose-only correction. No commit, merge or release of this
candidate is claimed.

### Added

- **FL-001:** Main Astra/xhigh orchestrator profile and ten specialist profiles
  for small tasks, frontend, backend, 3D/motion, research, ingestion/OCR, RAG,
  geospatial/engineering, QA and bounded plan repair.
- **FL-001:** Owner-approved Terra/low, Sonnet/medium and Sol/high worker tiers;
  explicit routing, no silent model fallback, no nested worker delegation,
  minimal-context assignments and model/usage verification.
- **FL-001:** Agent registry, shared execution contract, activation guidance and
  approved configuration specification.

### Changed

- Execution guidance and feature handoffs now record role/risk rationale,
  actual model/effort evidence, bounded attempts and exposed usage. Development
  usage is distinct from the shared Meta application budget.
- Reconciled FL-000 and the 0.1.0 baseline against the owner's actual integration
  commit `e8b156a`; this does not retroactively claim an application release.

### Validation

- Static checks passed for 11 YAML profiles/model tiers/tool boundaries, 12 routing
  cases, 143 local references, backlog dependencies and version consistency.
  VS Code reported no agent-file diagnostics; `git diff --check` passed.
- Host profile/model activation remains untested and is a required check before
  real feature delegation; static checks do not prove runtime model selection.
- No application implementation, new worktrees, paid Meta calls or publication.

## 0.1.0 - 2026-10-27

Initial documentation baseline, integrated on `master` by `e8b156a`.
No application release or Git tag is asserted; earlier unversioned commits
remain listed below without invented historical versions.

### Added

- **FL-000:** Development workflow for main-agent planning/orchestration, isolated
  implementation worktrees, dependency-aware parallelism, verification/handoff,
  serialized integration and backlog reconciliation.
- **FL-000:** Persistent backlog, canonical version file, changelog policy, and
  feature-template fields for delegation, compatibility and integration evidence.
- **FL-000 / FL-008:** Historical perforation requirements and a draft feature
  contract for MD/TVD intervals, total/open perforated length, date-specific
  producing/injecting/shut-in states, reperforation, uncertainty and provenance.
  These are requirements, not implemented application capabilities.

### Changed

- **FL-000:** Project, technical, source and developer guidance now account for
  historical perforation state and selected-time/revision consistency.
- **FL-000:** Clarified that the deferred application-runtime multi-agent framework
  does not exclude the required multi-agent development workflow.

### Validation

- Checked 94 local Markdown/HTML references, backlog ID/dependency integrity,
  bootstrap version consistency, all seven synthetic state/length examples and
  ft/m round trips. Skill metadata matches the previously validated baseline;
  `git diff --check` passed.
  No application feature tests, worktree-agent execution, push, release or tag
  were performed by the documentation task. Integration was subsequently confirmed
  from Git history.

## Pre-versioning history

These entries describe existing commits, not historical numbered releases.

- **2026-10-27, `2772cff`:** Design/reference assets, curated development skills
  and supporting documentation.
- **2026-10-26, `695da46`:** Initial project structure, requirements and technical
  documentation.
