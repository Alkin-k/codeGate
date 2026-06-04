"""ArtifactStore runtime tests — Phase 2 of v0.7 Governance Contract Runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.schemas.work_item import WorkItem
from codegate.schemas.contract import ImplementationContract, AcceptanceCriterion
from codegate.schemas.execution import ExecutionReport
from codegate.schemas.gate import GateDecision
from codegate.schemas.review import ReviewFinding
from codegate.schemas.sandbox import SandboxReport
from codegate.workflow.state import GovernanceState
from codegate.store.artifact_store import ArtifactStore


def _make_state(*, raw_request="runtime test", with_sandbox=False, blocking=False):
    work_item = WorkItem(raw_request=raw_request)
    state = GovernanceState(work_item=work_item)
    state.contract = ImplementationContract(
        work_item_id=work_item.id,
        goals=["goal"],
        non_goals=["nope"],
        acceptance_criteria=[
            AcceptanceCriterion(description="c", priority="must", verification="manual")
        ],
    )
    state.execution_report = ExecutionReport(
        work_item_id=work_item.id,
        code_output="out",
        summary="did the thing",
        executor_name="codex",
        file_list=["a.py", "b.py"],
    )
    state.gate_decision = GateDecision(
        work_item_id=work_item.id,
        decision="approve",
        drift_score=0,
        coverage_score=100,
        summary="all good",
        next_action="merge",
    )
    if blocking:
        state.review_findings = [
            ReviewFinding(
                severity="P0",
                category="security",
                message="missing auth",
                contract_clause_ref="AC-1",
                blocking=True,
            )
        ]
    if with_sandbox:
        state.sandbox_report = SandboxReport(
            enabled=True,
            strategy="git_worktree",
            project_dir="/tmp/project",
            sandbox_dir="/tmp/sandbox",
            base_ref="deadbeef",
            changed_files=["a.py"],
            diff_content="--- a/a.py\n+++ b/a.py\n",
            created_at="2026-06-04T00:00:00Z",
            cleanup_status="cleaned",
        )
    return state


class TestNewLayout:
    def test_saves_under_runs_run_id(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(_make_state())
        assert run_dir.parent == tmp_path / "runs"
        assert run_dir.name.startswith("run_")
        assert (run_dir / "run_metadata.json").exists()
        assert (run_dir / "verdict.json").exists()
        assert (run_dir / "run_manifest.json").exists()

    def test_same_work_item_twice_no_overwrite(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        state = _make_state()
        dir1 = store.save_run(state, run_id="run_20260604_120000_aaaaaa")
        dir2 = store.save_run(state, run_id="run_20260604_120001_bbbbbb")
        assert dir1 != dir2
        assert dir1.exists() and dir2.exists()
        runs = sorted((tmp_path / "runs").iterdir())
        assert len(runs) == 2

    def test_default_run_id_no_overwrite_same_second(self, tmp_path):
        """Auto-generated run_id (no explicit id) must not collide/overwrite even
        when the same work item is saved back-to-back within the same second."""
        store = ArtifactStore(base_dir=tmp_path)
        state = _make_state()  # same GovernanceState / same work_item.id
        dir1 = store.save_run(state)
        dir2 = store.save_run(state)
        assert dir1 != dir2
        assert dir1.exists() and dir2.exists()
        assert len(list((tmp_path / "runs").iterdir())) == 2
        index = json.loads((tmp_path / "run_index.json").read_text())
        run_ids = [r["run_id"] for r in index["runs"]]
        assert len(run_ids) == 2
        assert len(set(run_ids)) == 2  # two distinct entries
        # Both entries share the same work_item_id (proving the no-overwrite point).
        assert len({r["work_item_id"] for r in index["runs"]}) == 1


class TestVerdict:
    def test_verdict_fields(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(_make_state(with_sandbox=True, blocking=True))
        verdict = json.loads((run_dir / "verdict.json").read_text())
        assert verdict["final_decision"] == "approve"
        assert verdict["approved"] is True
        assert verdict["executor_name"] == "codex"
        assert verdict["sandbox_enabled"] is True
        assert verdict["sandbox_strategy"] == "git_worktree"
        assert verdict["changed_files_count"] == 1  # from sandbox changed_files
        assert verdict["blocking_findings_count"] == 1
        assert verdict["next_action"] == "merge"
        assert any("missing auth" in r for r in verdict["reasons"])

    def test_verdict_evidence_pointers_exist(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(_make_state(with_sandbox=True))
        verdict = json.loads((run_dir / "verdict.json").read_text())
        ev = verdict["evidence"]
        for key in ("manifest", "contract", "gate_decision", "candidate_diff"):
            val = ev[key]
            assert val is not None, f"{key} pointer is None"
            assert not Path(val).is_absolute()
            assert (run_dir / val).exists(), f"{key} -> {val} missing"

    def test_changed_files_falls_back_to_execution_report(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(_make_state(with_sandbox=False))
        verdict = json.loads((run_dir / "verdict.json").read_text())
        assert verdict["changed_files_count"] == 2  # file_list a.py, b.py


class TestManifestPointers:
    def test_manifest_includes_runtime_pointers_relative(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(_make_state())
        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        for key in ("run_metadata", "verdict"):
            val = manifest[key]
            assert val is not None
            assert not Path(val).is_absolute()
            assert (run_dir / val).exists()


class TestRunIndex:
    def test_index_updated(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(), run_id="run_a")
        store.save_run(_make_state(), run_id="run_b")
        index = json.loads((tmp_path / "run_index.json").read_text())
        ids = {r["run_id"] for r in index["runs"]}
        assert ids == {"run_a", "run_b"}
        entry = next(r for r in index["runs"] if r["run_id"] == "run_a")
        assert entry["artifact_dir"] == "runs/run_a"
        assert entry["verdict"] == "runs/run_a/verdict.json"
        assert entry["decision"] == "approve"

    def test_resave_same_run_id_replaces_not_duplicates(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(), run_id="run_a")
        store.save_run(_make_state(), run_id="run_a")
        index = json.loads((tmp_path / "run_index.json").read_text())
        assert sum(1 for r in index["runs"] if r["run_id"] == "run_a") == 1

    def test_index_failure_does_not_break_artifact(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        # Make run_index.json a directory so writing it raises — artifact must survive.
        (tmp_path / "run_index.json").mkdir()
        run_dir = store.save_run(_make_state(), run_id="run_a")
        assert (run_dir / "verdict.json").exists()
        assert (run_dir / "run_metadata.json").exists()


class TestLoadAndQuery:
    def test_list_run_metadata(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(), run_id="run_20260604_120000_aaaaaa")
        store.save_run(_make_state(), run_id="run_20260604_120001_bbbbbb")
        metas = store.list_run_metadata()
        assert [m.run_id for m in metas] == [
            "run_20260604_120000_aaaaaa",
            "run_20260604_120001_bbbbbb",
        ]
        assert metas[0].executor_name == "codex"

    def test_load_run_roundtrip(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(with_sandbox=True), run_id="run_a")
        bundle = store.load_run("run_a")
        assert bundle.metadata is not None
        assert bundle.verdict is not None
        assert bundle.verdict.final_decision == "approve"
        assert bundle.completeness_score == 1.0

    def test_completeness_reports_missing(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(_make_state(with_sandbox=True), run_id="run_a")
        # Delete a manifest-referenced artifact.
        (run_dir / "candidate.diff").unlink()
        bundle = store.load_run("run_a")
        assert "candidate.diff" in bundle.missing
        assert bundle.completeness_score < 1.0

    def test_diff_runs(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(with_sandbox=True), run_id="run_a")
        s = _make_state()
        s.gate_decision.decision = "revise_code"
        store.save_run(s, run_id="run_b")
        diff = store.diff_runs("run_a", "run_b")
        assert "final_decision" in diff["differing_fields"]
        assert diff["a"]["final_decision"] == "approve"
        assert diff["b"]["final_decision"] == "revise_code"
