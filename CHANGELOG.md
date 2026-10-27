# Changelog

Human-readable changes by integration version. Versions use major.minor.patch:
breaking changes increment major, features minor, fixes/documentation patch.
See the [workflow](docs/DEVELOPMENT_WORKFLOW.md) for classification and merge rules.

## Unreleased

**Bootstrap candidate: 0.1.0**, matching [VERSION](VERSION). This initializes
version tracking for a documentation-only repository; it is not an application
release or Git tag. The orchestrator will date this section at first integration.
Subsequent accepted changes receive an assessed bump; no retroactive versions
are assigned to the earlier unversioned commits below.

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
  No application feature tests, worktree-agent execution, commit, merge, push,
  release or tag are claimed by this pending entry.

## Pre-versioning history

These entries describe existing commits, not historical numbered releases.

- **2026-10-27, `2772cff`:** Design/reference assets, curated development skills
  and supporting documentation.
- **2026-10-26, `695da46`:** Initial project structure, requirements and technical
  documentation.
