"""Review History tests — verify multi-round evidence accumulation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.schemas.work_item import WorkItem
from codegate.schemas.gate import GateDecision
from codegate.schemas.review import ReviewFinding
from codegate.workflow.state import GovernanceState


def _make_state() -> GovernanceState:
    work_item = WorkItem(raw_request="review history test")
    return GovernanceState(work_item=work_item)


def _make_review_entry(iteration: int) -> dict:
    """Simulate a review_history entry for a given iteration."""
    return {
        "iteration": iteration,
        "timestamp": f"2026-05-06T00:0{iteration}:00Z",
        "review_findings": [
            {
                "category": "correctness",
                "severity": "medium",
                "message": f"Finding from iteration {iteration}",
                "contract_clause_ref": None,
                "code_location": None,
                "blocking": False,
                "suggestion": "fix it",
            }
        ],
        "policy_result": {
            "violations": [],
            "override_decision": None,
            "warnings": [],
        },
        "gate_decision": {
            "work_item_id": "test",
            "decision": "revise_code" if iteration < 3 else "approve",
            "blocking_findings": 0,
            "all_findings_count": 1,
            "drift_score": iteration * 10,
            "coverage_score": 100 - iteration * 5,
            "summary": f"Iteration {iteration} gate",
            "requires_human": False,
            "next_action": None,
            "iteration": iteration,
        },
    }


class TestHistoryAccumulates:
    """Review history should accumulate across iterations."""

    def test_single_iteration(self):
        state = _make_state()
        state.review_history.append(_make_review_entry(1))
        assert len(state.review_history) == 1
        assert state.review_history[0]["iteration"] == 1

    def test_multiple_iterations(self):
        state = _make_state()
        for i in range(1, 4):
            state.review_history.append(_make_review_entry(i))
        assert len(state.review_history) == 3
        assert state.review_history[0]["iteration"] == 1
        assert state.review_history[1]["iteration"] == 2
        assert state.review_history[2]["iteration"] == 3


class TestHistoryNotOverwritten:
    """Previous iteration evidence must not be overwritten."""

    def test_earlier_entries_preserved(self):
        state = _make_state()
        state.review_history.append(_make_review_entry(1))
        state.review_history.append(_make_review_entry(2))

        # Verify iteration 1 data is still intact
        entry_1 = state.review_history[0]
        assert entry_1["iteration"] == 1
        assert entry_1["gate_decision"]["decision"] == "revise_code"
        assert len(entry_1["review_findings"]) == 1
        assert "iteration 1" in entry_1["review_findings"][0]["message"]

    def test_each_entry_has_independent_findings(self):
        state = _make_state()
        state.review_history.append(_make_review_entry(1))
        state.review_history.append(_make_review_entry(2))

        # Findings in iteration 1 and 2 should be different
        msg_1 = state.review_history[0]["review_findings"][0]["message"]
        msg_2 = state.review_history[1]["review_findings"][0]["message"]
        assert msg_1 != msg_2


class TestHistoryFields:
    """Each history entry should contain the required fields."""

    def test_entry_has_required_fields(self):
        entry = _make_review_entry(1)
        assert "iteration" in entry
        assert "timestamp" in entry
        assert "review_findings" in entry
        assert "policy_result" in entry
        assert "gate_decision" in entry

    def test_review_findings_is_list(self):
        entry = _make_review_entry(1)
        assert isinstance(entry["review_findings"], list)
        assert len(entry["review_findings"]) > 0

    def test_gate_decision_has_decision_field(self):
        entry = _make_review_entry(1)
        assert "decision" in entry["gate_decision"]


class TestPolicyOverrideAutoAppends:
    """apply_policy_override() must auto-append to review_history (production path)."""

    def test_apply_policy_override_appends_history(self):
        """Calling apply_policy_override should append a review_history entry."""
        from codegate.policies.engine import apply_policy_override

        state = _make_state()
        state.review_findings = [
            ReviewFinding(
                category="correctness",
                severity="P2",
                message="minor issue",
                contract_clause_ref="goal[0]",
                blocking=False,
            ),
        ]
        state.gate_decision = GateDecision(
            work_item_id=state.work_item.id,
            decision="approve",
            drift_score=5,
            coverage_score=95,
        )
        assert len(state.review_history) == 0

        apply_policy_override(state)

        assert len(state.review_history) == 1
        entry = state.review_history[0]
        assert entry["iteration"] == 1
        assert "timestamp" in entry
        assert isinstance(entry["review_findings"], list)
        assert isinstance(entry["policy_result"], dict)
        assert entry["gate_decision"] is not None

    def test_apply_policy_override_includes_audit_fields(self):
        """review_history entry should include raw_review_findings and suppressed_findings."""
        from codegate.policies.engine import apply_policy_override

        state = _make_state()
        state.review_findings = [
            ReviewFinding(
                category="drift",
                severity="P1",
                message="drift detected",
                contract_clause_ref="goal[0]",
                blocking=True,
            ),
        ]
        state.raw_review_findings = [
            ReviewFinding(
                category="drift",
                severity="P1",
                message="drift detected",
                contract_clause_ref="goal[0]",
                blocking=True,
            ),
            ReviewFinding(
                category="maintainability",
                severity="P2",
                message="suppressed false positive",
                contract_clause_ref="goal[1]",
                blocking=False,
            ),
        ]
        state.suppressed_findings = [
            {
                "message": "suppressed false positive",
                "category": "maintainability",
                "severity": "P2",
                "reason": "Suppressed by structural pre-check",
            }
        ]
        state.gate_decision = GateDecision(
            work_item_id=state.work_item.id,
            decision="approve",
            drift_score=10,
            coverage_score=90,
        )

        apply_policy_override(state)

        entry = state.review_history[0]
        assert "raw_review_findings" in entry
        assert "suppressed_findings" in entry
        assert len(entry["raw_review_findings"]) == 2
        assert len(entry["suppressed_findings"]) == 1
        assert entry["suppressed_findings"][0]["reason"] == "Suppressed by structural pre-check"

    def test_multiple_policy_override_calls_accumulate(self):
        """Multiple calls to apply_policy_override should accumulate entries."""
        from codegate.policies.engine import apply_policy_override

        state = _make_state()

        # Iteration 1: approve (no violations)
        state.review_findings = []
        state.gate_decision = GateDecision(
            work_item_id=state.work_item.id,
            decision="approve",
            drift_score=0,
            coverage_score=100,
        )
        apply_policy_override(state)

        # Iteration 2: revise (blocking finding)
        state.review_findings = [
            ReviewFinding(
                category="security",
                severity="P0",
                message="sql injection",
                contract_clause_ref="goal[0]",
                blocking=True,
            ),
        ]
        state.gate_decision.decision = "approve"  # Gate says approve
        apply_policy_override(state)

        assert len(state.review_history) == 2
        assert state.review_history[0]["gate_decision"]["decision"] == "approve"
        # Second call should have been overridden to revise_code
        assert state.review_history[1]["policy_result"]["has_violations"] is True
