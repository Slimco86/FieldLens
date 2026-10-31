"""Process-local index health shared by the index runner (writer) and the retrieval service
(reader), so a failed maintenance step is visible in coverage instead of only in a log line."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IndexHealth:
    analyze_error: str | None = None
