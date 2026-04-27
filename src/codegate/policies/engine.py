"""Policy Engine — programmatic gate rules.

These rules are deterministic and run AFTER the LLM-based review,
adding a layer of hard policy enforcement that cannot be overridden
by model hallucination.

Rule inventory:
  Rule 1: Never approve with blocking findings
  Rule 2: Never approve with high drift (>30, or >15 for high-risk)
  Rule 3: Never approve with low coverage (<70, or <85 for high-risk)
  Rule 4: Escalate after too many iterations
  Rule 5: Security P0 findings always block
  Rule 6: Never approve with unresolved items
  Rule 7: Findings referencing assumed_defaults at P0/P1 block approve
  Rule 8: Risk-level-aware enforcement (high-risk = stricter thresholds)
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
    For example, if the gatekeeper says "approve" but there are
    unresolved P0 findings, the policy engine will force "revise_code".
    """
    result = PolicyResult()

    if state.gate_decision is None:
        result.violations.append("No gate decision present")
        result.override_decision = "escalate_to_human"
        return result

    decision = state.gate_decision
    risk = state.work_item.risk_level

    # Risk-aware thresholds (Rule 8)
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

    # Rule 6: Never approve with unresolved items
    if decision.decision == "approve" and state.execution_report:
        unresolved = state.execution_report.unresolved_items
        if unresolved:
            result.violations.append(
                f"Cannot approve with {len(unresolved)} unresolved item(s): "
                + "; ".join(str(u)[:60] for u in unresolved[:3])
            )
            result.override_decision = "revise_code"

    # Rule 7: Findings referencing assumed_defaults at P0/P1 block approve
    #   If the reviewer found issues with assumed defaults, the implementation
    #   is relying on unverified assumptions — this is a governance gap.
    if decision.decision == "approve":
        assumption_violations = [
            f for f in state.review_findings
            if "assumed_default" in f.contract_clause_ref
            and f.severity in ("P0", "P1")
        ]
        if assumption_violations:
            result.violations.append(
                f"Cannot approve with {len(assumption_violations)} finding(s) "
                f"violating assumed defaults: "
                + "; ".join(f.message[:60] for f in assumption_violations[:3])
            )
            # High-risk: escalate; otherwise: revise
            if risk == "high":
                result.override_decision = "escalate_to_human"
            else:
                result.override_decision = "revise_code"

    # Rule 8: High-risk tasks require human review if any P0/P1 findings exist
    if (
        decision.decision == "approve"
        and risk == "high"
        and any(f.severity in ("P0", "P1") for f in state.review_findings)
    ):
        p1_plus = [f for f in state.review_findings if f.severity in ("P0", "P1")]
        result.warnings.append(
            f"High-risk task approved with {len(p1_plus)} P0/P1 finding(s) — "
            f"consider human review"
        )
        # Only override if there are multiple P1+ findings
        if len(p1_plus) >= 2:
            result.violations.append(
                f"High-risk task cannot auto-approve with {len(p1_plus)} "
                f"P0/P1 findings — requires human review"
            )
            result.override_decision = "escalate_to_human"

    if result.violations:
        logger.warning(
            f"Policy violations: {result.violations}, "
            f"overriding decision to: {result.override_decision}"
        )

    return result


def apply_policy_override(state: GovernanceState) -> GovernanceState:
    """Apply policy engine results, potentially overriding the LLM decision."""
    policy_result = evaluate_policies(state)

    if policy_result.has_violations and policy_result.override_decision:
        original = state.gate_decision.decision if state.gate_decision else "none"
        logger.warning(
            f"Policy override: {original} → {policy_result.override_decision}"
        )

        if state.gate_decision:
            state.gate_decision.decision = policy_result.override_decision
            state.gate_decision.summary += (
                f"\n[POLICY OVERRIDE] Original decision was '{original}'. "
                f"Overridden due to: {'; '.join(policy_result.violations)}"
            )
            if policy_result.override_decision == "escalate_to_human":
                state.gate_decision.requires_human = True

    return state
