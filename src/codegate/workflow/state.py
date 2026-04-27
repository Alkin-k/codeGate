"""Global state definition for the LangGraph governance workflow."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from codegate.schemas.work_item import WorkItem, WorkflowStatus
from codegate.schemas.contract import ImplementationContract
from codegate.schemas.execution import ExecutionReport
from codegate.schemas.review import ReviewFinding
from codegate.schemas.gate import GateDecision


class GovernanceState(BaseModel):
    """The shared state that flows through all nodes in the governance pipeline.

    This is the single source of truth for the entire workflow.
    Each node reads from and writes to this state.

    Note: Uses Optional[] instead of X | None for LangGraph compatibility
    with Python 3.9 (LangGraph calls get_type_hints which doesn't
    respect `from __future__ import annotations`).
    """

    # === Input ===
    work_item: WorkItem

    # === Spec Council outputs ===
    clarification_questions: List[str] = Field(default_factory=list)
    clarification_answers: List[str] = Field(default_factory=list)
    clarification_round: int = 0
    clarification_mode: str = "none"  # "none" | "interactive" | "pre_provided"
    contract: Optional[ImplementationContract] = None

    # === Executor outputs ===
    execution_report: Optional[ExecutionReport] = None

    # === Review outputs ===
    review_findings: List[ReviewFinding] = Field(default_factory=list)

    # === Audit evidence (structural pre-check pipeline) ===
    structural_diff: Optional[Dict] = None        # Serialized BaselineDiffResult
    raw_review_findings: List[ReviewFinding] = Field(default_factory=list)  # LLM output before post-filter
    suppressed_findings: List[Dict] = Field(default_factory=list)  # Post-filtered with reasons

    # === Gate outputs ===
    gate_decision: Optional[GateDecision] = None

    # === Iteration history (for per-iteration evidence) ===
    iteration_history: List[Dict] = Field(default_factory=list)

    # === Policy Engine results (for evidence) ===
    policy_violations: List[str] = Field(default_factory=list)
    policy_result: Optional[Dict] = None  # Structured policy result for artifact persistence

    # === Control flow ===
    current_phase: WorkflowStatus = WorkflowStatus.DRAFT
    iteration: int = 1
    max_iterations: int = 3
    error: Optional[str] = None

    # === Metrics (for benchmark) ===
    total_tokens: int = 0
    phase_tokens: Dict[str, int] = Field(default_factory=dict)
    phase_timings: Dict[str, float] = Field(default_factory=dict)

    # === Reviewer scores (passed between nodes) ===
    review_drift_score: int = 50
    review_coverage_score: int = 50

    def add_tokens(self, phase: str, tokens: int) -> None:
        """Track token usage per phase for cost analysis."""
        self.total_tokens += tokens
        self.phase_tokens[phase] = self.phase_tokens.get(phase, 0) + tokens

    def add_timing(self, phase: str, seconds: float) -> None:
        """Track wall-clock time per phase for overhead analysis."""
        self.phase_timings[phase] = self.phase_timings.get(phase, 0) + seconds
