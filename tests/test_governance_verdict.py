"""GovernanceVerdict tests — Phase 1 of v0.7 Governance Contract Runtime."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.schemas.verdict import GovernanceVerdict, VerdictEvidence


class TestGovernanceVerdict:
    def test_defaults(self):
        v = GovernanceVerdict(run_id="r", work_item_id="w")
        assert v.approved is False
        assert v.requires_human is False
        assert v.risk_level == "medium"
        assert v.sandbox_enabled is False
        assert v.changed_files_count == 0
        assert v.blocking_findings_count == 0
        assert v.policy_violations_count == 0
        assert v.completed_iterations == 0
        assert v.reasons == []
        assert v.next_action is None
        assert isinstance(v.evidence, VerdictEvidence)
        assert v.evidence.manifest is None

    def test_json_roundtrip(self):
        v = GovernanceVerdict(
            run_id="run_x",
            work_item_id="wi1",
            final_decision="approve",
            final_status="approved",
            approved=True,
            requires_human=False,
            risk_level="high",
            executor_name="codex",
            sandbox_enabled=True,
            sandbox_strategy="git_worktree",
            changed_files_count=3,
            blocking_findings_count=0,
            policy_violations_count=1,
            completed_iterations=2,
            evidence=VerdictEvidence(
                manifest="run_manifest.json",
                gate_decision="gate_decision.json",
                candidate_diff="candidate.diff",
            ),
            reasons=["all acceptance criteria met"],
            next_action="merge",
        )
        restored = GovernanceVerdict(**v.model_dump(mode="json"))
        assert restored == v

    def test_nested_evidence_relative_pointers(self):
        v = GovernanceVerdict(
            run_id="r",
            work_item_id="w",
            evidence=VerdictEvidence(manifest="run_manifest.json"),
        )
        dumped = v.model_dump(mode="json")
        assert dumped["evidence"]["manifest"] == "run_manifest.json"
        assert dumped["evidence"]["contract"] is None
