"""Gatekeeper Agent — makes the final programmatic approve/revise/escalate decision."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from codegate.config import get_config
from codegate.llm import call_llm_json, load_prompt
from codegate.schemas.gate import GateDecision
from codegate.schemas.work_item import WorkflowStatus
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


def run_gatekeeper(state: GovernanceState) -> GovernanceState:
    """Run the Gatekeeper node.

    Makes the final decision based on contract, execution report,
    and review findings.
    """
    if state.contract is None or state.execution_report is None:
        state.error = "Cannot gate: missing contract or execution report"
        return state

    config = get_config()
    model = config.models.gate_model
    system_prompt = load_prompt("gatekeeper")

    user_message = _build_gate_prompt(state)

    result, tokens = call_llm_json(
        model=model,
        system_prompt=system_prompt,
        user_message=user_message,
    )
    state.add_tokens("gatekeeper", tokens)

    try:
        decision = _parse_decision(result, state)

        # Capture the current round index BEFORE any increment.
        # This ensures the audit trail shows round 1, 2, 3... naturally.
        round_index = state.iteration

        state.gate_decision = decision

        # Record per-iteration snapshot for audit trail (before increment)
        snapshot = {
            "round": round_index,
            "iteration": round_index,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": decision.decision,
            "drift_score": decision.drift_score,
            "coverage_score": decision.coverage_score,
            "findings_count": len(state.review_findings),
            "blocking_count": sum(1 for f in state.review_findings if f.blocking),
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "message": f.message[:120],
                    "blocking": f.blocking,
                    "contract_clause_ref": f.contract_clause_ref,
                }
                for f in state.review_findings
            ],
            "summary": decision.summary[:200],
            "next_action": decision.next_action[:200] if decision.next_action else "",
        }
        state.iteration_history.append(snapshot)

        # Increment iteration counter AFTER snapshot so audit trail is natural.
        if decision.decision in ("revise_code", "revise_spec"):
            state.iteration += 1
            decision.iteration = state.iteration

        # Update work item status based on decision
        status_map = {
            "approve": WorkflowStatus.APPROVED,
            "revise_code": WorkflowStatus.REVISE_CODE,
            "revise_spec": WorkflowStatus.REVISE_SPEC,
            "escalate_to_human": WorkflowStatus.ESCALATED,
        }
        state.work_item.transition_to(
            status_map.get(decision.decision, WorkflowStatus.ESCALATED)
        )

        logger.info(
            f"Gate decision: {decision.decision} "
            f"(drift={decision.drift_score}, coverage={decision.coverage_score}, "
            f"round={round_index}, iteration={state.iteration}/{state.max_iterations})"
        )
    except Exception as e:
        logger.error(f"Failed to parse gate decision: {e}")
        state.error = f"Gate decision parsing failed: {e}"

    return state


def _build_gate_prompt(state: GovernanceState) -> str:
    """Build the prompt for the gatekeeper with all evidence."""
    contract = state.contract
    report = state.execution_report
    assert contract is not None and report is not None

    parts = [
        "## CONTRACT SUMMARY\n",
        f"Goals: {len(contract.goals)}",
        f"Acceptance Criteria: {len(contract.acceptance_criteria)} "
        f"({sum(1 for ac in contract.acceptance_criteria if ac.priority == 'must')} must)",
        f"Constraints: {len(contract.constraints)}",
        f"Assumed Defaults: {len(contract.assumed_defaults)}",
        "",
        "### Goals",
    ]
    for i, g in enumerate(contract.goals):
        parts.append(f"  [{i}] {g}")

    parts.append(f"\n## EXECUTION SUMMARY\n")
    parts.append(f"Executor: {report.executor_name}")
    parts.append(f"Summary: {report.summary}")
    parts.append(f"Unresolved: {report.unresolved_items}")

    parts.append(f"\n## REVIEW FINDINGS\n")
    if state.review_findings:
        blocking = [f for f in state.review_findings if f.blocking]
        non_blocking = [f for f in state.review_findings if not f.blocking]

        parts.append(f"Total: {len(state.review_findings)} findings "
                      f"({len(blocking)} blocking)\n")

        if blocking:
            parts.append("### Blocking Findings (P0)")
            for f in blocking:
                parts.append(f"  - [{f.category}] {f.message}")
                parts.append(f"    Ref: {f.contract_clause_ref}")

        if non_blocking:
            parts.append("\n### Non-Blocking Findings")
            for f in non_blocking:
                parts.append(f"  - [{f.severity}][{f.category}] {f.message}")
    else:
        parts.append("No findings reported.\n")

    # Include scores from reviewer if available
    drift = state.review_drift_score
    coverage = state.review_coverage_score
    parts.append(f"\n## SCORES\n")
    parts.append(f"Drift Score: {drift}/100 (lower is better)")
    parts.append(f"Coverage Score: {coverage}/100 (higher is better)")

    parts.append(
        f"\n## Iteration: {state.iteration}/{state.max_iterations}\n"
    )

    # Include risk level for risk-aware decisions
    risk = state.work_item.risk_level
    parts.append(f"## Risk Level: {risk.upper()}\n")
    if risk == "high":
        parts.append(
            "⚠️ HIGH RISK — stricter thresholds apply: "
            "max_drift=15, min_coverage=85, ≥2 P0/P1 → escalate\n"
        )

    parts.append(
        "\n## Your Task\n\n"
        "Make a gate decision based on the decision matrix in your instructions.\n\n"
        "Respond with JSON:\n"
        "```json\n"
        "{\n"
        '  "decision": "approve|revise_code|revise_spec|escalate_to_human",\n'
        '  "drift_score": N,\n'
        '  "coverage_score": N,\n'
        '  "summary": "2-3 sentence rationale",\n'
        '  "next_action": "specific instruction on what to do next",\n'
        '  "requires_human": true|false\n'
        "}\n"
        "```"
    )

    return "\n".join(parts)


def _parse_decision(data: dict, state: GovernanceState) -> GateDecision:
    """Parse LLM output into a GateDecision."""
    blocking = [f for f in state.review_findings if f.blocking]

    return GateDecision(
        work_item_id=state.work_item.id,
        decision=data.get("decision", "escalate_to_human"),
        blocking_findings=blocking,
        all_findings_count=len(state.review_findings),
        drift_score=data.get("drift_score", state.review_drift_score),
        coverage_score=data.get("coverage_score", state.review_coverage_score),
        summary=data.get("summary", ""),
        requires_human=data.get("requires_human", False),
        next_action=data.get("next_action", ""),
        iteration=state.iteration,
    )
