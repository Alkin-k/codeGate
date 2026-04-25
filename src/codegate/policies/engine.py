"""Policy Engine — programmatic gate rules.

These rules are deterministic and run AFTER the LLM-based review,
adding a layer of hard policy enforcement that cannot be overridden
by model hallucination.
"""

from __future__ import annotations

import logging
from typing import Literal

from codegate.schemas.gate import GateDecision
from codegate.schemas.review import ReviewFinding
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


class PolicyResult:
    """Result of policy evaluation."""

    def __init__(self):
        self.violations: list[str] = []
        self.warnings: list[str] = []
        self.override_decision: str | None = None

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0


def evaluate_policies(state: GovernanceState) -> PolicyResult:
    """Run all hard policy rules against the current state.

    These policies can OVERRIDE the LLM gatekeeper's decision.
    Rules 2/3 are risk-aware: high-risk tasks get stricter thresholds.
    """
    result = PolicyResult()

    if state.gate_decision is None:
        result.violations.append("No gate decision present")
        result.override_decision = "escalate_to_human"
        return result

    decision = state.gate_decision
    risk = state.work_item.risk_level  # "low", "medium", "high"

    # --- Risk-aware thresholds (ADR-008) ---
    max_drift = 15 if risk == "high" else 30
    min_coverage = 85 if risk == "high" else 70

    # Rule 1: Never approve with blocking findings
    blocking = [f for f in state.review_findings if f.blocking]
    if decision.decision == "approve" and blocking:
        result.violations.append(
            f"Cannot approve with {len(blocking)} blocking finding(s): "
            + "; ".join(f.message[:80] for f in blocking[:3])
        )
        result.override_decision = "revise_code"

    # Rule 2: Never approve with high drift (risk-aware)
    if decision.decision == "approve" and decision.drift_score > max_drift:
        result.violations.append(
            f"Cannot approve with drift_score={decision.drift_score} "
            f"(max: {max_drift} for {risk}-risk)"
        )
        result.override_decision = "revise_code"

    # Rule 3: Never approve with low coverage (risk-aware)
    if decision.decision == "approve" and decision.coverage_score < min_coverage:
        result.violations.append(
            f"Cannot approve with coverage_score={decision.coverage_score} "
            f"(min: {min_coverage} for {risk}-risk)"
        )
        result.override_decision = "revise_code"

    # Rule 4: Escalate after too many iterations
    if state.iteration >= state.max_iterations and decision.decision != "approve":
        result.violations.append(
            f"Max iterations ({state.max_iterations}) reached without approval"
        )
        result.override_decision = "escalate_to_human"

    # Rule 5: Security findings always block
    security_p0 = [
        f for f in state.review_findings
        if f.category == "security" and f.severity == "P0"
    ]
    if decision.decision == "approve" and security_p0:
        result.violations.append(
            f"Cannot approve with {len(security_p0)} security P0 finding(s)"
        )
        result.override_decision = "escalate_to_human"

    # Rule 6: Unresolved items block approval (ADR-007)
    if decision.decision == "approve" and state.execution_report:
        unresolved = state.execution_report.unresolved_items
        if unresolved:
            result.violations.append(
                f"Cannot approve with {len(unresolved)} unresolved item(s): "
                + "; ".join(str(u)[:60] for u in unresolved[:3])
            )
            result.override_decision = "revise_code"

    # Rule 7: assumed_defaults violations block approval (ADR-007)
    if decision.decision == "approve":
        assumed_violations = [
            f for f in state.review_findings
            if f.contract_clause_ref.startswith("assumed_defaults")
            and f.severity in ("P0", "P1")
        ]
        if assumed_violations:
            override = "escalate_to_human" if risk == "high" else "revise_code"
            result.violations.append(
                f"Cannot approve with {len(assumed_violations)} assumed_defaults "
                f"violation(s) at P0/P1 severity"
            )
            result.override_decision = override

    # Rule 8: High-risk + multiple P0/P1 findings → escalate (ADR-008)
    if decision.decision == "approve" and risk == "high":
        severe = [
            f for f in state.review_findings
            if f.severity in ("P0", "P1")
        ]
        if len(severe) >= 2:
            result.violations.append(
                f"High-risk task with {len(severe)} P0/P1 findings → escalate"
            )
            result.override_decision = "escalate_to_human"

    if result.violations:
        logger.warning(
            f"Policy violations: {result.violations}, "
            f"overriding decision to: {result.override_decision}"
        )

    return result


def apply_policy_override(state: GovernanceState) -> GovernanceState:
    """Apply policy engine results, potentially overriding the LLM decision.

    When overriding, MUST sync: decision, summary, next_action, requires_human,
    AND work_item.status (otherwise summary.final_status diverges from decision).
    Persists violations list on state for evidence.
    """
    from codegate.schemas.work_item import WorkflowStatus

    policy_result = evaluate_policies(state)

    # Always persist policy evaluation result (even if no violations)
    state.policy_violations = policy_result.violations
    state.policy_result = {
        "violations": policy_result.violations,
        "override_applied": policy_result.has_violations and policy_result.override_decision is not None,
        "override_decision": policy_result.override_decision,
        "gatekeeper_original_decision": (
            state.gate_decision.decision if state.gate_decision else None
        ),
    }

    if policy_result.has_violations and policy_result.override_decision:
        original = state.gate_decision.decision if state.gate_decision else "none"
        new_decision = policy_result.override_decision
        logger.warning(
            f"Policy override: {original} → {new_decision}"
        )

        if state.gate_decision:
            state.gate_decision.decision = new_decision
            state.gate_decision.summary += (
                f"\n[POLICY OVERRIDE] Original decision was '{original}'. "
                f"Overridden due to: {'; '.join(policy_result.violations)}"
            )

            # Sync next_action to match the overridden decision
            if new_decision == "escalate_to_human":
                state.gate_decision.requires_human = True
                state.gate_decision.next_action = (
                    f"[ESCALATED BY POLICY] "
                    f"Violations: {'; '.join(policy_result.violations)}. "
                    f"Requires human review before proceeding."
                )
            elif new_decision == "revise_code":
                state.gate_decision.next_action = (
                    f"[BLOCKED BY POLICY] "
                    f"Violations: {'; '.join(policy_result.violations)}. "
                    f"Revise code to address these issues."
                )

            # Sync work_item.status to match the overridden decision.
            # Without this, summary.final_status stays as the original
            # gatekeeper decision (e.g., "approved") while decision is
            # "revise_code", causing misleading evidence.
            status_map = {
                "approve": WorkflowStatus.APPROVED,
                "revise_code": WorkflowStatus.REVISE_CODE,
                "revise_spec": WorkflowStatus.REVISE_SPEC,
                "escalate_to_human": WorkflowStatus.ESCALATED,
            }
            new_status = status_map.get(new_decision, WorkflowStatus.ESCALATED)
            state.work_item.transition_to(new_status)

    return state

