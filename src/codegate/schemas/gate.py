"""GateDecision — the final programmatic approve/revise/escalate decision."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from codegate.schemas.review import ReviewFinding


class GateDecision(BaseModel):
    """The gatekeeper's final decision on whether to approve the implementation.

    This is a PROGRAMMATIC decision, not advisory. If the decision is
    'revise_code' or 'escalate_to_human', the implementation CANNOT proceed.
    """

    work_item_id: str

    # === Decision ===
    decision: Literal["approve", "revise_spec", "revise_code", "escalate_to_human"] = Field(
        ...,
        description="The gate decision. "
        "'approve' = implementation passes all gates. "
        "'revise_spec' = contract itself needs changes. "
        "'revise_code' = implementation needs changes. "
        "'escalate_to_human' = too risky for automated decision.",
    )

    # === Evidence ===
    blocking_findings: list[ReviewFinding] = Field(
        default_factory=list,
        description="Findings that block approval.",
    )
    all_findings_count: int = Field(
        default=0,
        description="Total number of findings (blocking + non-blocking).",
    )

    # === Scores ===
    drift_score: int = Field(
        default=0,
        ge=0,
        le=100,
        description="0-100. How much the implementation drifts from the contract. "
        "0 = perfect alignment, 100 = completely off-track.",
    )
    coverage_score: int = Field(
        default=0,
        ge=0,
        le=100,
        description="0-100. How many contract goals/criteria are addressed. "
        "100 = all addressed, 0 = none addressed.",
    )

    # === Reasoning ===
    summary: str = Field(
        default="",
        description="Human-readable summary of the decision rationale.",
    )
    requires_human: bool = Field(
        default=False,
        description="True if this decision should be reviewed by a human.",
    )
    next_action: str = Field(
        default="",
        description="What should happen next. "
        "Example: 'Fix the missing soft-delete logic and resubmit.'",
    )

    # === Metadata ===
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    iteration: int = Field(
        default=1,
        description="Which iteration of review this is (1 = first attempt).",
    )
