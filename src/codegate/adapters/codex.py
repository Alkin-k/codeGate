"""Codex CLI Executor Adapter — delegates code execution to OpenAI's Codex CLI.

This adapter calls `codex exec <prompt>` in non-interactive (headless) mode,
collects the file changes it makes, and returns them as an ExecutionReport.

The Codex CLI must be installed and accessible on PATH.
Install: npm install -g @openai/codex
See: https://github.com/openai/codex

Key differences from Gemini CLI adapter:
  - Uses `codex exec "prompt"` for headless mode (vs `gemini -p "prompt"`)
  - Uses `--full-auto` for non-interactive low-friction execution (vs `-y`)
  - Progress streams to stderr, final result to stdout
  - No structured JSON output with token stats (unlike gemini -o json)
  - File changes detected via git diff (same as other adapters)

Environment:
  - OPENAI_API_KEY must be set (or configured in ~/.codex/config.toml)
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import time
from typing import Optional

from codegate.adapters.executor import ExecutorAdapter
from codegate.adapters._file_detection import (
    snapshot_files,
    detect_git_changes,
    detect_changes_by_mtime,
    format_code_output,
    run_validation,
)
from codegate.schemas.contract import ImplementationContract
from codegate.schemas.execution import ExecutionReport

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 600


class CodexCLIAdapter(ExecutorAdapter):
    """Adapter that delegates to the Codex CLI (codex exec) via subprocess.

    codex exec [--full-auto] [--model model] "prompt"

    Actual file changes are detected via git diff (same as GeminiCLIAdapter).
    """

    def __init__(
        self,
        model: str = "",
        timeout: int = DEFAULT_TIMEOUT,
        codex_bin: str = "codex",
        project_dir: Optional[str] = None,
        approval_mode: str = "full-auto",
    ):
        """
        Args:
            model: Model to use (e.g., "o4-mini", "gpt-4.1"). Empty = codex default.
            timeout: Max seconds to wait for codex to complete.
            codex_bin: Path to the codex binary.
            project_dir: If set, run codex in this directory directly.
            approval_mode: Execution mode for file writes:
                "suggest" — no auto flag; Codex may stop for approval
                "auto-edit" — compatibility alias for "full-auto"
                "full-auto" — pass --full-auto (default for governance)
        """
        self._model = model
        self._timeout = timeout
        self._codex_bin = self._resolve_codex_bin(codex_bin)
        self._project_dir = project_dir
        self._approval_mode = approval_mode

    @property
    def name(self) -> str:
        return "codex"

    def execute(
        self,
        contract: ImplementationContract,
        context: str = "",
        feedback: str = "",
    ) -> ExecutionReport:
        """Execute the contract via Codex CLI."""

        prompt = self._build_prompt(contract, context, feedback)
        work_dir = self._resolve_work_dir()

        logger.info(
            f"Codex CLI executing in: {work_dir} "
            f"(model={self._model or 'default'}, timeout={self._timeout}s)"
        )

        start = time.time()
        try:
            # Snapshot existing files before execution (for diff detection)
            files_before = snapshot_files(work_dir)

            # Run codex
            raw_output = self._run_codex(prompt, work_dir)
            elapsed = time.time() - start

            # Detect actual file changes via git
            changed_files: dict[str, str] = {}
            baseline_content: dict[str, str] = {}

            git_result = detect_git_changes(work_dir)
            if git_result is not None:
                changed_files, baseline_content = git_result
            else:
                # Fallback: filesystem mtime comparison
                files_after = snapshot_files(work_dir)
                changed_files = detect_changes_by_mtime(
                    files_before, files_after, work_dir
                )

            # Post-run validation
            validation = run_validation(work_dir)

            # Build report
            file_list = list(changed_files.keys())
            code_output = format_code_output(changed_files)

            # Extract summary from stdout (codex exec streams result to stdout)
            summary_text = raw_output.strip() if raw_output else "No output from Codex CLI."
            # Truncate very long output to avoid bloating the report
            if len(summary_text) > 5000:
                summary_text = summary_text[:5000] + "\n... (truncated)"

            return ExecutionReport(
                work_item_id="",  # filled by caller
                code_output=code_output,
                file_list=file_list,
                files_content=changed_files,
                baseline_content=baseline_content,
                summary=summary_text,
                goals_addressed=[],
                unresolved_items=[],
                self_reported_risks=[],
                executor_name="codex",
                model_used=self._model or "codex-default",
                token_usage=0,  # Codex CLI doesn't report token usage in stdout
                execution_time_seconds=elapsed,
                validation_result=validation,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            logger.error(f"Codex CLI timed out after {self._timeout}s")

            # Timeout evidence capture
            changed_files = {}
            baseline_content = {}
            partial_summary = f"Codex CLI execution timed out after {self._timeout}s"
            try:
                git_result = detect_git_changes(work_dir)
                if git_result:
                    changed_files, baseline_content = git_result
                if changed_files:
                    logger.info(
                        f"Timeout evidence: found {len(changed_files)} changed "
                        f"file(s) on disk after timeout"
                    )
                    partial_summary += (
                        f". However, {len(changed_files)} file(s) were already "
                        f"written to disk: {list(changed_files.keys())}"
                    )
            except Exception as cap_err:
                logger.debug(f"Failed to capture timeout evidence: {cap_err}")

            # Post-run validation (may catch compile errors from partial writes)
            validation = None
            if changed_files:
                try:
                    validation = run_validation(work_dir)
                except Exception:
                    pass

            file_list = list(changed_files.keys())
            code_output = format_code_output(changed_files)

            return ExecutionReport(
                work_item_id="",
                code_output=code_output,
                file_list=file_list,
                files_content=changed_files,
                baseline_content=baseline_content,
                summary=partial_summary,
                unresolved_items=["Execution timed out"],
                executor_name="codex",
                model_used=self._model or "codex-default",
                execution_time_seconds=elapsed,
                timed_out=True,
                validation_result=validation,
            )
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"Codex CLI execution failed: {e}")
            return ExecutionReport(
                work_item_id="",
                code_output="",
                file_list=[],
                summary=f"Codex CLI execution failed: {e}",
                unresolved_items=[f"Execution error: {e}"],
                executor_name="codex",
                model_used=self._model or "codex-default",
                execution_time_seconds=elapsed,
            )

    # ---- Codex CLI invocation ------------------------------------------------

    def _resolve_work_dir(self) -> str:
        """Determine which directory to run codex in."""
        if self._project_dir:
            return self._project_dir
        return os.getcwd()

    @classmethod
    def _resolve_codex_bin(cls, codex_bin: str) -> str:
        """Resolve the default codex binary while skipping broken shims.

        Some local installations can leave an older Homebrew shim first on PATH
        with a shebang that points at a deleted Node runtime. subprocess would
        try that shim first and fail before reaching a healthy npm/nvm install.
        """
        if codex_bin != "codex" or os.path.sep in codex_bin:
            return codex_bin

        seen: set[str] = set()
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            if not path_dir:
                continue
            candidate = os.path.join(path_dir, codex_bin)
            if candidate in seen:
                continue
            seen.add(candidate)
            if not os.path.isfile(candidate) or not os.access(candidate, os.X_OK):
                continue
            if cls._has_usable_shebang(candidate):
                return candidate

        return codex_bin

    @staticmethod
    def _has_usable_shebang(path: str) -> bool:
        """Return False for scripts whose shebang interpreter is missing."""
        try:
            with open(path, "rb") as f:
                first_line = f.readline(256)
        except OSError:
            return False

        if not first_line.startswith(b"#!"):
            return True

        try:
            shebang = first_line[2:].decode("utf-8", errors="ignore").strip()
        except UnicodeDecodeError:
            return True

        if not shebang:
            return False

        parts = shlex.split(shebang)
        if not parts:
            return False

        interpreter = parts[0]
        if os.path.basename(interpreter) == "env" and len(parts) > 1:
            return shutil.which(parts[1]) is not None
        if os.path.isabs(interpreter):
            return os.path.exists(interpreter) and os.access(interpreter, os.X_OK)
        return True

    def _run_codex(self, prompt: str, work_dir: str) -> str:
        """Call codex CLI in headless mode and return raw stdout.

        Uses `codex exec` for non-interactive mode. Current Codex CLI
        exposes --full-auto rather than the older --approval-mode flag.
        """
        cmd = [
            self._codex_bin,
            "exec",             # non-interactive headless mode
        ]

        if self._approval_mode in ("auto-edit", "full-auto"):
            cmd.append("--full-auto")

        cmd.append("--skip-git-repo-check")

        if self._model:
            cmd.extend(["--model", self._model])

        cmd.append(prompt)

        logger.debug(f"Running: {' '.join(cmd[:5])}...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self._timeout,
            cwd=work_dir,
        )

        if result.returncode != 0 and not result.stdout:
            raise RuntimeError(
                f"codex exited with code {result.returncode}: "
                f"{result.stderr[:500]}"
            )

        return result.stdout

    # ---- Prompt construction -------------------------------------------------

    @staticmethod
    def _build_prompt(
        contract: ImplementationContract,
        context: str,
        feedback: str,
    ) -> str:
        """Build the codex prompt from the contract.

        We let codex use its native file-writing tools.
        No JSON output requested from the LLM itself.
        """
        parts = [
            "## Implementation Contract (APPROVED)\n",
            "You MUST implement the following contract exactly as specified.\n",
            "### Goals",
        ]
        for i, g in enumerate(contract.goals):
            parts.append(f"{i + 1}. {g}")

        parts.append("\n### Non-Goals (DO NOT implement these)")
        for ng in contract.non_goals:
            parts.append(f"- ❌ {ng}")

        parts.append("\n### Acceptance Criteria")
        for i, ac in enumerate(contract.acceptance_criteria):
            parts.append(f"{i + 1}. [{ac.priority.upper()}] {ac.description}")
            parts.append(f"   Verification: {ac.verification}")

        if contract.constraints:
            parts.append("\n### Constraints")
            for c in contract.constraints:
                parts.append(f"- {c}")

        if contract.required_tests:
            parts.append("\n### Required Tests")
            for t in contract.required_tests:
                parts.append(f"- {t}")

        if context:
            parts.append(f"\n### Project Context\n\n{context}")

        if feedback:
            parts.append(
                f"\n### Previous Review Feedback\n\n"
                f"Your previous implementation was rejected. "
                f"Fix these issues:\n{feedback}"
            )

        parts.append(
            "\n## Instructions\n\n"
            "Implement the contract above by creating/modifying files. "
            "Use your file writing tools to create all necessary files. "
            "Do NOT skip any acceptance criteria."
        )

        return "\n".join(parts)
