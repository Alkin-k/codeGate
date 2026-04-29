"""LangGraph workflow — the governance state machine.

Defines the 5-node pipeline:
  spec_council → executor → reviewer → gatekeeper → policy_check

With conditional routing for revisions and escalation.
The policy_check node runs the deterministic Policy Engine (Rule 1-11
+ SEC-1~5) and can override the gatekeeper's decision. If the policy
overrides to revise_code and iterations remain, the loop continues
back to the executor with policy violations included in feedback.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from langgraph.graph import StateGraph, START, END

from codegate.agents.spec_council import run_spec_council
from codegate.agents.executor import run_executor
from codegate.agents.reviewer import run_reviewer
from codegate.agents.gatekeeper import run_gatekeeper
from codegate.schemas.work_item import WorkflowStatus
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


def _timed_node(phase_name: str, node_fn):
    """Wrap a node function with wall-clock timing instrumentation.

    Records actual elapsed time into state.phase_timings[phase_name].
    This gives the benchmark real measurements instead of token-ratio estimates.
    """
    def wrapper(state: GovernanceState) -> GovernanceState:
        start = time.time()
        result = node_fn(state)
        elapsed = time.time() - start
        result.add_timing(phase_name, elapsed)
        return result
    wrapper.__name__ = node_fn.__name__
    return wrapper


def _route_after_spec(state: GovernanceState) -> str:
    """Route after Spec Council: approved → executor, otherwise ask questions."""
    if state.error:
        return "end"
    if state.work_item.status == WorkflowStatus.SPEC_APPROVED:
        return "executor"
    # Spec needs clarification — handled externally
    return "end"


def run_policy_check(state: GovernanceState) -> GovernanceState:
    """Policy Check node — runs deterministic policy rules after gatekeeper.

    This node applies the Policy Engine (Rule 1-11 + SEC-1~5) which can
    override the gatekeeper's LLM-based decision. The override is written
    into state.gate_decision, state.policy_violations, and state.policy_result
    so downstream routing and artifact persistence see the final decision.
    """
    from codegate.policies.engine import apply_policy_override
    return apply_policy_override(state)


def _route_after_policy(
    state: GovernanceState,
) -> str:
    """Route after Policy Check.

    This is the final routing decision in the governance loop.
    If policy overrides to revise_code and iterations remain,
    the loop sends the state back to the executor with policy
    violations included in the feedback.

    IMPORTANT: Do NOT mutate state here — LangGraph conditional edge
    functions are read-only routers.
    """
    if state.error:
        return "end"

    decision = state.gate_decision
    if decision is None:
        return "end"

    if decision.decision == "approve":
        return "end"
    elif decision.decision == "revise_code" and state.iteration < state.max_iterations:
        # Will re-execute; iteration was already incremented by gatekeeper
        return "executor"
    elif decision.decision == "revise_spec":
        return "end"  # Spec revision handled externally
    else:
        # escalate_to_human or max iterations reached
        return "end"


def build_governance_graph() -> StateGraph:
    """Build the LangGraph state machine for the governance pipeline.

    Flow:
        START → spec_council → executor → reviewer → gatekeeper → policy_check → END
                                  ↑                                     │
                                  └────────── revise_code ──────────────┘

    The policy_check node is the final arbiter. It can override the
    gatekeeper's decision (e.g., approve → revise_code due to Rule 7)
    and route back to the executor with policy violations in feedback.
    """
    graph = StateGraph(GovernanceState)

    # Add nodes with timing instrumentation
    graph.add_node("spec_council", _timed_node("spec_council", run_spec_council))
    graph.add_node("executor", _timed_node("executor", run_executor))
    graph.add_node("reviewer", _timed_node("reviewer", run_reviewer))
    graph.add_node("gatekeeper", _timed_node("gatekeeper", run_gatekeeper))
    graph.add_node("policy_check", _timed_node("policy", run_policy_check))

    # Define edges
    graph.add_edge(START, "spec_council")
    graph.add_conditional_edges(
        "spec_council",
        _route_after_spec,
        {"executor": "executor", "end": END},
    )
    graph.add_edge("executor", "reviewer")
    graph.add_edge("reviewer", "gatekeeper")
    graph.add_edge("gatekeeper", "policy_check")  # Always run policy after gate
    graph.add_conditional_edges(
        "policy_check",
        _route_after_policy,
        {"executor": "executor", "end": END},
    )

    return graph


def create_governance_workflow():
    """Create and compile the governance workflow."""
    graph = build_governance_graph()
    return graph.compile()


def run_governance_pipeline(
    raw_request: str,
    context: str = "",
    constraints: list[str] | None = None,
    clarification_answers: list[str] | None = None,
    clarification_questions: list[str] | None = None,
    clarification_mode: str = "none",
    risk_level: str = "medium",
) -> GovernanceState:
    """Run the full governance pipeline for a given request.

    This is the main entry point for the governance workflow.

    Args:
        raw_request: The user's original requirement
        context: Project context (tech stack, existing code info)
        constraints: User-specified constraints
        clarification_answers: Pre-provided answers to clarification questions.
            If None, the pipeline will stop at spec_review for interactive Q&A.
        clarification_questions: Questions from a prior Spec Council run.
            Must be provided alongside answers for proper Q&A pairing in contract.
        clarification_mode: How answers were collected:
            "none" | "interactive" | "pre_provided".
        risk_level: Task risk level ('low', 'medium', 'high').
            Affects governance depth.

    Returns:
        Final GovernanceState with all artifacts
    """
    from codegate.schemas.work_item import WorkItem

    work_item = WorkItem(
        raw_request=raw_request,
        context=context,
        constraints=constraints or [],
        risk_level=risk_level,
    )

    initial_state = GovernanceState(
        work_item=work_item,
        clarification_answers=clarification_answers or [],
        clarification_questions=clarification_questions or [],
        clarification_mode=clarification_mode,
    )

    workflow = create_governance_workflow()
    final_state = workflow.invoke(initial_state)

    # LangGraph returns a dict — reconstruct GovernanceState with proper
    # Pydantic model deserialization for nested objects.
    if isinstance(final_state, dict):
        final_state = _reconstruct_state(final_state)

    return final_state


def _reconstruct_state(data: dict) -> GovernanceState:
    """Reconstruct GovernanceState from a LangGraph output dict.

    LangGraph serializes Pydantic models to dicts internally. We need
    to rebuild nested objects (contract, execution_report, etc.) properly.
    """
    from codegate.schemas.work_item import WorkItem
    from codegate.schemas.contract import ImplementationContract
    from codegate.schemas.execution import ExecutionReport
    from codegate.schemas.review import ReviewFinding
    from codegate.schemas.gate import GateDecision

    # Rebuild nested Pydantic models from dicts
    if isinstance(data.get("work_item"), dict):
        data["work_item"] = WorkItem(**data["work_item"])

    if isinstance(data.get("contract"), dict):
        data["contract"] = ImplementationContract(**data["contract"])

    if isinstance(data.get("execution_report"), dict):
        data["execution_report"] = ExecutionReport(**data["execution_report"])

    if isinstance(data.get("review_findings"), list):
        data["review_findings"] = [
            ReviewFinding(**f) if isinstance(f, dict) else f
            for f in data["review_findings"]
        ]

    if isinstance(data.get("gate_decision"), dict):
        data["gate_decision"] = GateDecision(**data["gate_decision"])

    return GovernanceState(**data)
