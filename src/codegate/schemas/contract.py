"""ImplementationContract — the approved specification that executors must follow.

This is the single most important artifact in the system.
It is executor-agnostic: any developer (human or AI) should be able
to read it and know exactly what to build without further questions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    """A single verifiable acceptance criterion.

    Each criterion must be specific enough that you can write a test for it.
    Bad:  "用户能正常使用"
    Good: "POST /api/users 传入 {name, email} 返回 201 + user_id"
    """

    description: str = Field(
        ...,
        description="What must be true for this criterion to pass.",
    )
    verification: str = Field(
        ...,
        description="How to verify this criterion. "
        "Example: 'curl POST /api/users → expect 201'",
    )
    priority: Literal["must", "should", "nice_to_have"] = Field(
        default="must",
        description="Priority level. 'must' items block approval if not met.",
    )


class Risk(BaseModel):
    """An identified risk with mitigation strategy."""

    description: str
    probability: Literal["low", "medium", "high"] = "medium"
    impact: Literal["low", "medium", "high"] = "medium"
    mitigation: str = Field(
        ...,
        description="How to mitigate this risk. Must be actionable.",
    )


class AssumedDefault(BaseModel):
    """A decision that was auto-filled by the system, not explicitly confirmed by the user.

    These are tracked separately so the Review Gate can flag
    implementations that rely heavily on assumptions.
    """

    topic: str  # e.g., "deletion_strategy"
    assumed_value: str  # e.g., "soft_delete"
    reason: str  # e.g., "用户未指定，系统默认使用软删除以支持恢复"


class ImplementationContract(BaseModel):
    """The approved contract that defines what must be built.

    This document is executor-agnostic. It describes WHAT to build,
    not HOW to tell a specific agent to build it. The adapter layer
    handles translation to executor-specific formats.
    """

    work_item_id: str

    # === Core specification ===
    goals: list[str] = Field(
        ...,
        min_length=1,
        description="Specific, verifiable goals. "
        "Each goal must be concrete enough to test. "
        "❌ '提高系统性能' → ✅ '将 /api/users P99 从 500ms 降到 200ms'",
    )
    non_goals: list[str] = Field(
        ...,
        min_length=1,
        description="Explicitly out-of-scope items. "
        "This is critical — it prevents the executor from over-building. "
        "Example: ['不做前端页面', '不做用户注册/登录流程']",
    )

    # === Verification ===
    acceptance_criteria: list[AcceptanceCriterion] = Field(
        ...,
        min_length=1,
        description="Verifiable conditions for approval.",
    )
    required_tests: list[str] = Field(
        default_factory=list,
        description="Tests that must pass. "
        "Example: ['test_create_user', 'test_delete_user_soft']",
    )

    # === Constraints & risks ===
    constraints: list[str] = Field(
        default_factory=list,
        description="Technical constraints. "
        "Example: ['使用现有 FastAPI 框架', '不引入新 ORM']",
    )
    risks: list[Risk] = Field(
        default_factory=list,
        description="Identified risks with mitigation plans.",
    )
    rollback_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions under which the change should be rolled back.",
    )

    # === Metadata ===
    assumed_defaults: list[AssumedDefault] = Field(
        default_factory=list,
        description="Decisions auto-filled by Spec Council, not confirmed by user. "
        "Tracked for transparency and audit.",
    )
    approval_status: Literal["pending", "approved", "rejected"] = "pending"
    approved_at: datetime | None = None
    version: int = 1
    clarification_rounds: int = Field(
        default=0,
        description="How many rounds of clarification occurred before approval.",
    )

    def approve(self) -> None:
        """Mark this contract as approved."""
        self.approval_status = "approved"
        self.approved_at = datetime.now(timezone.utc)

    def reject(self) -> None:
        """Mark this contract as rejected (needs revision)."""
        self.approval_status = "rejected"
        self.version += 1
