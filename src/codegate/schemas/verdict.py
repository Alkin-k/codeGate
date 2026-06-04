"""GovernanceVerdict — the single machine-readable final verdict for a run.

v0.7 introduces this schema so downstream consumers (CLI, future dashboards,
audit tooling) no longer need to stitch together gate_decision.json +
summary.json + policy_result.json by hand. One verdict.json per run captures
the final decision plus relative pointers to all supporting evidence.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class VerdictEvidence(BaseModel):
    """Relative-path-or-None pointers to the evidence backing a verdict.

    All values are paths relative to the run directory (or None when the
    artifact was not produced), mirroring the all-relative discipline of
    run_manifest.json so the bundle stays valid after being moved/archived.
    """

    manifest: Optional[str] = None
    contract: Optional[str] = None
    sandbox_report: Optional[str] = None
    candidate_diff: Optional[str] = None
    review_history: Optional[str] = None
    gate_decision: Optional[str] = None
    policy_result: Optional[str] = None


class GovernanceVerdict(BaseModel):
    """The final, machine-readable verdict produced by a governance run."""

    run_id: str
    work_item_id: str

    # === Decision ===
    final_decision: Optional[str] = Field(
        default=None,
        description="The gate decision: approve | revise_spec | revise_code | "
        "escalate_to_human. None if the run produced no gate decision.",
    )
    final_status: Optional[str] = Field(
        default=None,
        description="The terminal WorkflowStatus value for the work item.",
    )
    approved: bool = False
    requires_human: bool = False
    risk_level: str = "medium"

    # === Execution context ===
    executor_name: Optional[str] = None
    sandbox_enabled: bool = False
    sandbox_strategy: Optional[str] = None

    # === Quantitative summary ===
    changed_files_count: int = 0
    blocking_findings_count: int = 0
    policy_violations_count: int = 0
    completed_iterations: int = 0

    # === Evidence + reasoning ===
    evidence: VerdictEvidence = Field(default_factory=VerdictEvidence)
    reasons: List[str] = Field(default_factory=list)
    next_action: Optional[str] = None
