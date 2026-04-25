"""ReviewFinding — a single issue found during contract-vs-implementation audit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewFinding(BaseModel):
    """A single finding from the Review Gate.

    Each finding traces back to a specific contract clause,
    enabling "contract drift audit" — the core differentiator of CodeGate.

    Uses a two-dimensional classification:
      - severity: impact level (P0 = critical, P1 = significant, P2 = minor)
      - disposition: gate action (blocking = must fix, advisory = should fix, info = FYI)

    This avoids the confusing "P1 non-blocking" anti-pattern. Instead:
      - P0 blocking = constraint violated, must fix
      - P1 advisory = significant drift, should fix but doesn't block approval
      - P2 info     = minor style issue, FYI only
    """

    category: Literal["correctness", "drift", "security", "maintainability", "completeness"] = (
        Field(
            ...,
            description="Type of issue found. "
            "'drift' = implementation deviates from approved contract. "
            "'completeness' = contract goal not addressed.",
        )
    )
    severity: Literal["P0", "P1", "P2"] = Field(
        ...,
        description="Impact level. "
        "P0 = critical (constraint violated, security vulnerability), "
        "P1 = significant (goal partially met, silent behavioral change), "
        "P2 = minor (style, optimization).",
    )
    disposition: Literal["blocking", "advisory", "info"] = Field(
        default="advisory",
        description="Gate action. "
        "'blocking' = must fix before approval. "
        "'advisory' = should fix, but doesn't block approval. "
        "'info' = informational only.",
    )
    message: str = Field(
        ...,
        description="Clear description of the issue.",
    )
    contract_clause_ref: str = Field(
        default="",
        description="Which contract goal/criterion this finding relates to. "
        "Example: 'goal[0]', 'acceptance_criteria[2]', 'non_goals[1]'",
    )
    code_location: str = Field(
        default="",
        description="Where in the code this issue was found. "
        "Example: 'user_router.py:L45', 'models/user.py'",
    )
    blocking: bool = Field(
        default=False,
        description="Derived convenience field. True when disposition == 'blocking'.",
    )
    suggestion: str = Field(
        default="",
        description="Suggested fix or improvement.",
    )

    def model_post_init(self, __context) -> None:
        """Sync blocking flag from disposition for backward compatibility."""
        if self.disposition == "blocking":
            object.__setattr__(self, "blocking", True)
        elif not self.blocking:
            # If blocking was explicitly set to True by caller, respect it
            # and upgrade disposition accordingly
            pass
        if self.blocking and self.disposition != "blocking":
            object.__setattr__(self, "disposition", "blocking")

