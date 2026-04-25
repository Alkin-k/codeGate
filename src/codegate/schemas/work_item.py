"""WorkItem — the top-level task object that flows through the governance pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    """All possible states in the governance state machine."""

    DRAFT = "draft"
    SPEC_REVIEW = "spec_review"
    SPEC_APPROVED = "spec_approved"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REVISE_SPEC = "revise_spec"
    REVISE_CODE = "revise_code"
    ESCALATED = "escalated"


class WorkItem(BaseModel):
    """A single unit of work entering the governance pipeline.

    This is the root object that carries the user's original request
    and tracks its journey through spec → execute → review → gate.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    raw_request: str = Field(
        ...,
        description="The user's original requirement, as-is. "
        "Example: '给我做一个用户管理页面，包含增删改查'",
    )
    context: str = Field(
        default="",
        description="Project context — tech stack, existing codebase info, etc. "
        "Can be auto-detected from the repo or manually provided.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="User-specified constraints. "
        "Example: ['不要引入新的依赖', '必须兼容 Python 3.11']",
    )
    risk_level: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Estimated risk level. Affects whether Spec Council "
        "does deep questioning or fast-track.",
    )
    status: WorkflowStatus = WorkflowStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def transition_to(self, new_status: WorkflowStatus) -> None:
        """Transition to a new workflow status with timestamp update."""
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
