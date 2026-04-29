"""Gemini CLI Executor Adapter — delegates code execution to Google's Gemini CLI.

This adapter calls `gemini -p <prompt> -o json` in non-interactive (headless)
mode, collects the file changes it makes, and returns them as an ExecutionReport.

The Gemini CLI must be installed and accessible on PATH.
Install: npm install -g @google/gemini-cli
See: https://github.com/google-gemini/gemini-cli

Key differences from OpenCode adapter:
  - Uses `-p` for headless mode (vs `opencode run`)
  - Uses `-o json` for JSON output (vs `--format json`)
  - Uses `-y` / `--yolo` for auto-approve (vs `--dangerously-skip-permissions`)
  - Runs in CWD (vs `--dir`)
  - Output is a single JSON object (vs NDJSON event stream)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from codegate.adapters.executor import ExecutorAdapter
from codegate.schemas.contract import ImplementationContract
from codegate.schemas.execution import ExecutionReport, ValidationResult

logger = logging.getLogger(__name__)

# Default timeout for gemini CLI (seconds)
DEFAULT_TIMEOUT = 600

IGNORED_DIR_NAMES = {
    ".git",
    ".gemini",
    ".gradle",
    ".idea",
    ".mvn",
    ".pytest_cache",
    ".ruff_cache",
    ".vscode",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
}

IGNORED_FILE_SUFFIXES = {
    ".class",
    ".jar",
    ".pyc",
    ".pyo",
    ".war",
}


class GeminiCLIAdapter(ExecutorAdapter):
    """Adapter that delegates to the Gemini CLI (gemini) via subprocess.

    gemini -p "prompt" -o json [-y] [-m model]

    Parses the JSON output to extract:
    - Response text (summary)
    - Token usage from stats.models
    - Tool call stats from stats.tools
    - File change stats from stats.files

    Actual file changes are detected via git diff (same as OpenCodeAdapter).
    """

    def __init__(
        self,
        model: str = "",
        timeout: int = DEFAULT_TIMEOUT,
        gemini_bin: str = "gemini",
        project_dir: Optional[str] = None,
        use_sandbox: bool = False,
        auto_approve: bool = True,
    ):
        """
        Args:
            model: Model to use (e.g., "gemini-2.5-pro"). Empty = gemini default.
            timeout: Max seconds to wait for gemini to complete.
            gemini_bin: Path to the gemini binary.
            project_dir: If set, run gemini in this directory directly.
            use_sandbox: If True, pass --sandbox flag.
            auto_approve: If True, pass -y (yolo) to auto-approve file writes.
        """
        self._model = model
        self._timeout = timeout
        self._gemini_bin = gemini_bin
        self._project_dir = project_dir
        self._use_sandbox = use_sandbox
        self._auto_approve = auto_approve

    @property
    def name(self) -> str:
        return "gemini"

    def execute(
        self,
        contract: ImplementationContract,
        context: str = "",
        feedback: str = "",
    ) -> ExecutionReport:
        """Execute the contract via Gemini CLI."""

        prompt = self._build_prompt(contract, context, feedback)
        work_dir = self._resolve_work_dir()
        sandbox_created = work_dir != self._project_dir

        logger.info(
            f"Gemini CLI executing in: {work_dir} "
            f"(model={self._model or 'default'}, timeout={self._timeout}s)"
        )

        start = time.time()
        try:
            # Snapshot existing files before execution (for diff detection)
            files_before = self._snapshot_files(work_dir)

            # Run gemini
            raw_output = self._run_gemini(prompt, work_dir)
            elapsed = time.time() - start

            # Parse JSON output
            parsed = self._parse_output(raw_output)

            # Extract results
            summary_text = parsed.get("response", "No response from Gemini CLI.")
            total_tokens = self._extract_tokens(parsed)

            # Detect actual file changes via git
            changed_files: dict[str, str] = {}
            baseline_content: dict[str, str] = {}

            git_result = self._detect_git_changes(work_dir)
            if git_result is not None:
                changed_files, baseline_content = git_result
            else:
                # Fallback: filesystem mtime comparison
                files_after = self._snapshot_files(work_dir)
                changed_files = self._detect_changes_by_mtime(
                    files_before, files_after, work_dir
                )

            # Post-run validation
            validation = self._run_validation(work_dir)

            # Build report
            file_list = list(changed_files.keys())
            code_output = self._format_code_output(changed_files)

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
                executor_name="gemini",
                model_used=self._model or "gemini-default",
                token_usage=total_tokens,
                execution_time_seconds=elapsed,
                validation_result=validation,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            logger.error(f"Gemini CLI timed out after {self._timeout}s")

            # Timeout evidence capture
            changed_files = {}
            baseline_content = {}
            partial_summary = f"Gemini CLI execution timed out after {self._timeout}s"
            try:
                git_result = self._detect_git_changes(work_dir)
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
                    validation = self._run_validation(work_dir)
                except Exception:
                    pass

            file_list = list(changed_files.keys())
            code_output = self._format_code_output(changed_files)

            return ExecutionReport(
                work_item_id="",
                code_output=code_output,
                file_list=file_list,
                files_content=changed_files,
                baseline_content=baseline_content,
                summary=partial_summary,
                unresolved_items=["Execution timed out"],
                executor_name="gemini",
                model_used=self._model or "gemini-default",
                execution_time_seconds=elapsed,
                timed_out=True,
                validation_result=validation,
            )
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"Gemini CLI execution failed: {e}")
            return ExecutionReport(
                work_item_id="",
                code_output="",
                file_list=[],
                summary=f"Gemini CLI execution failed: {e}",
                unresolved_items=[f"Execution error: {e}"],
                executor_name="gemini",
                model_used=self._model or "gemini-default",
                execution_time_seconds=elapsed,
            )
        finally:
            # Clean up sandbox if we created one
            if sandbox_created and work_dir and os.path.exists(work_dir):
                try:
                    shutil.rmtree(work_dir)
                    logger.debug(f"Cleaned up sandbox: {work_dir}")
                except Exception:
                    pass

    # ---- Gemini CLI invocation -----------------------------------------------

    def _resolve_work_dir(self) -> str:
        """Determine which directory to run gemini in."""
        if self._project_dir:
            return self._project_dir
        return os.getcwd()

    def _run_gemini(self, prompt: str, work_dir: str) -> str:
        """Call gemini CLI in headless mode and return raw stdout.

        Uses -y (yolo) to auto-approve file writes by default. The safety
        boundary is the /tmp project copy, not this flag. Real project
        directories should only be used with explicit user intent.
        """
        cmd = [
            self._gemini_bin,
            "-p", prompt,       # non-interactive headless mode
            "-o", "json",       # JSON output
        ]

        if self._auto_approve:
            cmd.append("-y")    # auto-approve all tool calls

        if self._use_sandbox:
            cmd.append("--sandbox")

        if self._model:
            cmd.extend(["-m", self._model])

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
                f"gemini exited with code {result.returncode}: "
                f"{result.stderr[:500]}"
            )

        return result.stdout

    # ---- Output parsing ------------------------------------------------------

    @staticmethod
    def _parse_output(raw: str) -> dict:
        """Parse Gemini CLI JSON output.

        Gemini CLI with -o json returns a single JSON object:
        {
          "session_id": "...",
          "response": "text response",
          "stats": {
            "models": { ... token info per model ... },
            "tools":  { "totalCalls": N, "byName": { ... } },
            "files":  { "totalLinesAdded": N, "totalLinesRemoved": N }
          }
        }
        """
        raw = raw.strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Sometimes there might be stderr mixed in; try to find the JSON
            for line in raw.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            logger.warning(f"Could not parse gemini output: {raw[:200]}")
            return {"response": raw}

    @staticmethod
    def _extract_tokens(parsed: dict) -> int:
        """Sum total tokens across all models from stats."""
        total = 0
        stats = parsed.get("stats", {})
        models = stats.get("models", {})
        for model_name, model_stats in models.items():
            tokens = model_stats.get("tokens", {})
            total += tokens.get("total", 0)
        return total

    # ---- Prompt construction -------------------------------------------------

    @staticmethod
    def _build_prompt(
        contract: ImplementationContract,
        context: str,
        feedback: str,
    ) -> str:
        """Build the gemini prompt from the contract.

        We let gemini use its native file-writing tools (write_file, etc.).
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

    # ---- File change detection -----------------------------------------------
    # These methods are shared with OpenCodeAdapter. In the future they
    # should be extracted to a common mixin/utility module.

    def _snapshot_files(self, work_dir: str) -> dict[str, float]:
        """Take a snapshot of files and their mtimes for change detection."""
        snapshot = {}
        for root, _, files in os.walk(work_dir):
            if self._is_ignored_path(root, work_dir):
                continue
            for f in files:
                path = os.path.join(root, f)
                if self._is_ignored_path(path, work_dir):
                    continue
                try:
                    snapshot[path] = os.path.getmtime(path)
                except OSError:
                    pass
        return snapshot

    def _detect_changes_by_mtime(
        self,
        before: dict[str, float],
        after: dict[str, float],
        work_dir: str,
    ) -> dict[str, str]:
        """Detect file changes using mtime comparison (fallback when not git)."""
        changed = {}
        for path, mtime in after.items():
            if path not in before or before[path] != mtime:
                rel = self._make_relative(path, work_dir)
                if self._is_ignored_relative_path(rel):
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        changed[rel] = f.read()
                except Exception:
                    changed[rel] = "<binary or unreadable>"
        return changed

    def _detect_git_changes(
        self, work_dir: str
    ) -> tuple[dict[str, str], dict[str, str]] | None:
        """Return git-visible changes + baseline content when work dir is git repo.

        Returns (changed_files, baseline_content) where:
        - changed_files: filepath → current content
        - baseline_content: filepath → content at HEAD (only for MODIFIED files)
        """
        prefix_result = subprocess.run(
            ["git", "-C", work_dir, "rev-parse", "--show-prefix"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if prefix_result.returncode != 0:
            return None
        git_prefix = prefix_result.stdout.strip()

        result = subprocess.run(
            [
                "git",
                "-C",
                work_dir,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "-z",
            ],
            capture_output=True,
            text=False,
            timeout=15,
        )
        if result.returncode != 0:
            logger.debug("git status failed; falling back to filesystem diff")
            return None

        entries = self._parse_git_status_entries(result.stdout)
        changed: dict[str, str] = {}
        baseline: dict[str, str] = {}
        for status, rel in entries:
            if git_prefix and rel.startswith(git_prefix):
                git_rel = rel
                project_rel = rel[len(git_prefix):]
            else:
                git_rel = f"{git_prefix}{rel}"
                project_rel = rel

            if self._is_ignored_relative_path(project_rel):
                continue
            abs_path = Path(work_dir) / project_rel
            if not abs_path.exists():
                changed[project_rel] = "<deleted>"
                continue
            try:
                changed[project_rel] = abs_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                changed[project_rel] = "<binary or unreadable>"

            # For MODIFIED files (not new/untracked), capture baseline from HEAD
            if status.strip() and not status.strip().startswith("?"):
                try:
                    head_result = subprocess.run(
                        ["git", "-C", work_dir, "show", f"HEAD:{git_rel}"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if head_result.returncode == 0:
                        baseline[project_rel] = head_result.stdout
                except Exception:
                    pass  # New file or error — no baseline

        return changed, baseline

    @staticmethod
    def _parse_git_status_entries(raw: bytes) -> list[tuple[str, str]]:
        """Parse `git status --porcelain=v1 -z` into (status, path) tuples."""
        entries = []
        parts = [p for p in raw.split(b"\0") if p]
        i = 0
        while i < len(parts):
            entry = parts[i].decode("utf-8", errors="replace")
            status = entry[:2]
            path = entry[3:]
            if status.startswith("R") or status.startswith("C"):
                i += 1
            if path:
                entries.append((status, path))
            i += 1
        return entries

    # ---- Post-run validation -------------------------------------------------

    _VALIDATION_TIMEOUT = 120  # seconds

    def _run_validation(self, work_dir: str) -> ValidationResult | None:
        """Auto-detect project type and run validation (mvn test / npm test).

        Returns None if project type is not detected.
        """
        project_type, cmd = self._detect_project_type(work_dir)
        if project_type is None:
            return None

        logger.info(f"Running post-run validation: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._VALIDATION_TIMEOUT,
                cwd=work_dir,
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(
                type=project_type,
                command=" ".join(cmd),
                exit_code=-1,
                passed=False,
                error_summary=f"Validation timed out after {self._VALIDATION_TIMEOUT}s",
            )
        except Exception as e:
            return ValidationResult(
                type=project_type,
                command=" ".join(cmd),
                exit_code=-1,
                passed=False,
                error_summary=str(e),
            )

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        combined = stdout + "\n" + stderr

        passed = result.returncode == 0
        error_summary = None
        tests_run = 0
        tests_failed = 0

        if project_type == "maven":
            tests_run, tests_failed, error_summary = (
                self._parse_maven_output(combined, passed)
            )
        elif project_type == "npm":
            tests_run, tests_failed, error_summary = (
                self._parse_npm_output(combined, passed)
            )

        # Keep last 30 lines for diagnostics
        stdout_tail = "\n".join(combined.strip().split("\n")[-30:])

        return ValidationResult(
            type=project_type,
            command=" ".join(cmd),
            exit_code=result.returncode,
            passed=passed,
            error_summary=error_summary,
            tests_run=tests_run,
            tests_failed=tests_failed,
            stdout_tail=stdout_tail,
        )

    @staticmethod
    def _detect_project_type(work_dir: str) -> tuple[str | None, list[str]]:
        """Detect project type from build files."""
        p = Path(work_dir)
        if (p / "pom.xml").exists():
            return "maven", ["mvn", "test", "-B"]
        if (p / "build.gradle").exists() or (p / "build.gradle.kts").exists():
            return "gradle", ["./gradlew", "test", "--no-daemon"]
        if (p / "package.json").exists():
            return "npm", ["npm", "test"]
        return None, []

    @staticmethod
    def _parse_maven_output(
        output: str, passed: bool
    ) -> tuple[int, int, str | None]:
        """Parse Maven test output for counts and error summary."""
        import re

        tests_run = 0
        tests_failed = 0
        error_summary = None

        for match in re.finditer(
            r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)", output
        ):
            tests_run = int(match.group(1))
            tests_failed = int(match.group(2)) + int(match.group(3))

        if not passed and not error_summary:
            error_lines = []
            for line in output.split("\n"):
                if "[ERROR]" in line and (
                    "不存在" in line
                    or "找不到" in line
                    or "cannot find" in line
                    or "does not exist" in line
                    or "Compilation failure" in line
                ):
                    error_lines.append(line.strip())
            if error_lines:
                error_summary = "\n".join(error_lines[:5])
            else:
                for line in output.split("\n"):
                    if line.strip().startswith("[ERROR]") and len(line.strip()) > 10:
                        error_summary = line.strip()
                        break

        return tests_run, tests_failed, error_summary

    @staticmethod
    def _parse_npm_output(
        output: str, passed: bool
    ) -> tuple[int, int, str | None]:
        """Parse npm test output for counts and error summary."""
        import re

        tests_run = 0
        tests_failed = 0
        error_summary = None

        m = re.search(r"(\d+)\s+passing", output)
        if m:
            tests_run = int(m.group(1))
        m = re.search(r"(\d+)\s+failing", output)
        if m:
            tests_failed = int(m.group(1))
            tests_run += tests_failed

        if not passed and not error_summary:
            for line in output.split("\n"):
                if "Error:" in line or "FAIL" in line:
                    error_summary = line.strip()
                    break

        return tests_run, tests_failed, error_summary

    # ---- Path helpers --------------------------------------------------------

    def _is_ignored_path(self, path: str, base: str) -> bool:
        """Return True when a filesystem path should not enter evidence."""
        return self._is_ignored_relative_path(self._make_relative(path, base))

    @staticmethod
    def _is_ignored_relative_path(path: str) -> bool:
        normalized = path.replace("\\", "/")
        parts = [p for p in normalized.split("/") if p]
        if any(part in IGNORED_DIR_NAMES for part in parts):
            return True
        return any(normalized.endswith(suffix) for suffix in IGNORED_FILE_SUFFIXES)

    @staticmethod
    def _make_relative(filepath: str, base: str) -> str:
        """Convert absolute path to relative path from base."""
        try:
            return str(Path(filepath).relative_to(base))
        except ValueError:
            # Handle /private/tmp vs /tmp on macOS
            try:
                return str(Path(filepath).relative_to(f"/private{base}"))
            except ValueError:
                return filepath

    @staticmethod
    def _format_code_output(files: dict[str, str]) -> str:
        """Format files into a single code_output string for review."""
        if not files:
            return ""
        parts = []
        for path, content in sorted(files.items()):
            parts.append(f"=== {path} ===\n{content}")
        return "\n\n".join(parts)
