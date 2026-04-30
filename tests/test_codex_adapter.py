"""Tests for Codex CLI Adapter.

Tests are fully mocked — no actual Codex CLI or API key required.
"""

from __future__ import annotations

import json
import os
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codegate.adapters.codex import CodexCLIAdapter
from codegate.schemas.contract import (
    ImplementationContract,
    AcceptanceCriterion,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_contract(**overrides) -> ImplementationContract:
    """Create a minimal ImplementationContract for testing."""
    defaults = {
        "work_item_id": "test-work-item-001",
        "goals": ["Add guest mode with scoped access"],
        "non_goals": ["Do not add admin bypass"],
        "acceptance_criteria": [
            AcceptanceCriterion(
                description="Guest users can access public pages",
                verification="Check route meta has guest: true",
                priority="must",
            ),
        ],
        "constraints": ["Do not modify auth guard logic"],
        "required_tests": [],
    }
    defaults.update(overrides)
    return ImplementationContract(**defaults)


@pytest.fixture
def adapter():
    """Create a CodexCLIAdapter with defaults."""
    return CodexCLIAdapter(
        model="o4-mini",
        timeout=60,
        project_dir="/tmp/test-project",
    )


@pytest.fixture
def contract():
    return _make_contract()


# ---------------------------------------------------------------------------
# Unit tests: prompt construction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    """Test _build_prompt generates correct prompt format."""

    def test_prompt_contains_goals(self, contract):
        prompt = CodexCLIAdapter._build_prompt(contract, "", "")
        assert "Add guest mode with scoped access" in prompt

    def test_prompt_contains_non_goals(self, contract):
        prompt = CodexCLIAdapter._build_prompt(contract, "", "")
        assert "❌ Do not add admin bypass" in prompt

    def test_prompt_contains_acceptance_criteria(self, contract):
        prompt = CodexCLIAdapter._build_prompt(contract, "", "")
        assert "[MUST]" in prompt
        assert "Guest users can access public pages" in prompt

    def test_prompt_contains_constraints(self, contract):
        prompt = CodexCLIAdapter._build_prompt(contract, "", "")
        assert "Do not modify auth guard logic" in prompt

    def test_prompt_includes_context(self, contract):
        prompt = CodexCLIAdapter._build_prompt(
            contract, "Vue.js 3 + TypeScript project", ""
        )
        assert "Vue.js 3 + TypeScript project" in prompt

    def test_prompt_includes_feedback(self, contract):
        prompt = CodexCLIAdapter._build_prompt(
            contract, "", "Fix the auth guard bypass issue"
        )
        assert "Fix the auth guard bypass issue" in prompt
        assert "Previous Review Feedback" in prompt


# ---------------------------------------------------------------------------
# Unit tests: CLI invocation (mocked subprocess)
# ---------------------------------------------------------------------------


class TestCodexExecution:
    """Test execute() with mocked subprocess."""

    @patch("codegate.adapters.codex.run_validation", return_value=None)
    @patch("codegate.adapters.codex.detect_git_changes")
    @patch("subprocess.run")
    def test_successful_execution(
        self, mock_run, mock_git, mock_val, adapter, contract
    ):
        """Test normal successful execution path."""
        # Mock codex CLI output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Successfully implemented guest mode.",
            stderr="",
        )

        # Mock git changes
        mock_git.return_value = (
            {"src/router/index.ts": "const router = ..."},
            {"src/router/index.ts": "const oldRouter = ..."},
        )

        report = adapter.execute(contract, context="Vue.js project")

        assert report.executor_name == "codex"
        assert report.model_used == "o4-mini"
        assert report.file_list == ["src/router/index.ts"]
        assert "router" in report.code_output
        assert report.files_content == {"src/router/index.ts": "const router = ..."}
        assert report.baseline_content == {"src/router/index.ts": "const oldRouter = ..."}
        assert not report.timed_out

    @patch("codegate.adapters.codex.run_validation", return_value=None)
    @patch("codegate.adapters.codex.detect_git_changes", return_value=None)
    @patch("codegate.adapters.codex.detect_changes_by_mtime")
    @patch("codegate.adapters.codex.snapshot_files")
    @patch("subprocess.run")
    def test_fallback_to_mtime(
        self, mock_run, mock_snap, mock_mtime, mock_git, mock_val,
        adapter, contract
    ):
        """Test fallback to mtime detection when not in git repo."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Done.", stderr=""
        )
        mock_snap.side_effect = [{}, {"file.txt": 12345.0}]
        mock_mtime.return_value = {"file.txt": "content"}

        report = adapter.execute(contract)

        assert report.file_list == ["file.txt"]
        assert mock_mtime.called

    @patch("codegate.adapters.codex.detect_git_changes")
    @patch("subprocess.run")
    def test_timeout_captures_evidence(
        self, mock_run, mock_git, adapter, contract
    ):
        """Test timeout path captures partial file changes."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="codex", timeout=60
        )
        mock_git.return_value = (
            {"partial.ts": "partial content"},
            {},
        )

        report = adapter.execute(contract)

        assert report.timed_out is True
        assert "timed out" in report.summary
        assert report.file_list == ["partial.ts"]
        assert "Execution timed out" in report.unresolved_items

    @patch("subprocess.run")
    def test_execution_failure(self, mock_run, adapter, contract):
        """Test error handling when codex CLI fails."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: OPENAI_API_KEY not set",
        )

        report = adapter.execute(contract)

        assert "failed" in report.summary.lower()
        assert report.file_list == []

    @patch("codegate.adapters.codex.run_validation", return_value=None)
    @patch("codegate.adapters.codex.detect_git_changes")
    @patch("subprocess.run")
    def test_command_construction(
        self, mock_run, mock_git, mock_val, adapter, contract
    ):
        """Test that the correct command is constructed."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="OK", stderr=""
        )
        mock_git.return_value = ({}, {})

        adapter.execute(contract)

        # Check the subprocess.run call
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "codex" or cmd[0].endswith("/codex")
        assert cmd[1] == "exec"
        assert "--full-auto" in cmd
        assert "--skip-git-repo-check" in cmd
        assert "--model" in cmd
        assert "o4-mini" in cmd
        assert cmd[-1].startswith("## Implementation Contract")
        assert call_args[1]["cwd"] == "/tmp/test-project"
        assert call_args[1]["timeout"] == 60

    @patch("codegate.adapters.codex.run_validation", return_value=None)
    @patch("codegate.adapters.codex.detect_git_changes")
    @patch("subprocess.run")
    def test_no_model_flag_when_empty(
        self, mock_run, mock_git, mock_val, contract
    ):
        """Test that --model is not passed when model is empty."""
        adapter = CodexCLIAdapter(project_dir="/tmp/test")
        mock_run.return_value = MagicMock(
            returncode=0, stdout="OK", stderr=""
        )
        mock_git.return_value = ({}, {})

        adapter.execute(contract)

        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    @patch("codegate.adapters.codex.run_validation", return_value=None)
    @patch("codegate.adapters.codex.detect_git_changes")
    @patch("subprocess.run")
    def test_long_output_truncated(
        self, mock_run, mock_git, mock_val, adapter, contract
    ):
        """Test that very long stdout is truncated."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="x" * 10000,
            stderr="",
        )
        mock_git.return_value = ({}, {})

        report = adapter.execute(contract)

        assert len(report.summary) < 6000
        assert "truncated" in report.summary


class TestAdapterProperties:
    """Test adapter basic properties."""

    def test_name(self, adapter):
        assert adapter.name == "codex"

    def test_default_approval_mode(self):
        adapter = CodexCLIAdapter()
        assert adapter._approval_mode == "full-auto"

    def test_custom_approval_mode(self):
        adapter = CodexCLIAdapter(approval_mode="suggest")
        assert adapter._approval_mode == "suggest"

    def test_resolve_work_dir_with_project(self, adapter):
        assert adapter._resolve_work_dir() == "/tmp/test-project"

    def test_resolve_work_dir_default(self):
        adapter = CodexCLIAdapter()
        assert adapter._resolve_work_dir() == os.getcwd()

    def test_default_codex_bin_skips_broken_shebang(self, tmp_path, monkeypatch):
        broken_dir = tmp_path / "broken"
        good_dir = tmp_path / "good"
        broken_dir.mkdir()
        good_dir.mkdir()

        broken = broken_dir / "codex"
        broken.write_text("#!/missing/node\nconsole.log('broken')\n")
        broken.chmod(0o755)

        good = good_dir / "codex"
        good.write_text("#!/usr/bin/env node\nconsole.log('good')\n")
        good.chmod(0o755)

        monkeypatch.setenv("PATH", f"{broken_dir}{os.pathsep}{good_dir}")
        monkeypatch.setattr(
            "codegate.adapters.codex.shutil.which",
            lambda name: "/usr/bin/node" if name == "node" else None,
        )

        adapter = CodexCLIAdapter()

        assert adapter._codex_bin == str(good)
