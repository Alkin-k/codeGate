"""CLI `runs` group tests — Phase 3+4 of v0.7 Governance Contract Runtime.

Most logic lives in ArtifactStore helpers, so we test those directly and add a
light Typer CliRunner smoke test for the command wiring. Critically, replay-lite
must perform zero LLM/executor work — it only reads artifacts.
"""

from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.schemas.work_item import WorkItem
from codegate.schemas.contract import ImplementationContract, AcceptanceCriterion
from codegate.schemas.execution import ExecutionReport
from codegate.schemas.gate import GateDecision
from codegate.workflow.state import GovernanceState
from codegate.store.artifact_store import ArtifactStore


def _make_state(decision="approve", executor="codex"):
    work_item = WorkItem(raw_request="cli runs test")
    state = GovernanceState(work_item=work_item)
    state.contract = ImplementationContract(
        work_item_id=work_item.id,
        goals=["g"],
        non_goals=["n"],
        acceptance_criteria=[
            AcceptanceCriterion(description="c", priority="must", verification="manual")
        ],
    )
    state.execution_report = ExecutionReport(
        work_item_id=work_item.id, code_output="o", summary="s",
        executor_name=executor, file_list=["a.py"],
    )
    state.gate_decision = GateDecision(
        work_item_id=work_item.id, decision=decision, drift_score=0, coverage_score=100,
        summary="ok", next_action="merge",
    )
    return state


class TestHelpers:
    def test_list_run_metadata(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(), run_id="run_1")
        store.save_run(_make_state(), run_id="run_2")
        assert {m.run_id for m in store.list_run_metadata()} == {"run_1", "run_2"}

    def test_diff_two_runs(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(decision="approve"), run_id="run_a")
        store.save_run(_make_state(decision="revise_code"), run_id="run_b")
        diff = store.diff_runs("run_a", "run_b")
        assert "final_decision" in diff["differing_fields"]

    def test_full_bundle_completeness_is_one(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(), run_id="run_a")
        bundle = store.load_run("run_a")
        assert bundle.completeness_score == 1.0
        assert bundle.missing == []

    def test_missing_referenced_file_lowers_score(self, tmp_path):
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(_make_state(), run_id="run_a")
        (run_dir / "summary.json").unlink()
        bundle = store.load_run("run_a")
        assert "summary.json" in bundle.missing
        assert bundle.completeness_score < 1.0

    def test_replay_does_no_network(self, tmp_path, monkeypatch):
        """load_run/completeness must not invoke the LLM layer."""
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(), run_id="run_a")

        import codegate.llm as llm_mod

        def _boom(*a, **k):
            raise AssertionError("replay must not call the LLM")

        # Guard every public callable in the llm module.
        for attr in dir(llm_mod):
            obj = getattr(llm_mod, attr)
            if callable(obj) and not attr.startswith("__"):
                monkeypatch.setattr(llm_mod, attr, _boom, raising=False)

        bundle = store.load_run("run_a")
        store.diff_runs("run_a", "run_a")
        assert bundle.verdict is not None


class TestCliWiring:
    def test_runs_list_and_replay_smoke(self, tmp_path, monkeypatch):
        # Point the store at our tmp artifacts dir via CODEGATE_STORE_DIR.
        monkeypatch.setenv("CODEGATE_STORE_DIR", str(tmp_path))
        store = ArtifactStore(base_dir=tmp_path)
        store.save_run(_make_state(), run_id="run_cli")

        from codegate.cli import app

        runner = CliRunner()
        res_list = runner.invoke(app, ["runs", "list"])
        assert res_list.exit_code == 0, res_list.output
        assert "run_cli" in res_list.output

        res_replay = runner.invoke(app, ["runs", "replay", "run_cli"])
        assert res_replay.exit_code == 0, res_replay.output
        assert "Replay" in res_replay.output

        res_show = runner.invoke(app, ["runs", "show", "run_cli"])
        assert res_show.exit_code == 0, res_show.output

    def test_runs_show_missing_run(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEGATE_STORE_DIR", str(tmp_path))
        from codegate.cli import app

        runner = CliRunner()
        res = runner.invoke(app, ["runs", "show", "nope"])
        assert res.exit_code == 1
