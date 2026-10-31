"""Typed, sanitized provider/budget failures.

Messages are fixed or built from non-sensitive facts (codes, counts, amounts). They never carry
prompts, source text, opaque reasoning, request bodies or credentials. ``retryable`` is a
property of the failure class; the runner owns the (single) retry.
"""

from __future__ import annotations

from decimal import Decimal


class AssistantError(Exception):
    """Base class; ``code`` is stable and safe to log or return."""

    code = "assistant_error"
    retryable = False
    chargeable = True
    """Whether an attempt that ended this way may still have been billed by the provider."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class ProviderUnavailable(AssistantError):
    """Missing key, balance or pricing: raised before any dispatch (fail closed)."""

    code = "provider_unavailable"
    chargeable = False

    def __init__(self, reason: str) -> None:
        super().__init__(f"provider unavailable: {reason}")
        self.reason = reason


class BudgetExceeded(AssistantError):
    code = "budget_exceeded"
    chargeable = False

    def __init__(self, requested: Decimal, available: Decimal, reason: str = "ceiling") -> None:
        super().__init__(
            f"budget {reason}: requested USD {requested} exceeds available USD {available}"
        )
        self.requested = requested
        self.available = available
        self.reason = reason


class ReservationStateError(AssistantError):
    code = "reservation_state"
    chargeable = False


class RequestLimitExceeded(AssistantError):
    """An MI-5 bound (attempts, tool calls, deadline, output tokens, reserved cost)."""

    code = "request_limit_exceeded"
    chargeable = False

    def __init__(self, limit: str) -> None:
        super().__init__(f"request limit exceeded: {limit}")
        self.limit = limit


class RequestCancelled(AssistantError):
    """Cooperative cancel. Raised before dispatch (nothing billed) or, with ``settled`` true,
    after an in-flight call completed and its actual usage was recorded (that call is billed)."""

    code = "request_cancelled"
    chargeable = False

    def __init__(self, message: str | None = None, *, settled: bool = False) -> None:
        super().__init__(message)
        self.settled = settled


class ProviderAuthError(AssistantError):
    """401/403: not retried; stop the live slice."""

    code = "provider_auth"
    chargeable = False


class ProviderRateLimited(AssistantError):
    code = "provider_rate_limited"
    retryable = True
    chargeable = False  # a 429 is rejected before processing

    def __init__(self, message: str | None = None, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ProviderServerError(AssistantError):
    code = "provider_server_error"
    retryable = True


class ProviderTimeout(AssistantError):
    """Dispatch may have reached the provider: liability is retained until reconciliation."""

    code = "provider_timeout"


class ProviderConnectionError(AssistantError):
    code = "provider_connection"


class ProviderRefusal(AssistantError):
    code = "provider_refusal"


class ProviderTruncated(AssistantError):
    code = "provider_truncated"


class ProviderMalformed(AssistantError):
    """Bad schema, unknown tool, invalid tool arguments or unparseable output."""

    code = "provider_malformed"


class ProviderRejected(ProviderMalformed):
    """HTTP 4xx refusal before processing (unknown model, no such endpoint): not billed.

    Observed in MI-6: rejected requests do not appear as billed on the provider dashboard.
    """

    code = "provider_rejected"
    chargeable = False


class ReplayMiss(AssistantError):
    """The recorded-replay provider has no recording for this request."""

    code = "replay_miss"
    chargeable = False
