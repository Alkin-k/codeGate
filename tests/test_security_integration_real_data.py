"""Integration test using REAL T5/T6 execution_report.json data.

This test loads actual executor output from previous runs and validates
the full pipeline:
  compute_baseline_diff → evaluate_security_policies → evaluate_policies

No external LLM calls. Pure offline verification.

Test data source:
  test_results/v2_frontend_client_full_rerun_20260428/
    t5_security_constrained/c2455db13629/execution_report.json
    t6_security_unconstrained/5bb8b984f7a9/execution_report.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codegate.analysis.baseline_diff import compute_baseline_diff
from codegate.policies.engine import evaluate_policies
from codegate.policies.security import evaluate_security_policies
from codegate.schemas.gate import GateDecision
from codegate.schemas.work_item import WorkItem
from codegate.workflow.state import GovernanceState

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent
_RERUN_DIR = _PROJECT_ROOT / "test_results" / "v2_frontend_client_full_rerun_20260428"
_T5_DIR = _RERUN_DIR / "t5_security_constrained" / "c2455db13629"
_T6_DIR = _RERUN_DIR / "t6_security_unconstrained" / "5bb8b984f7a9"

_has_t5_data = _T5_DIR.exists() and (_T5_DIR / "execution_report.json").exists()
_has_t6_data = _T6_DIR.exists() and (_T6_DIR / "execution_report.json").exists()

skip_no_data = pytest.mark.skipif(
    not (_has_t5_data and _has_t6_data),
    reason="Real T5/T6 test data not available"
)


def _load_report(path: Path) -> dict:
    with open(path / "execution_report.json") as f:
        return json.load(f)


def _build_state_from_report(report: dict, decision: str = "approve") -> GovernanceState:
    """Build a GovernanceState from a real execution report.

    Runs compute_baseline_diff to produce structural_diff, then
    creates a state that can be fed to evaluate_policies.
    """
    baseline = report.get("baseline_content", {})
    current = report.get("files_content", {})

    diff_result = compute_baseline_diff(baseline, current)

    work_item = WorkItem(
        raw_request="integration test",
        id=report.get("work_item_id", "test"),
    )

    return GovernanceState(
        work_item=work_item,
        structural_diff=diff_result.to_dict(),
        gate_decision=GateDecision(
            work_item_id=work_item.id,
            decision=decision,
            drift_score=0,
            coverage_score=100,
        ),
    )


# ---------------------------------------------------------------------------
# T5: Real data — should PASS
# ---------------------------------------------------------------------------


@skip_no_data
class TestT5RealDataPasses:
    """T5 real execution_report.json: scoped guest via meta.guest → approve."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.report = _load_report(_T5_DIR)
        self.baseline = self.report.get("baseline_content", {})
        self.current = self.report.get("files_content", {})
        self.diff = compute_baseline_diff(self.baseline, self.current)

    def test_structural_diff_has_ts_patterns(self) -> None:
        """TS extractor produces meaningful patterns, not just @click/@keyframes."""
        all_kinds = set()
        for p in self.diff.removed_from_baseline:
            all_kinds.add(p.kind)
        for p in self.diff.added_not_in_baseline:
            all_kinds.add(p.kind)
        for p in self.diff.unchanged_baseline:
            all_kinds.add(p.kind)

        # Should have TS-specific kinds
        ts_kinds = {"router_guard", "auth_condition", "guard_condition",
                     "route_meta", "storage_access", "import"}
        has_ts_kinds = all_kinds & ts_kinds
        assert len(has_ts_kinds) > 0, \
            f"Expected TS-specific pattern kinds, got: {all_kinds}"

    def test_no_security_violations(self) -> None:
        sec_result = evaluate_security_policies(
            self.diff.to_dict(), self.current
        )
        assert sec_result.security_violations == [], \
            f"T5 should have no violations: {sec_result.security_violations}"

    def test_policy_does_not_override(self) -> None:
        sec_result = evaluate_security_policies(
            self.diff.to_dict(), self.current
        )
        assert sec_result.override_decision is None

    def test_policy_engine_no_security_violations(self) -> None:
        state = _build_state_from_report(self.report)
        result = evaluate_policies(state)
        security_violations = [v for v in result.violations if "[SECURITY]" in v]
        assert security_violations == [], \
            f"T5 should pass policy engine: {security_violations}"

    def test_nothing_removed_from_baseline(self) -> None:
        """T5 preserves all existing auth logic."""
        assert len(self.diff.removed_from_baseline) == 0, \
            f"T5 should not remove anything: {[p.pattern for p in self.diff.removed_from_baseline]}"

    def test_guest_route_meta_added(self) -> None:
        """T5 adds guest route meta (scoped access)."""
        added_meta = [p for p in self.diff.added_not_in_baseline if p.kind == "route_meta"]
        assert any("guest" in p.pattern.lower() for p in added_meta), \
            f"T5 should add guest route meta, got: {[p.pattern for p in added_meta]}"


# ---------------------------------------------------------------------------
# T6: Real data — should BLOCK
# ---------------------------------------------------------------------------


@skip_no_data
class TestT6RealDataBlocks:
    """T6 real execution_report.json: global guest bypass → escalate."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.report = _load_report(_T6_DIR)
        self.baseline = self.report.get("baseline_content", {})
        self.current = self.report.get("files_content", {})
        self.diff = compute_baseline_diff(self.baseline, self.current)

    def test_structural_diff_not_trivial(self) -> None:
        """Should produce meaningful patterns, not just @click/@keyframes."""
        all_kinds = set()
        for p in self.diff.added_not_in_baseline:
            all_kinds.add(p.kind)
        for p in self.diff.removed_from_baseline:
            all_kinds.add(p.kind)

        # Must have TS security-relevant kinds
        security_kinds = {"auth_condition", "guard_condition", "import"}
        has_security = all_kinds & security_kinds
        assert len(has_security) > 0, \
            f"Expected security-relevant patterns, got kinds: {all_kinds}"

    def test_detects_guard_condition_changes(self) -> None:
        """Removed and added guard_conditions should be detected."""
        removed_guards = [p for p in self.diff.removed_from_baseline if p.kind == "guard_condition"]
        added_guards = [p for p in self.diff.added_not_in_baseline if p.kind == "guard_condition"]
        assert len(removed_guards) > 0, "Should detect removed guard conditions"
        assert len(added_guards) > 0, "Should detect added guard conditions"

    def test_detects_guest_patterns_added(self) -> None:
        """Guest-related auth_conditions should be in added."""
        added_auth = [p for p in self.diff.added_not_in_baseline if p.kind == "auth_condition"]
        guest_auth = [p for p in added_auth if "guest" in p.pattern.lower()]
        assert len(guest_auth) > 0, \
            f"Should detect guest auth additions, got: {[p.pattern for p in added_auth]}"

    def test_security_violations_triggered(self) -> None:
        sec_result = evaluate_security_policies(
            self.diff.to_dict(), self.current
        )
        assert len(sec_result.security_violations) > 0, \
            f"T6 should have security violations: {sec_result.security_violations}"

    def test_sec1_triggered(self) -> None:
        """SEC-1: Guard condition weakened should trigger."""
        sec_result = evaluate_security_policies(
            self.diff.to_dict(), self.current
        )
        sec1_triggers = [t for t in sec_result.rule_triggers if t["rule"] == "SEC-1"]
        assert len(sec1_triggers) > 0, \
            f"SEC-1 should trigger, got rules: {[t['rule'] for t in sec_result.rule_triggers]}"

    def test_sec3_triggered(self) -> None:
        """SEC-3: Unscoped guest access should trigger."""
        sec_result = evaluate_security_policies(
            self.diff.to_dict(), self.current
        )
        sec3_triggers = [t for t in sec_result.rule_triggers if t["rule"] == "SEC-3"]
        assert len(sec3_triggers) > 0, \
            f"SEC-3 should trigger, got rules: {[t['rule'] for t in sec_result.rule_triggers]}"

    def test_sec4_triggered_as_weakened(self) -> None:
        """SEC-4: Token logic weakened (not deleted) should trigger."""
        sec_result = evaluate_security_policies(
            self.diff.to_dict(), self.current
        )
        sec4_triggers = [t for t in sec_result.rule_triggers if t["rule"] == "SEC-4"]
        assert len(sec4_triggers) > 0, \
            f"SEC-4 should trigger, got rules: {[t['rule'] for t in sec_result.rule_triggers]}"
        # Verify it's classified as 'weakened', not 'deleted'
        cases = [t.get("case", "") for t in sec4_triggers]
        assert "token_weakened" in cases, \
            f"SEC-4 should be 'token_weakened', got cases: {cases}"

    def test_override_is_escalate(self) -> None:
        sec_result = evaluate_security_policies(
            self.diff.to_dict(), self.current
        )
        assert sec_result.override_decision == "escalate_to_human", \
            f"T6 should escalate, got: {sec_result.override_decision}"

    def test_policy_engine_blocks(self) -> None:
        """Full policy engine should block T6."""
        state = _build_state_from_report(self.report)
        result = evaluate_policies(state)
        security_violations = [v for v in result.violations if "[SECURITY]" in v]
        assert len(security_violations) > 0, \
            f"T6 should be blocked by policy engine: {result.violations}"
        assert result.override_decision in ("revise_code", "escalate_to_human")

    def test_policy_result_has_security_field(self) -> None:
        """policy_result should include security sub-object for audit trail."""
        from codegate.policies.engine import apply_policy_override

        state = _build_state_from_report(self.report)
        state = apply_policy_override(state)

        assert state.policy_result is not None
        assert "security" in state.policy_result, \
            f"policy_result should have 'security' field: {list(state.policy_result.keys())}"

        sec = state.policy_result["security"]
        assert len(sec.get("rule_triggers", [])) > 0
        assert len(sec.get("security_violations", [])) > 0

    def test_final_decision_consistent(self) -> None:
        """Final decision and work_item.status should be consistent."""
        from codegate.policies.engine import apply_policy_override

        state = _build_state_from_report(self.report)
        state = apply_policy_override(state)

        decision = state.gate_decision.decision
        status = state.work_item.status.value

        if decision == "escalate_to_human":
            assert status == "escalated"
        elif decision == "revise_code":
            assert status == "revise_code"
        elif decision == "approve":
            # T6 should NOT be approved
            pytest.fail(f"T6 should not be approved, got: {decision}")
