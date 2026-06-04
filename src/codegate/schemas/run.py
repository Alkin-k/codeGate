"""Run identity & artifact bundle schemas for the Governance Contract Runtime.

v0.7 gives every governance run a stable ``run_id`` (distinct from the
work_item id) so that re-running the same work item no longer overwrites prior
evidence. RunMetadata stamps the immutable identity of a run; RunArtifactBundle
is the in-memory result of loading a run back from disk for replay/inspection.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from codegate.schemas.verdict import GovernanceVerdict


def generate_run_id(work_item_id: str | None = None) -> str:
    """Generate a unique, sortable run id: ``run_YYYYMMDD_HHMMSS_<shortid>_<rand>``.

    The leading timestamp keeps ids sortable; the work-item-derived ``shortid``
    aids traceability; and the trailing random suffix guarantees uniqueness even
    when the same work item is saved multiple times within the same second.

    The run id is intentionally NOT equal to the work_item id so that multiple
    runs of the same work item are distinct, non-overwriting records.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    shortid = (work_item_id or uuid.uuid4().hex)[:6]
    rand = uuid.uuid4().hex[:6]
    return f"run_{ts}_{shortid}_{rand}"


class RunMetadata(BaseModel):
    """Immutable identity & context of a single governance run."""

    run_id: str
    work_item_id: str
    codegate_version: str = "0.0.0"
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None
    project_dir: Optional[str] = None
    executor_name: Optional[str] = None
    sandbox_strategy: Optional[str] = None
    git_base_ref: Optional[str] = None
    git_head_ref: Optional[str] = None
    status: Literal["running", "completed", "failed", "cancelled"] = "completed"


class RunArtifactBundle(BaseModel):
    """In-memory view of a run loaded back from disk (replay-lite).

    Holds the parsed metadata/verdict plus the completeness report so callers
    can inspect or replay a run without re-invoking any LLM or executor.
    """

    run_id: str
    run_dir: str
    metadata: Optional[RunMetadata] = None
    verdict: Optional[GovernanceVerdict] = None
    manifest: Optional[dict] = None
    summary: Optional[dict] = None
    review_history: List[dict] = Field(default_factory=list)
    policy_result: Optional[dict] = None
    present: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    completeness_score: float = 0.0
