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
  Rule 9: Validation test failure blocks approve
  Rule 10: Missing test script is a warning (not a violation)
  Rule 11: Security Policy Gate (SEC-1~5 auth/routing risk detection)
"""

from __future__ import annotations

import logging

from codegate.schemas.work_item import WorkflowStatus
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

    # Rule 9: Validation test failure blocks approve
    #   Distinguish "tests ran and failed" from "no test script" from
    #   "build/dependency/runner failure".
    if decision.decision == "approve" and state.execution_report:
        vr = state.execution_report.validation_result
        if vr is not None and not vr.passed:
            if vr.tests_run > 0 and vr.tests_failed > 0:
                # Case A: Tests ran and some failed → block
                result.violations.append(
                    f"Cannot approve: {vr.tests_failed}/{vr.tests_run} tests failed "
                    f"(command: {vr.command}, exit_code: {vr.exit_code})"
                )
                result.override_decision = "revise_code"
            elif vr.tests_run == 0 and _is_missing_test_script(vr):
                # Rule 10: Genuinely missing test script → warning only.
                # Identified by explicit npm/yarn error signatures.
                error_hint = vr.error_summary or "no test script found"
                result.warnings.append(
                    f"Validation: no test script configured "
                    f"({error_hint}). Not blocking approval."
                )
            else:
                # Case B: tests_run==0 but NOT a missing-script case, or
                # any other unrecognized failure → block as validation_failure.
                # Covers: build errors, syntax errors, dependency issues,
                # test runner crashes, etc.
                error_hint = vr.error_summary or f"exit_code={vr.exit_code}"
                result.violations.append(
                    f"Cannot approve: validation failed ({vr.command}: {error_hint})"
                )
                result.override_decision = "revise_code"

    # Rule 11: Security Policy Gate (SEC-1~5)
    # Consumes structural_diff facts to detect auth/routing risks.
    if state.structural_diff:
        from codegate.policies.security import evaluate_security_policies

        files_content = (
            state.execution_report.files_content
            if state.execution_report
            else None
        )
        sec_result = evaluate_security_policies(
            state.structural_diff, files_content
        )
        if sec_result.security_violations:
            for v in sec_result.security_violations:
                result.violations.append(f"[SECURITY] {v}")
            # Security policy may escalate; use its decision if stronger
            if sec_result.override_decision == "escalate_to_human":
                result.override_decision = "escalate_to_human"
            elif result.override_decision is None:
                result.override_decision = sec_result.override_decision or "revise_code"
        result.warnings.extend(
            f"[SECURITY] {w}" for w in sec_result.security_warnings
        )
        # Store security result for merging into policy_result
        result._security_result = sec_result  # type: ignore[attr-defined]

    if result.violations:
        logger.warning(
            f"Policy violations: {result.violations}, "
            f"overriding decision to: {result.override_decision}"
        )

    return result


# Known error signatures for "no test script configured" in JS package managers.
# Only these patterns trigger the Rule 10 warning-only path.
_MISSING_SCRIPT_SIGNATURES = [
    # npm / yarn
    "missing script: \"test\"",
    "missing script: 'test'",
    "no test specified",
    "error: missing script: test",
]


def _is_missing_test_script(vr) -> bool:
    """Check if a validation failure is specifically due to a missing test script.

    Returns True ONLY when the error output contains a known signature
    indicating the project simply has no test script configured.
    Returns False for all other failures (build errors, dependency issues,
    syntax errors, runner crashes, etc.) so they are treated as real failures.
    """
    search_text = ""
    if vr.error_summary:
        search_text += vr.error_summary.lower()
    if vr.stdout_tail:
        search_text += " " + vr.stdout_tail.lower()

    if not search_text.strip():
        return False

    return any(sig in search_text for sig in _MISSING_SCRIPT_SIGNATURES)


def apply_policy_override(state: GovernanceState) -> GovernanceState:
    """Apply policy engine results, potentially overriding the LLM decision.

    Writes structured audit evidence to state.policy_violations and
    state.policy_result, and syncs work_item.status to match the
    overridden decision.
    """
    policy_result = evaluate_policies(state)

    original = state.gate_decision.decision if state.gate_decision else "none"

    if (
        state.gate_decision
        and policy_result.has_violations
        and policy_result.override_decision in ("revise_code", "revise_spec")
        and original not in ("revise_code", "revise_spec")
    ):
        state.iteration += 1
        state.gate_decision.iteration = state.iteration
        if state.iteration >= state.max_iterations:
            policy_result.violations.append(
                f"Max iterations ({state.max_iterations}) reached without approval"
            )
            policy_result.override_decision = "escalate_to_human"

    # Always persist policy evaluation results for audit trail,
    # even when no violations occurred (proves the check ran).
    state.policy_violations = policy_result.violations
    policy_dict = {
        "gatekeeper_original_decision": original,
        "violations": policy_result.violations,
        "warnings": policy_result.warnings,
        "override_decision": policy_result.override_decision,
        "has_violations": policy_result.has_violations,
    }

    # Merge security policy results into unified policy_result
    sec_result = getattr(policy_result, "_security_result", None)
    if sec_result is not None:
        policy_dict["security"] = sec_result.to_dict()
        state.security_policy_result = sec_result.to_dict()
    else:
        policy_dict["security"] = {
            "security_violations": [],
            "security_warnings": [],
            "override_decision": None,
            "rule_triggers": [],
        }

    state.policy_result = policy_dict

    if policy_result.has_violations and policy_result.override_decision:
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

            # Sync work_item.status to match the overridden decision.
            # Without this, final_status and decision diverge in artifacts.
            status_map = {
                "approve": WorkflowStatus.APPROVED,
                "revise_code": WorkflowStatus.REVISE_CODE,
                "revise_spec": WorkflowStatus.REVISE_SPEC,
                "escalate_to_human": WorkflowStatus.ESCALATED,
            }
            new_status = status_map.get(
                policy_result.override_decision, WorkflowStatus.ESCALATED
            )
            state.work_item.transition_to(new_status)

    return state
