"""Run Manifest tests — verify artifact indexing in run_manifest.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.schemas.work_item import WorkItem
from codegate.schemas.contract import ImplementationContract, AcceptanceCriterion
from codegate.schemas.execution import ExecutionReport
from codegate.schemas.gate import GateDecision
from codegate.schemas.sandbox import SandboxReport
from codegate.workflow.state import GovernanceState
from codegate.store.artifact_store import ArtifactStore


def _make_state(
    *,
    with_contract: bool = True,
    with_execution: bool = True,
    with_gate: bool = True,
    with_sandbox: bool = False,
    with_review_history: bool = False,
) -> GovernanceState:
    work_item = WorkItem(raw_request="manifest test")
    state = GovernanceState(work_item=work_item)

    if with_contract:
        state.contract = ImplementationContract(
            work_item_id=work_item.id,
            goals=["test goal"],
            non_goals=["explicitly out of scope"],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="test criterion",
                    priority="must",
                    verification="manual",
                )
            ],
        )

    if with_execution:
        state.execution_report = ExecutionReport(
            work_item_id=work_item.id,
            code_output="test output",
            summary="test execution",
        )

    if with_gate:
        state.gate_decision = GateDecision(
            work_item_id=work_item.id,
            decision="approve",
            drift_score=0,
            coverage_score=100,
        )

    if with_sandbox:
        state.sandbox_report = SandboxReport(
            enabled=True,
            strategy="temp_copy",
            project_dir="/tmp/project",
            sandbox_dir="/tmp/sandbox",
            changed_files=["test.py"],
            diff_path="/tmp/sandbox/candidate.diff",
            patch_path=None,
            created_at="2026-05-06T00:00:00Z",
            cleanup_status="cleaned",
        )

    if with_review_history:
        state.review_history = [
            {
                "iteration": 1,
                "timestamp": "2026-05-06T00:00:00Z",
                "review_findings": [],
                "policy_result": {"violations": []},
                "gate_decision": {"decision": "revise_code"},
            },
            {
                "iteration": 2,
                "timestamp": "2026-05-06T00:01:00Z",
                "review_findings": [],
                "policy_result": {"violations": []},
                "gate_decision": {"decision": "approve"},
            },
        ]

    return state


class TestManifestIndexesArtifacts:
    """run_manifest.json must index all artifacts produced by a run."""

    def test_manifest_contains_required_keys(self, tmp_path):
        state = _make_state()
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest_path = run_dir / "run_manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert "work_item_id" in manifest
        assert "generated_at" in manifest
        assert "artifacts" in manifest
        assert "work_item" in manifest
        assert "contract" in manifest
        assert "execution_report" in manifest
        assert "gate_decision" in manifest
        assert "summary" in manifest

    def test_manifest_artifacts_dict_lists_json_files(self, tmp_path):
        state = _make_state()
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert isinstance(manifest["artifacts"], dict)
        # Should have at least work_item.json, contract.json, etc.
        assert "work_item.json" in manifest["artifacts"]
        assert "contract.json" in manifest["artifacts"]
        assert "summary.json" in manifest["artifacts"]

    def test_manifest_pointers_are_relative_and_valid(self, tmp_path):
        state = _make_state()
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        # All pointers must be relative and the file must exist in run_dir
        for key in ("work_item", "summary", "contract"):
            val = manifest[key]
            assert val is not None, f"{key} is None"
            assert not Path(val).is_absolute(), f"{key} is absolute: {val}"
            assert (run_dir / val).exists(), f"{key} file missing: {val}"

    def test_manifest_artifacts_values_are_relative(self, tmp_path):
        state = _make_state()
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        for rel_path, stored_val in manifest["artifacts"].items():
            assert not Path(rel_path).is_absolute(), (
                f"artifact key is absolute: {rel_path}"
            )
            assert rel_path == stored_val, (
                f"artifact value should equal key, got {stored_val!r}"
            )
            assert (run_dir / rel_path).exists(), (
                f"artifact file missing: {rel_path}"
            )


class TestManifestIncludesSandbox:
    """Manifest must include sandbox report when present."""

    def test_sandbox_report_indexed(self, tmp_path):
        state = _make_state(with_sandbox=True)
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert manifest["sandbox_report"] is not None
        assert not Path(manifest["sandbox_report"]).is_absolute()
        assert (run_dir / manifest["sandbox_report"]).exists()

    def test_sandbox_report_null_when_absent(self, tmp_path):
        state = _make_state(with_sandbox=False)
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert manifest["sandbox_report"] is None


class TestManifestDiffPatchPointers:
    """Manifest must include candidate_diff and candidate_patch pointers."""

    def test_diff_patch_from_sandbox_with_content(self, tmp_path):
        """When diff_content is set, candidate.diff is written to run_dir."""
        state = _make_state(with_sandbox=True)
        # Set diff_content so the file is actually written to run_dir
        state.sandbox_report.diff_content = "--- a/test.py\n+++ b/test.py\n"
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        # Should be a relative path within run_dir, not the sandbox temp path
        assert manifest["candidate_diff"] == "candidate.diff"
        assert Path(run_dir / manifest["candidate_diff"]).exists()
        assert manifest["candidate_patch"] is None

    def test_diff_patch_null_when_no_content(self, tmp_path):
        """Without diff_content, no file is written — manifest should be null."""
        state = _make_state(with_sandbox=True)
        # No diff_content set — file won't exist in run_dir
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert manifest["candidate_diff"] is None
        assert manifest["candidate_patch"] is None

    def test_diff_patch_null_when_no_sandbox(self, tmp_path):
        state = _make_state(with_sandbox=False)
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert manifest["candidate_diff"] is None
        assert manifest["candidate_patch"] is None

    def test_manifest_no_absolute_paths(self, tmp_path):
        """ALL manifest pointer fields must be relative or None — no absolute paths."""
        state = _make_state(with_sandbox=True, with_review_history=True)
        state.sandbox_report.diff_content = "diff content"
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())

        # Every pointer field that resolves to a file must be relative
        pointer_keys = [
            "work_item", "contract", "execution_report", "sandbox_report",
            "review_history", "policy_result", "gate_decision", "summary",
            "candidate_diff", "candidate_patch",
        ]
        for key in pointer_keys:
            val = manifest.get(key)
            if val is not None:
                assert isinstance(val, str), f"manifest[{key}] not a string: {val!r}"
                assert not Path(val).is_absolute(), (
                    f"manifest[{key}] should be relative, got: {val}"
                )
                assert (run_dir / val).exists(), (
                    f"manifest[{key}] points to missing file: {val}"
                )


class TestManifestReviewHistory:
    """Manifest must include review_history when present."""

    def test_review_history_indexed(self, tmp_path):
        state = _make_state(with_review_history=True)
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert manifest["review_history"] is not None
        assert not Path(manifest["review_history"]).is_absolute()
        assert (run_dir / manifest["review_history"]).exists()

    def test_review_history_null_when_absent(self, tmp_path):
        state = _make_state(with_review_history=False)
        store = ArtifactStore(base_dir=tmp_path)
        run_dir = store.save_run(state)

        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert manifest["review_history"] is None
