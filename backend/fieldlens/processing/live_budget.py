"""Safe wording for ledger refusals of the live processing step (TASK-074).

A failed run must say why. Texts carry no secret and no document text.
"""

from __future__ import annotations

UNCONFIRMED_REASON = "starting balance is not confirmed"
PAUSED_REASON = "budget is paused"
PRICING_REASON = "pricing revision is not recorded"

# Reason (as raised by the ledger) -> plain explanation. Failure messages are stored in 400 chars.
REASON_HINTS = {
    UNCONFIRMED_REASON: (
        "the budget period has no starting balance (the live processing period sets it "
        "automatically when the app starts; restart the app)"
    ),
    PAUSED_REASON: "the live processing budget period is paused; resume it before processing",
    PRICING_REASON: "the live pricing revision is not recorded; restart the app to register it",
}


def failure_text(code: str, reason: str | None) -> str:
    """Safe, actionable failure text for an assistant error with an optional ledger reason."""
    if not reason:
        return f"provider error: {code}"
    return f"provider error: {code}: {REASON_HINTS.get(reason, reason)}"[:400]
