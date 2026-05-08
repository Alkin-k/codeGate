"""Integration test — run_executor creates ExecutionSandbox, isolates changes, produces artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.adapters.executor import ExecutorAdapter
from codegate.schemas.contract import ImplementationContract, AcceptanceCriterion
from codegate.schemas.execution import ExecutionReport
from codegate.schemas.work_item import WorkItem
from codegate.store.artifact_store import ArtifactStore
from codegate.workflow.state import GovernanceState


class FakeExecutorAdapter(ExecutorAdapter):
    """Adapter that writes a file into work_dir and records what it received."""

    def __init__(self):
        self.received_work_dir: str = ""
        self.received_contract: ImplementationContract | None = None

    @property
    def name(self) -> str:
        return "fake_sandbox_test"

    def execute(
        self,
        contract: ImplementationContract,
        context: str = "",
        feedback: str = "",
        work_dir: str = "",
    ) -> ExecutionReport:
        self.received_work_dir = work_dir
        self.received_contract = contract

        # Write a file into the sandbox
        if work_dir:
            (Path(work_dir) / "fake_output.py").write_text(
                "def hello():\n    return 'from sandbox'\n"
            )

        return ExecutionReport(
            work_item_id="",
            code_output="def hello():\n    return 'from sandbox'\n",
            file_list=["fake_output.py"],
            summary="Fake executor produced fake_output.py",
        )


def _make_git_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=str(project), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(project), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(project), capture_output=True, check=True,
    )
    (project / "README.md").write_text("# Original\n")
    subprocess.run(["git", "add", "."], cwd=str(project), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(project), capture_output=True, check=True,
    )
    return project


@pytest.fixture(autouse=True)
def _restore_adapter():
    """Ensure the default adapter is restored after each test."""
    from codegate.agents import executor as executor_mod
    original = executor_mod._adapter
    yield
    executor_mod._adapter = original


class TestRunExecutorSandboxIntegration:
    """run_executor must create a sandbox, run the adapter in it, and produce evidence."""

    def test_adapter_receives_sandbox_work_dir(self, tmp_path):
        from codegate.agents.executor import run_executor, set_executor_adapter

        project_dir = _make_git_project(tmp_path)
        fake = FakeExecutorAdapter()
        set_executor_adapter(fake)

        work_item = WorkItem(raw_request="create hello function")
        state = GovernanceState(work_item=work_item)
        state.contract = ImplementationContract(
            work_item_id=work_item.id,
            goals=["create hello function"],
            non_goals=["do not modify existing files"],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="hello.py exists",
                    priority="must",
                    verification="manual",
                )
            ],
        )

        # Monkey-patch adapter's project_dir to point to our test project
        fake._project_dir = str(project_dir)

        run_executor(state)

        # Adapter must have received a work_dir
        assert fake.received_work_dir != ""
        # work_dir must NOT be the original project_dir
        assert Path(fake.received_work_dir).resolve() != project_dir.resolve()

    def test_original_project_not_polluted(self, tmp_path):
        from codegate.agents.executor import run_executor, set_executor_adapter

        project_dir = _make_git_project(tmp_path)
        original_files = set(
            f.name for f in project_dir.iterdir() if f.name != ".git"
        )

        fake = FakeExecutorAdapter()
        set_executor_adapter(fake)
        fake._project_dir = str(project_dir)

        work_item = WorkItem(raw_request="test")
        state = GovernanceState(work_item=work_item)
        state.contract = ImplementationContract(
            work_item_id=work_item.id,
            goals=["test"],
            non_goals=["out of scope"],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="basic check",
                    priority="must",
                    verification="manual",
                )
            ],
        )

        run_executor(state)

        # fake_output.py must NOT exist in the original project
        assert not (project_dir / "fake_output.py").exists()
        # No new files appeared
        current_files = set(
            f.name for f in project_dir.iterdir() if f.name != ".git"
        )
        assert current_files == original_files

    def test_sandbox_report_has_changed_files_and_diff(self, tmp_path):
        from codegate.agents.executor import run_executor, set_executor_adapter

        project_dir = _make_git_project(tmp_path)
        fake = FakeExecutorAdapter()
        set_executor_adapter(fake)
        fake._project_dir = str(project_dir)

        work_item = WorkItem(raw_request="test")
        state = GovernanceState(work_item=work_item)
        state.contract = ImplementationContract(
            work_item_id=work_item.id,
            goals=["test"],
            non_goals=["out of scope"],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="basic check",
                    priority="must",
                    verification="manual",
                )
            ],
        )

        run_executor(state)

        assert state.sandbox_report is not None
        assert state.sandbox_report.enabled is True
        assert "fake_output.py" in state.sandbox_report.changed_files
        assert state.sandbox_report.diff_content is not None
        assert len(state.sandbox_report.diff_content) > 0
        assert state.sandbox_report.cleanup_status == "cleaned"

    def test_artifact_store_saves_candidate_diff(self, tmp_path):
        from codegate.agents.executor import run_executor, set_executor_adapter

        project_dir = _make_git_project(tmp_path)
        fake = FakeExecutorAdapter()
        set_executor_adapter(fake)
        fake._project_dir = str(project_dir)

        work_item = WorkItem(raw_request="test")
        state = GovernanceState(work_item=work_item)
        state.contract = ImplementationContract(
            work_item_id=work_item.id,
            goals=["test"],
            non_goals=["out of scope"],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="basic check",
                    priority="must",
                    verification="manual",
                )
            ],
        )

        run_executor(state)

        store = ArtifactStore(base_dir=tmp_path / "artifacts")
        run_dir = store.save_run(state)

        # candidate.diff must exist in run_dir
        diff_file = run_dir / "candidate.diff"
        assert diff_file.exists(), "candidate.diff not saved to run_dir"
        assert len(diff_file.read_text()) > 0

        # manifest must reference it with a relative path
        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert manifest["candidate_diff"] == "candidate.diff"

        # No absolute paths anywhere in the manifest pointer fields
        for key in (
            "work_item", "contract", "execution_report", "sandbox_report",
            "summary", "candidate_diff", "candidate_patch",
        ):
            val = manifest.get(key)
            if val is not None:
                assert not Path(val).is_absolute(), (
                    f"manifest[{key}] is absolute: {val}"
                )

    def test_failure_still_captures_sandbox_evidence(self, tmp_path):
        from codegate.agents.executor import run_executor, set_executor_adapter
        from codegate.agents import executor as executor_mod

        project_dir = _make_git_project(tmp_path)

        class FailingAdapter(ExecutorAdapter):
            @property
            def name(self):
                return "failing"

            def execute(self, contract, context="", feedback="", work_dir=""):
                raise RuntimeError("simulated executor crash")

        set_executor_adapter(FailingAdapter())
        executor_mod._adapter._project_dir = str(project_dir)

        work_item = WorkItem(raw_request="test")
        state = GovernanceState(work_item=work_item)
        state.contract = ImplementationContract(
            work_item_id=work_item.id,
            goals=["test"],
            non_goals=["out of scope"],
            acceptance_criteria=[
                AcceptanceCriterion(
                    description="basic check",
                    priority="must",
                    verification="manual",
                )
            ],
        )

        run_executor(state)

        # Error must be recorded
        assert state.error is not None
        assert "simulated executor crash" in state.error

        # Sandbox evidence should still be captured (even on failure)
        assert state.sandbox_report is not None
        assert state.sandbox_report.enabled is True
        assert state.sandbox_report.cleanup_status == "preserved"
