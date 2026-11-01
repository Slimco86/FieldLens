"""Merge proposals: AI-proposed, user-reviewed identity merges (TASK-057, PF-7).

Spec: ``docs/specs/MERGE_PROPOSALS.md``. The deterministic resolver stays the identity authority;
this package only proposes, validates and, after an explicit user decision, records a revertible
merge that the resolver applies."""
