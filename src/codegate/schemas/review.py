"""ReviewFinding — a single issue found during contract-vs-implementation audit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewFinding(BaseModel):
    """A single finding from the Review Gate.

    Each finding traces back to a specific contract clause,
    enabling "contract drift audit" — the core differentiator of CodeGate.
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
        description="P0 = blocking (must fix before approval), "
        "P1 = significant (should fix), "
        "P2 = minor (nice to fix).",
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
        description="If True, this finding must be resolved before approval.",
    )
    suggestion: str = Field(
        default="",
        description="Suggested fix or improvement.",
    )
