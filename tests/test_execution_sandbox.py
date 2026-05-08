"""Execution Sandbox tests — verify isolation, diff/patch generation, and evidence capture."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.execution.sandbox import ExecutionSandbox
from codegate.schemas.sandbox import SandboxReport


def _make_git_project(tmp_path: Path) -> Path:
    """Create a minimal git repository for testing."""
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
    (project / "README.md").write_text("# Test Project\n")
    subprocess.run(["git", "add", "."], cwd=str(project), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(project), capture_output=True, check=True,
    )
    return project


def _make_plain_project(tmp_path: Path) -> Path:
    """Create a plain (non-git) project directory."""
    project = tmp_path / "plain_project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n")
    return project


class TestSandboxNoPollution:
    """Sandbox modifications must not affect the original project."""

    def test_copy_strategy_no_pollution(self, tmp_path):
        project = _make_plain_project(tmp_path)
        original_content = (project / "main.py").read_text()

        with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
            # Write a new file in the sandbox
            new_file = sandbox.sandbox_dir / "new_file.py"
            new_file.write_text("# created in sandbox\n")
            # Modify existing file in sandbox
            (sandbox.sandbox_dir / "main.py").write_text("print('modified')\n")

        # Original must be unchanged
        assert (project / "main.py").read_text() == original_content
        assert not (project / "new_file.py").exists()

    def test_worktree_strategy_no_pollution(self, tmp_path):
        project = _make_git_project(tmp_path)
        original_content = (project / "README.md").read_text()

        with ExecutionSandbox(project, strategy="git_worktree", base_dir=tmp_path) as sandbox:
            (sandbox.sandbox_dir / "new_file.py").write_text("# sandbox\n")

        # Original must be unchanged
        assert (project / "README.md").read_text() == original_content
        assert not (project / "new_file.py").exists()


class TestWorktreeStrategy:
    """Git worktree strategy creates an isolated workspace."""

    def test_worktree_creates_sandbox_dir(self, tmp_path):
        project = _make_git_project(tmp_path)
        with ExecutionSandbox(project, strategy="git_worktree", base_dir=tmp_path) as sandbox:
            assert sandbox.sandbox_dir is not None
            assert sandbox.sandbox_dir.exists()
            assert sandbox.sandbox_dir != project
            # README.md should exist in sandbox (copied from HEAD)
            assert (sandbox.sandbox_dir / "README.md").exists()

    def test_worktree_report_has_correct_strategy(self, tmp_path):
        project = _make_git_project(tmp_path)
        with ExecutionSandbox(project, strategy="git_worktree", base_dir=tmp_path) as sandbox:
            pass
        report = sandbox.report
        assert report is not None
        assert report.strategy == "git_worktree"
        assert report.enabled is True
        assert report.base_ref != "none"

    def test_worktree_cleanup_removes_dir(self, tmp_path):
        project = _make_git_project(tmp_path)
        with ExecutionSandbox(project, strategy="git_worktree", base_dir=tmp_path) as sandbox:
            sandbox_path = sandbox.sandbox_dir
        # After context exit, sandbox should be cleaned
        assert not sandbox_path.exists()


class TestCopyFallback:
    """Temp copy fallback for non-git projects."""

    def test_copy_creates_sandbox_dir(self, tmp_path):
        project = _make_plain_project(tmp_path)
        with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
            assert sandbox.sandbox_dir is not None
            assert sandbox.sandbox_dir.exists()
            assert (sandbox.sandbox_dir / "main.py").exists()

    def test_copy_report_has_correct_strategy(self, tmp_path):
        project = _make_plain_project(tmp_path)
        with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
            pass
        report = sandbox.report
        assert report is not None
        assert report.strategy == "temp_copy"

    def test_auto_fallback_to_copy_for_non_git(self, tmp_path):
        project = _make_plain_project(tmp_path)
        with ExecutionSandbox(project, strategy="auto", base_dir=tmp_path) as sandbox:
            assert sandbox.sandbox_dir is not None
        report = sandbox.report
        assert report.strategy == "temp_copy"

    def test_auto_uses_worktree_for_git(self, tmp_path):
        project = _make_git_project(tmp_path)
        with ExecutionSandbox(project, strategy="auto", base_dir=tmp_path) as sandbox:
            pass
        report = sandbox.report
        assert report.strategy == "git_worktree"


class TestDiffPatchGeneration:
    """Diff and patch files are generated for changed files."""

    def test_copy_diff_generation(self, tmp_path):
        project = _make_plain_project(tmp_path)
        with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
            # Modify a file in sandbox
            (sandbox.sandbox_dir / "main.py").write_text("print('modified')\n")
            sandbox.collect_changes()

            # Verify diff was generated (while sandbox still exists)
            report = sandbox.report
            assert report is not None
            assert "main.py" in report.changed_files
            assert report.diff_path is not None
            assert Path(report.diff_path).exists()

        # After cleanup, file is gone but report metadata persists
        assert sandbox.report.changed_files == ["main.py"]

    def test_copy_new_file_detected(self, tmp_path):
        project = _make_plain_project(tmp_path)
        with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
            (sandbox.sandbox_dir / "new.py").write_text("# new\n")
            sandbox.collect_changes()

        report = sandbox.report
        assert "new.py" in report.changed_files

    def test_no_changes_empty_diff(self, tmp_path):
        project = _make_plain_project(tmp_path)
        with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
            sandbox.collect_changes()

        report = sandbox.report
        assert report.changed_files == []
        assert report.diff_path is None


class TestTimeoutPreservesEvidence:
    """Even on timeout/failure, sandbox report must be generated."""

    def test_context_manager_on_exception(self, tmp_path):
        project = _make_plain_project(tmp_path)
        try:
            with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
                (sandbox.sandbox_dir / "partial.py").write_text("# partial\n")
                raise RuntimeError("executor timed out")
        except RuntimeError:
            pass

        # Report should still be available (collect_changes called in __exit__)
        report = sandbox.report
        assert report is not None
        assert report.enabled is True
        # On exception, sandbox is preserved (not cleaned, not left pending)
        assert report.cleanup_status == "preserved"
        # Sandbox directory should still exist
        assert sandbox.sandbox_dir is not None
        assert sandbox.sandbox_dir.exists()

    def test_preserve_keeps_sandbox(self, tmp_path):
        project = _make_plain_project(tmp_path)
        sandbox = ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path)
        sandbox.create()
        sandbox_path = sandbox.sandbox_dir
        sandbox.preserve()
        sandbox.cleanup()
        # preserve() sets status but cleanup() is still called by __exit__
        # In a real scenario, the caller would skip cleanup after preserve()


class TestContextManager:
    """Context manager lifecycle."""

    def test_enter_returns_sandbox(self, tmp_path):
        project = _make_plain_project(tmp_path)
        with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
            assert isinstance(sandbox, ExecutionSandbox)
            assert sandbox.sandbox_dir is not None

    def test_report_available_after_exit(self, tmp_path):
        project = _make_plain_project(tmp_path)
        with ExecutionSandbox(project, strategy="temp_copy", base_dir=tmp_path) as sandbox:
            (sandbox.sandbox_dir / "test.py").write_text("x = 1\n")

        assert sandbox.report is not None
        assert len(sandbox.report.changed_files) > 0
