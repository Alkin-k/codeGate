"""Shared file detection and validation utilities for executor adapters.

Extracted from GeminiCLIAdapter/OpenCodeAdapter to avoid duplication.
All executor adapters that run external CLI tools and detect file changes
via git or filesystem comparison should use these utilities.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

from codegate.schemas.execution import ValidationResult

logger = logging.getLogger(__name__)

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

# Default timeout for post-run validation (seconds)
VALIDATION_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def is_ignored_relative_path(path: str) -> bool:
    """Return True when a relative path should not enter evidence."""
    normalized = path.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    if any(part in IGNORED_DIR_NAMES for part in parts):
        return True
    return any(normalized.endswith(suffix) for suffix in IGNORED_FILE_SUFFIXES)


def is_ignored_path(path: str, base: str) -> bool:
    """Return True when an absolute path should not enter evidence."""
    return is_ignored_relative_path(make_relative(path, base))


def make_relative(filepath: str, base: str) -> str:
    """Convert absolute path to relative path from base."""
    try:
        return str(Path(filepath).relative_to(base))
    except ValueError:
        # Handle /private/tmp vs /tmp on macOS
        try:
            return str(Path(filepath).relative_to(f"/private{base}"))
        except ValueError:
            return filepath


def format_code_output(files: dict[str, str]) -> str:
    """Format files into a single code_output string for review."""
    if not files:
        return ""
    parts = []
    for path, content in sorted(files.items()):
        parts.append(f"=== {path} ===\n{content}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# File change detection
# ---------------------------------------------------------------------------


def snapshot_files(work_dir: str) -> dict[str, float]:
    """Take a snapshot of files and their mtimes for change detection."""
    snap = {}
    for root, _, files in os.walk(work_dir):
        if is_ignored_path(root, work_dir):
            continue
        for f in files:
            path = os.path.join(root, f)
            if is_ignored_path(path, work_dir):
                continue
            try:
                snap[path] = os.path.getmtime(path)
            except OSError:
                pass
    return snap


def detect_changes_by_mtime(
    before: dict[str, float],
    after: dict[str, float],
    work_dir: str,
) -> dict[str, str]:
    """Detect file changes using mtime comparison (fallback when not git)."""
    changed = {}
    for path, mtime in after.items():
        if path not in before or before[path] != mtime:
            rel = make_relative(path, work_dir)
            if is_ignored_relative_path(rel):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    changed[rel] = f.read()
            except Exception:
                changed[rel] = "<binary or unreadable>"
    return changed


def detect_git_changes(
    work_dir: str,
) -> tuple[dict[str, str], dict[str, str]] | None:
    """Return git-visible changes + baseline content when work dir is git repo.

    Returns (changed_files, baseline_content) where:
    - changed_files: filepath → current content
    - baseline_content: filepath → content at HEAD (only for MODIFIED files)

    Returns None if work_dir is not a git repository.
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

    entries = parse_git_status_entries(result.stdout)
    changed: dict[str, str] = {}
    baseline: dict[str, str] = {}
    for status, rel in entries:
        if git_prefix and rel.startswith(git_prefix):
            git_rel = rel
            project_rel = rel[len(git_prefix):]
        else:
            git_rel = f"{git_prefix}{rel}"
            project_rel = rel

        if is_ignored_relative_path(project_rel):
            continue
        abs_path = Path(work_dir) / project_rel
        if not abs_path.exists():
            changed[project_rel] = "<deleted>"
            continue
        try:
            changed[project_rel] = abs_path.read_text(
                encoding="utf-8", errors="replace"
            )
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


def parse_git_status_entries(raw: bytes) -> list[tuple[str, str]]:
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


# ---------------------------------------------------------------------------
# Post-run validation
# ---------------------------------------------------------------------------


def run_validation(
    work_dir: str, timeout: int = VALIDATION_TIMEOUT
) -> ValidationResult | None:
    """Auto-detect project type and run validation (mvn test / npm test).

    Returns None if project type is not detected.
    """
    project_type, cmd = detect_project_type(work_dir)
    if project_type is None:
        return None

    logger.info(f"Running post-run validation: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
        )
    except subprocess.TimeoutExpired:
        return ValidationResult(
            type=project_type,
            command=" ".join(cmd),
            exit_code=-1,
            passed=False,
            error_summary=f"Validation timed out after {timeout}s",
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
        tests_run, tests_failed, error_summary = parse_maven_output(
            combined, passed
        )
    elif project_type == "npm":
        tests_run, tests_failed, error_summary = parse_npm_output(
            combined, passed
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


def detect_project_type(work_dir: str) -> tuple[str | None, list[str]]:
    """Detect project type from build files."""
    p = Path(work_dir)
    if (p / "pom.xml").exists():
        return "maven", ["mvn", "test", "-B"]
    if (p / "build.gradle").exists() or (p / "build.gradle.kts").exists():
        return "gradle", ["./gradlew", "test", "--no-daemon"]
    if (p / "package.json").exists():
        return "npm", ["npm", "test"]
    return None, []


def parse_maven_output(
    output: str, passed: bool
) -> tuple[int, int, str | None]:
    """Parse Maven test output for counts and error summary."""
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


def parse_npm_output(
    output: str, passed: bool
) -> tuple[int, int, str | None]:
    """Parse npm test output for counts and error summary."""
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
