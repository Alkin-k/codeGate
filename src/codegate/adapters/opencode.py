"""OpenCode Executor Adapter — delegates code execution to the opencode CLI.

This adapter calls `opencode run` in non-interactive (headless) mode,
collects the file changes it makes, and returns them as an ExecutionReport.

The opencode CLI must be installed and accessible on PATH.
See: https://github.com/opencode-ai/opencode

IMPORTANT: opencode with --dangerously-skip-permissions will auto-approve
all file operations. Run only in sandboxed/non-production directories.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from codegate.adapters.executor import ExecutorAdapter
from codegate.schemas.contract import ImplementationContract
from codegate.schemas.execution import ExecutionReport, ValidationResult

logger = logging.getLogger(__name__)

# Default timeout for opencode run (seconds)
DEFAULT_TIMEOUT = 300

IGNORED_DIR_NAMES = {
    ".git",
    ".opencode",
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


class OpenCodeAdapter(ExecutorAdapter):
    """Adapter that delegates to the opencode CLI via subprocess.

    opencode run "prompt" --format json --dir <sandbox>
    --dangerously-skip-permissions

    Parses the JSON event stream to extract:
    - File writes (tool_use with tool=write)
    - Text summaries
    - Token usage from step_finish events
    """

    def __init__(
        self,
        model: str = "",
        timeout: int = DEFAULT_TIMEOUT,
        opencode_bin: str = "opencode",
        project_dir: Optional[str] = None,
        use_sandbox: bool = True,
    ):
        """
        Args:
            model: Model to use (e.g., "kimi-for-coding/k2p6"). Empty = opencode default.
            timeout: Max seconds to wait for opencode to complete.
            opencode_bin: Path to the opencode binary.
            project_dir: If set, run opencode in this directory directly
                         (use_sandbox is ignored).
            use_sandbox: If True, create a temp sandbox dir. If False, use CWD.
        """
        self._model = model
        self._timeout = timeout
        self._opencode_bin = opencode_bin
        self._project_dir = project_dir
        self._use_sandbox = use_sandbox

    @property
    def name(self) -> str:
        return "opencode"

    def execute(
        self,
        contract: ImplementationContract,
        context: str = "",
        feedback: str = "",
    ) -> ExecutionReport:
        """Execute the contract via opencode CLI."""

        prompt = self._build_prompt(contract, context, feedback)
        work_dir = self._resolve_work_dir()
        sandbox_created = work_dir != self._project_dir

        logger.info(
            f"OpenCode executing in: {work_dir} "
            f"(model={self._model or 'default'}, timeout={self._timeout}s)"
        )

        start = time.time()
        try:
            # Snapshot existing files before execution (for diff detection)
            files_before = self._snapshot_files(work_dir)

            # Run opencode
            raw_output = self._run_opencode(prompt, work_dir)
            elapsed = time.time() - start

            # Parse JSON event stream
            events = self._parse_events(raw_output)

            # Extract results from events
            written_files = self._extract_written_files(events)
            summary_text = self._extract_summary(events)
            total_tokens = self._extract_tokens(events)

            # Detect actual file changes
            files_after = self._snapshot_files(work_dir)
            changed_files = self._detect_changes(
                files_before, files_after, written_files, work_dir
            )

            # Collect baseline content for modified files (for reviewer drift detection)
            baseline_content: dict[str, str] = {}
            git_result = self._detect_git_changes(work_dir)
            if git_result is not None:
                baseline_content = git_result[1]

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
                goals_addressed=[],  # opencode doesn't report this
                unresolved_items=[],
                self_reported_risks=[],
                executor_name="opencode",
                model_used=self._model or "opencode-default",
                token_usage=total_tokens,
                execution_time_seconds=elapsed,
                validation_result=validation,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            logger.error(f"OpenCode timed out after {self._timeout}s")

            # --- Timeout evidence capture ---
            # Even though the subprocess was killed, opencode may have already
            # written files to disk. Capture them for reviewer diagnosis.
            changed_files = {}
            partial_summary = f"OpenCode execution timed out after {self._timeout}s"
            try:
                git_result = self._detect_git_changes(work_dir)
                changed_files = git_result[0] if git_result else {}
                baseline_content = git_result[1] if git_result else {}
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
                executor_name="opencode",
                model_used=self._model or "opencode-default",
                execution_time_seconds=elapsed,
                timed_out=True,
                validation_result=validation,
            )
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"OpenCode execution failed: {e}")
            return ExecutionReport(
                work_item_id="",
                code_output="",
                file_list=[],
                summary=f"OpenCode execution failed: {e}",
                unresolved_items=[f"Execution error: {e}"],
                executor_name="opencode",
                model_used=self._model or "opencode-default",
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

    def _resolve_work_dir(self) -> str:
        """Determine which directory to run opencode in."""
        if self._project_dir:
            return self._project_dir
        if self._use_sandbox:
            sandbox = tempfile.mkdtemp(prefix="codegate_opencode_")
            logger.debug(f"Created sandbox: {sandbox}")
            return sandbox
        return os.getcwd()

    def _run_opencode(self, prompt: str, work_dir: str) -> str:
        """Call opencode run and return raw stdout.

        --dangerously-skip-permissions is always used because `opencode run`
        is headless (non-interactive). Without it, opencode blocks waiting
        for user approval of file writes, causing timeouts.

        The safety boundary is NOT this flag — it is the /tmp project copy.
        Real project directories should only be used with explicit user intent.
        """
        cmd = [
            self._opencode_bin,
            "run",
            prompt,
            "--format", "json",
            "--dir", work_dir,
            "--dangerously-skip-permissions",
        ]

        if self._model:
            cmd.extend(["--model", self._model])

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
                f"opencode exited with code {result.returncode}: "
                f"{result.stderr[:500]}"
            )

        return result.stdout

    def _parse_events(self, raw: str) -> list[dict]:
        """Parse newline-delimited JSON events from opencode output."""
        events = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                logger.debug(f"Skipping non-JSON line: {line[:80]}")
        return events

    def _extract_written_files(self, events: list[dict]) -> dict[str, str]:
        """Extract file writes from tool_use events.

        Returns dict of filepath -> content.
        """
        files = {}
        for ev in events:
            if ev.get("type") != "tool_use":
                continue
            part = ev.get("part", {})
            if part.get("tool") != "write":
                continue
            state = part.get("state", {})
            if state.get("status") != "completed":
                continue
            inp = state.get("input", {})
            filepath = inp.get("filePath", "")
            content = inp.get("content", "")
            if filepath:
                files[filepath] = content
        return files

    def _extract_summary(self, events: list[dict]) -> str:
        """Extract text summary from the last text event."""
        texts = []
        for ev in events:
            if ev.get("type") == "text":
                part = ev.get("part", {})
                text = part.get("text", "")
                if text:
                    texts.append(text)
        return "\n".join(texts) if texts else "No summary provided by opencode."

    def _extract_tokens(self, events: list[dict]) -> int:
        """Sum total tokens from all step_finish events."""
        total = 0
        for ev in events:
            if ev.get("type") != "step_finish":
                continue
            part = ev.get("part", {})
            tokens = part.get("tokens", {})
            total += tokens.get("total", 0)
        return total

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

    def _detect_changes(
        self,
        before: dict[str, float],
        after: dict[str, float],
        written_files: dict[str, str],
        work_dir: str,
    ) -> dict[str, str]:
        """Detect which files changed and return their content.

        Merges opencode's reported writes with filesystem-level detection.
        Returns relative paths.
        """
        git_result = self._detect_git_changes(work_dir)
        if git_result is not None:
            return git_result[0]  # baseline handled separately

        changed = {}

        # 1. Files from opencode events (highest confidence)
        for filepath, content in written_files.items():
            rel = self._make_relative(filepath, work_dir)
            if self._is_ignored_relative_path(rel):
                continue
            changed[rel] = content

        # 2. New or modified files detected via mtime
        for path, mtime in after.items():
            if path not in before or before[path] != mtime:
                rel = self._make_relative(path, work_dir)
                if self._is_ignored_relative_path(rel):
                    continue
                if rel not in changed:
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            changed[rel] = f.read()
                    except Exception:
                        changed[rel] = "<binary or unreadable>"

        return changed

    def _detect_git_changes(self, work_dir: str) -> tuple[dict[str, str], dict[str, str]] | None:
        """Return git-visible changes + baseline content when work dir is git repo.

        Returns (changed_files, baseline_content) where:
        - changed_files: filepath → current content
        - baseline_content: filepath → content at HEAD (only for MODIFIED files)

        Git status respects .gitignore, which keeps build outputs like target/
        out of the governance evidence while preserving real source changes.
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
    def _parse_git_status_paths(raw: bytes) -> list[str]:
        """Parse `git status --porcelain=v1 -z` output into file paths."""
        paths = []
        parts = [p for p in raw.split(b"\0") if p]
        i = 0
        while i < len(parts):
            entry = parts[i].decode("utf-8", errors="replace")
            status = entry[:2]
            path = entry[3:]
            if status.startswith("R") or status.startswith("C"):
                # Rename/copy entries are followed by the source path.
                i += 1
            if path:
                paths.append(path)
            i += 1
        return paths

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

    @staticmethod
    def _build_prompt(
        contract: ImplementationContract,
        context: str,
        feedback: str,
    ) -> str:
        """Build the opencode prompt from the contract.

        Unlike BuiltinLLMExecutor, we DON'T ask for JSON output.
        We let opencode use its native file-writing tools.
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
            "Use the write tool to create all necessary files. "
            "Do NOT skip any acceptance criteria."
        )

        return "\n".join(parts)

    # ---- Post-run validation ------------------------------------------------

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

        # Look for "Tests run: N, Failures: N, Errors: N"
        # Take the last occurrence (summary line)
        for match in re.finditer(
            r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)", output
        ):
            tests_run = int(match.group(1))
            tests_failed = int(match.group(2)) + int(match.group(3))

        if not passed and not error_summary:
            # Look for compilation errors
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
                # Generic: grab first [ERROR] line with content
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

        # Look for "Tests: N passed, N total" or "N passing"
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
