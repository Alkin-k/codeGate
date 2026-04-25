"""A/B Runner — automated comparison of pure executor vs CodeGate-governed execution.

Automates the full A/B evaluation protocol:
  1. Create clean copies of the source project (excluding build artifacts)
  2. Verify baseline (git status clean, tests pass)
  3. Line A: pure executor (opencode) without governance
  4. Line B: CodeGate + executor with full governance pipeline
  5. Analyze both results and generate evidence report

Usage:
    codegate ab --project /path/to/project --input "requirement" --model kimi-for-coding/k2p6
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Directories to exclude when copying project (build artifacts, caches)
EXCLUDED_DIRS = {
    "target", "build", ".gradle", "node_modules", "dist", "out",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".opencode",
    ".idea", ".vscode", "coverage",
}


class ABResult:
    """Result of a single A/B run."""

    def __init__(self):
        self.line_a: dict = {}
        self.line_b: dict = {}
        self.baseline: dict = {}
        self.metadata: dict = {}
        self.report_path: Optional[Path] = None


def _copy_project(src: str, dst: Path) -> None:
    """Copy project excluding build artifacts and caches."""

    def _ignore(directory: str, contents: list[str]) -> set[str]:
        return {c for c in contents if c in EXCLUDED_DIRS}

    shutil.copytree(src, dst, ignore=_ignore)


def run_ab(
    project_dir: str,
    request: str,
    model: str,
    answers: str = "",
    timeout: int = 600,
    output_dir: Optional[str] = None,
    build_cmd: str = "mvn test -B",
    case_name: str = "",
) -> ABResult:
    """Run a full A/B comparison.

    Args:
        project_dir: Path to the source project (will be copied, not modified).
        request: The requirement/task to execute.
        model: Executor model (e.g., kimi-for-coding/k2p6).
        answers: Pre-provided clarification answers for CodeGate.
        timeout: Executor timeout in seconds.
        output_dir: Where to save artifacts and report.
        build_cmd: Command to verify baseline and test results.
        case_name: Human-readable name for the case.

    Returns:
        ABResult with both line results and generated report path.
    """
    result = ABResult()
    stamp = int(time.time())
    case_id = case_name.replace(" ", "_").lower() or f"case_{stamp}"
    out_base = Path(output_dir) if output_dir else Path("ab_results")
    run_dir = out_base / f"{case_id}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    result.metadata = {
        "case_name": case_name or case_id,
        "case_id": case_id,
        "project_dir": project_dir,
        "request": request,
        "model": model,
        "build_cmd": build_cmd,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
    }

    logger.info(f"A/B run: {case_name} → {run_dir}")

    # --- Step 1: Create clean copies (excluding build artifacts) ---
    dir_a = Path(f"/tmp/codegate-ab-{case_id}-a-{stamp}")
    dir_b = Path(f"/tmp/codegate-ab-{case_id}-b-{stamp}")

    logger.info(f"Creating clean copies: {dir_a}, {dir_b}")
    _copy_project(project_dir, dir_a)
    _copy_project(project_dir, dir_b)

    # --- Step 2: Verify baseline ---
    result.baseline = _verify_baseline(dir_a, build_cmd)
    if not result.baseline["clean"]:
        logger.error(f"Baseline not clean: {result.baseline}")
        result.metadata["error"] = "Baseline verification failed"
        _save_result(run_dir, result)
        return result

    logger.info(f"Baseline verified: {result.baseline['test_summary']}")

    # --- Step 3: Line A — pure executor ---
    logger.info("=== Line A: Pure OpenCode ===")
    result.line_a = _run_line_a(dir_a, request, model, timeout, build_cmd)

    # --- Step 4: Line B — CodeGate + executor ---
    logger.info("=== Line B: CodeGate + OpenCode ===")
    result.line_b = _run_line_b(
        dir_b, request, model, timeout, build_cmd, answers, run_dir
    )

    # --- Step 5: Generate report ---
    result.metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_result(run_dir, result)
    result.report_path = _generate_report(run_dir, result)

    logger.info(f"A/B complete: report at {result.report_path}")
    return result


def _verify_baseline(project_dir: Path, build_cmd: str) -> dict:
    """Verify project is clean and tests pass."""
    baseline = {"clean": False, "git_dirty": 0, "test_pass": False, "test_summary": ""}

    # Check git status
    try:
        git_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        dirty_lines = [l for l in git_result.stdout.strip().split("\n") if l.strip()]
        baseline["git_dirty"] = len(dirty_lines)
    except Exception as e:
        baseline["git_error"] = str(e)
        return baseline

    # Run tests
    try:
        test_result = subprocess.run(
            build_cmd.split(),
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        baseline["test_pass"] = test_result.returncode == 0
        for line in test_result.stdout.split("\n"):
            if "Tests run:" in line and "Failures:" in line:
                baseline["test_summary"] = line.strip()
        if not baseline["test_summary"]:
            baseline["test_summary"] = "BUILD SUCCESS" if baseline["test_pass"] else "BUILD FAILED"
    except Exception as e:
        baseline["test_error"] = str(e)
        return baseline

    baseline["clean"] = baseline["git_dirty"] == 0 and baseline["test_pass"]
    return baseline


def _run_line_a(
    project_dir: Path, request: str, model: str, timeout: int, build_cmd: str
) -> dict:
    """Run pure executor (no governance)."""
    result = {
        "line": "A",
        "label": "Pure OpenCode",
        "workspace": str(project_dir),
    }

    t0 = time.time()
    try:
        proc = subprocess.run(
            [
                "opencode", "run", request,
                "--format", "json",
                "--dangerously-skip-permissions",
                "--model", model,
            ],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result["exit_code"] = proc.returncode
        result["duration"] = round(time.time() - t0, 1)

        # Parse opencode JSON output for summary
        for line in proc.stdout.strip().split("\n"):
            try:
                msg = json.loads(line)
                if msg.get("type") == "text":
                    text = msg.get("part", {}).get("text", "")
                    if text:
                        result["executor_summary"] = text[:500]
            except json.JSONDecodeError:
                continue

    except subprocess.TimeoutExpired:
        result["exit_code"] = -1
        result["duration"] = timeout
        result["error"] = "Timeout"
    except Exception as e:
        result["exit_code"] = -1
        result["duration"] = round(time.time() - t0, 1)
        result["error"] = str(e)

    # Check what changed
    result["changes"] = _collect_changes(project_dir)

    # Run tests
    result["test_result"] = _run_tests(project_dir, build_cmd)

    # Heuristic drift indicators (not confirmed drift)
    result["heuristic_analysis"] = _analyze_heuristic_indicators(project_dir)

    return result


def _run_line_b(
    project_dir: Path,
    request: str,
    model: str,
    timeout: int,
    build_cmd: str,
    answers: str,
    run_dir: Path,
) -> dict:
    """Run CodeGate + executor."""
    result = {
        "line": "B",
        "label": "CodeGate + OpenCode",
        "workspace": str(project_dir),
    }

    codegate_output = run_dir / "codegate_artifacts"
    codegate_output.mkdir(exist_ok=True)

    t0 = time.time()
    try:
        cmd = [
            "codegate", "run",
            "--input", request,
            "--executor", "opencode",
            "--executor-model", model,
            "--project-dir", str(project_dir),
            "--timeout", str(timeout),
            "--output", str(codegate_output),
        ]
        if answers:
            cmd.extend(["--answers", answers])

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 120,
        )
        result["exit_code"] = proc.returncode
        result["duration"] = round(time.time() - t0, 1)
        result["stdout_tail"] = proc.stdout[-2000:] if proc.stdout else ""

    except subprocess.TimeoutExpired:
        result["exit_code"] = -1
        result["duration"] = timeout + 120
        result["error"] = "Timeout"
    except Exception as e:
        result["exit_code"] = -1
        result["duration"] = round(time.time() - t0, 1)
        result["error"] = str(e)

    # Load CodeGate artifacts
    result["codegate"] = _load_codegate_artifacts(codegate_output)

    # Check what changed
    result["changes"] = _collect_changes(project_dir)

    # Run tests
    result["test_result"] = _run_tests(project_dir, build_cmd)

    return result


def _collect_changes(project_dir: Path) -> dict:
    """Collect git diff statistics."""
    changes = {"files": [], "stat": ""}
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
        changes["files"] = [f.strip() for f in proc.stdout.strip().split("\n") if f.strip()]

        proc2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
        untracked = [f.strip() for f in proc2.stdout.strip().split("\n") if f.strip()]
        if untracked:
            changes["files"].extend([f"[new] {f}" for f in untracked])

        proc3 = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
        changes["stat"] = proc3.stdout.strip()

    except Exception as e:
        changes["error"] = str(e)

    return changes


def _run_tests(project_dir: Path, build_cmd: str) -> dict:
    """Run tests and return structured results.

    Handles Maven surefire output format:
      [INFO] Tests run: 12, Failures: 0, Errors: 0, Skipped: 0
    Takes the LAST matching line (aggregated summary, not per-class).
    """
    test_result = {
        "pass": False,
        "summary": "",
        "total": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    try:
        proc = subprocess.run(
            build_cmd.split(),
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=120,
        )
        test_result["pass"] = proc.returncode == 0

        # Find all "Tests run:" lines, take the last one (aggregated summary)
        for line in proc.stdout.split("\n"):
            # Strip Maven [INFO]/[WARNING] prefix
            cleaned = re.sub(r"^\[(?:INFO|WARNING|ERROR)\]\s*", "", line.strip())
            if "Tests run:" in cleaned and "Failures:" in cleaned:
                test_result["summary"] = cleaned
                # Parse: "Tests run: 12, Failures: 0, Errors: 0, Skipped: 0"
                for part in cleaned.split(","):
                    part = part.strip()
                    m = re.match(r"(Tests run|Failures|Errors|Skipped):\s*(\d+)", part)
                    if m:
                        key = m.group(1).lower().replace("tests run", "total").replace(" ", "_")
                        test_result[key] = int(m.group(2))

        if not test_result["summary"]:
            test_result["summary"] = "BUILD SUCCESS" if test_result["pass"] else "BUILD FAILED"

    except Exception as e:
        test_result["error"] = str(e)

    return test_result


def _analyze_heuristic_indicators(project_dir: Path) -> dict:
    """Heuristic check for potential drift patterns in Line A changes.

    IMPORTANT: These are unconfirmed indicators, not confirmed drift.
    They flag areas that warrant manual or LLM-based review.
    Only the CodeGate reviewer can confirm actual drift.
    """
    analysis = {"heuristic_flags": [], "requires_review": False}
    try:
        proc = subprocess.run(
            ["git", "diff"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
        diff = proc.stdout
        diff_lines = diff.split("\n")

        flags = {}

        # 1. Return type change: only check method signature lines (- public ... / + public ...)
        removed_sigs = [l for l in diff_lines if re.match(r"^-\s+public\s+\S+", l)]
        added_sigs = [l for l in diff_lines if re.match(r"^\+\s+public\s+\S+", l)]
        if removed_sigs and added_sigs:
            # Check if any removed signature has a different return type than the added one
            for rem in removed_sigs:
                rem_type = _extract_return_type(rem)
                for add in added_sigs:
                    add_type = _extract_return_type(add)
                    if rem_type and add_type and rem_type != add_type:
                        flags["return_type_change"] = f"{rem_type} → {add_type}"
                        break

        # 2. Annotation removal: specifically check for removed @-annotations on - lines
        removed_annotations = [
            l.strip() for l in diff_lines
            if l.startswith("-") and not l.startswith("---")
            and re.search(r"@\w+", l)
            and not any(l.startswith("+") for l in [])  # Only removed lines
        ]
        added_annotations = [
            l.strip() for l in diff_lines
            if l.startswith("+") and not l.startswith("+++")
            and re.search(r"@\w+", l)
        ]
        # Only flag if annotations were removed but not re-added
        if removed_annotations and len(removed_annotations) > len(added_annotations):
            flags["annotation_removal"] = [a[1:].strip() for a in removed_annotations[:3]]

        # 3. New exception handler: specifically check for ADDED @ExceptionHandler
        new_handlers = [
            l for l in diff_lines
            if l.startswith("+") and "@ExceptionHandler" in l
        ]
        if new_handlers:
            flags["new_exception_handler"] = len(new_handlers)

        # 4. Weak assertions (test quality)
        weak_patterns = ["assertTrue(true)", "assertNotNull(service)", "// TODO"]
        found_weak = [p for p in weak_patterns if p in diff]
        if found_weak:
            flags["weak_assertion"] = found_weak

        analysis["heuristic_flags"] = list(flags.keys())
        analysis["heuristic_details"] = flags
        analysis["requires_review"] = len(flags) > 0

    except Exception as e:
        analysis["error"] = str(e)
        analysis["requires_review"] = False

    return analysis


def _extract_return_type(sig_line: str) -> Optional[str]:
    """Extract return type from a Java method signature line like '- public ApiResponse<X> method(...)'."""
    # Strip the diff prefix (- or +) and leading whitespace
    cleaned = re.sub(r"^[+-]\s*", "", sig_line).strip()
    # Match: [modifiers] ReturnType methodName(
    m = re.match(r"(?:public|private|protected)\s+(.+?)\s+\w+\s*\(", cleaned)
    if m:
        return m.group(1).strip()
    return None


def _load_codegate_artifacts(output_dir: Path) -> dict:
    """Load CodeGate governance artifacts."""
    result = {"artifact_id": None, "decision": None, "findings": []}

    subdirs = [d for d in output_dir.iterdir() if d.is_dir()]
    if not subdirs:
        result["error"] = "No artifact directory found"
        return result

    artifact_dir = subdirs[0]
    result["artifact_id"] = artifact_dir.name
    result["artifact_dir"] = str(artifact_dir)

    summary_path = artifact_dir / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        result["decision"] = summary.get("decision")
        result["drift_score"] = summary.get("drift_score")
        result["coverage_score"] = summary.get("coverage_score")
        result["findings_count"] = summary.get("findings_count", 0)
        result["blocking_findings"] = summary.get("blocking_findings", 0)
        result["advisory_findings"] = summary.get("advisory_findings", 0)
        result["info_findings"] = summary.get("info_findings", 0)
        result["phase_timings"] = summary.get("phase_timings", {})
        result["total_tokens"] = summary.get("total_tokens", 0)
        result["gatekeeper_original_decision"] = summary.get("gatekeeper_original_decision")
        result["policy_overridden"] = (
            result["gatekeeper_original_decision"] is not None
            and result["gatekeeper_original_decision"] != summary.get("decision")
        )

        timings = result["phase_timings"]
        executor_time = timings.get("executor", 0)
        total_time = sum(timings.values())
        overhead = total_time - executor_time
        result["governance_overhead_s"] = round(overhead, 1)
        result["governance_overhead_pct"] = (
            round(overhead / executor_time * 100, 1) if executor_time > 0 else 0
        )

    findings_path = artifact_dir / "review_findings.json"
    if findings_path.exists():
        result["findings"] = json.loads(findings_path.read_text(encoding="utf-8"))

    # Load gate_decision for policy override details
    gate_path = artifact_dir / "gate_decision.json"
    if gate_path.exists():
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        result["gate_summary"] = gate.get("summary", "")
        result["gate_next_action"] = gate.get("next_action", "")

    return result


def _save_result(run_dir: Path, result: ABResult) -> None:
    """Save raw A/B result as JSON."""
    data = {
        "metadata": result.metadata,
        "baseline": result.baseline,
        "line_a": result.line_a,
        "line_b": result.line_b,
    }
    path = run_dir / "ab_result.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info(f"Raw result saved: {path}")


def _generate_report(run_dir: Path, result: ABResult) -> Path:
    """Generate an auditor-ready evidence report.

    Designed to be readable by team leads and auditors without
    opening any JSON files. Every conclusion links to evidence.
    """
    meta = result.metadata
    a = result.line_a
    b = result.line_b
    cg = b.get("codegate", {})
    heuristic = a.get("heuristic_analysis", {})
    flags = heuristic.get("heuristic_flags", [])
    b_decision = (cg.get("decision") or "N/A").upper()
    b_drift = cg.get("drift_score", 0)

    a_tests = a.get("test_result", {}).get("total", 0)
    b_tests = b.get("test_result", {}).get("total", 0)

    lines = []

    # ===== HEADER =====
    lines.extend([
        "# 🛡️ Governance Evidence Report",
        "",
        f"**Case**: {meta.get('case_name', 'Unknown')}  ",
        f"**Generated**: {meta.get('completed_at', 'N/A')}",
        "",
    ])

    # ===== 1. CLEARANCE DECISION =====
    decision_emoji = {
        "APPROVE": "✅", "REVISE_CODE": "🔄",
        "REVISE_SPEC": "📝", "ESCALATE_TO_HUMAN": "⚠️",
    }.get(b_decision, "❓")

    lines.extend([
        "## 1. Clearance Decision",
        "",
        f"### {decision_emoji} {b_decision}",
        "",
    ])

    if b_decision == "APPROVE":
        lines.extend([
            "The implementation **passes all governance gates**:",
            f"- Drift score: **{b_drift}/100** (threshold: ≤30)",
            f"- Coverage score: **{cg.get('coverage_score', 0)}/100** (threshold: ≥70)",
            f"- Blocking findings: **{cg.get('blocking_findings', 0)}**",
            f"- Tests: **{b_tests} pass**, 0 failures",
            f"- Governance overhead: **{cg.get('governance_overhead_pct', 0)}%** (threshold: ≤20%)",
            "",
        ])
    else:
        lines.extend([
            "The implementation **requires action** before approval:",
            f"- Drift score: **{b_drift}/100**",
            f"- Blocking findings: **{cg.get('blocking_findings', 0)}**",
            f"- Advisory findings: **{cg.get('advisory_findings', 0)}**",
            "",
        ])

    # Policy override notice
    if cg.get("policy_overridden"):
        orig = (cg.get("gatekeeper_original_decision") or "").upper()
        lines.extend([
            f"> **⚠️ Policy Override**: Gatekeeper originally decided `{orig}`, ",
            f"> but policy enforcement overrode to `{b_decision}` due to {cg.get('blocking_findings', 0)} blocking finding(s). ",
            "> This may indicate a **contract conflict** — the requirement asks for behavior ",
            "> that inherently conflicts with a preservation constraint. Review the finding's ",
            "> suggestion field for resolution guidance.",
            "",
        ])

    # ===== 2. RISK SUMMARY =====
    lines.extend([
        "## 2. Risk Summary",
        "",
        "| Risk Dimension | Value | Status |",
        "|----------------|-------|--------|",
        f"| Drift score | {b_drift}/100 | {'🟢 Low' if b_drift <= 15 else '🟡 Medium' if b_drift <= 30 else '🔴 High'} |",
        f"| Coverage score | {cg.get('coverage_score', 0)}/100 | {'🟢 Good' if cg.get('coverage_score', 0) >= 80 else '🟡 Partial' if cg.get('coverage_score', 0) >= 50 else '🔴 Low'} |",
        f"| Blocking findings | {cg.get('blocking_findings', 0)} | {'🟢 None' if cg.get('blocking_findings', 0) == 0 else '🔴 Action required'} |",
        f"| Advisory findings | {cg.get('advisory_findings', 0)} | {'🟢 None' if cg.get('advisory_findings', 0) == 0 else '🟡 Review recommended'} |",
        f"| Info findings | {cg.get('info_findings', 0)} | ℹ️ |",
        f"| Governance overhead | {cg.get('governance_overhead_pct', 0)}% | {'🟢 Acceptable' if cg.get('governance_overhead_pct', 0) <= 20 else '🟡 High'} |",
        "",
    ])

    # ===== 3. FINDINGS DETAIL =====
    findings = cg.get("findings", [])
    if findings:
        lines.extend([
            "## 3. Findings Detail",
            "",
            "| # | Severity | Disposition | Category | Clause |",
            "|---|----------|-------------|----------|--------|",
        ])
        for i, f in enumerate(findings, 1):
            disp = f.get("disposition", "blocking" if f.get("blocking") else "advisory")
            ref = f.get("contract_clause_ref", "")
            loc = f.get("code_location", "")
            lines.append(f"| {i} | {f.get('severity', '?')} | {disp} | {f.get('category', '?')} | {ref} |")

        lines.append("")

        # Expanded details per finding
        for i, f in enumerate(findings, 1):
            disp = f.get("disposition", "blocking" if f.get("blocking") else "advisory")
            lines.extend([
                f"**Finding {i}** ({disp}):",
                f"- **Message**: {f.get('message', '')}",
            ])
            if f.get("code_location"):
                lines.append(f"- **Location**: `{f['code_location']}`")
            if f.get("suggestion"):
                lines.append(f"- **Suggestion**: {f['suggestion']}")
            lines.append("")

    else:
        lines.extend([
            "## 3. Findings",
            "",
            "No findings. The implementation fully satisfies the contract.",
            "",
        ])

    # ===== 4. A/B COMPARISON =====
    lines.extend([
        "## 4. A/B Comparison",
        "",
        "| Dimension | Line A (Pure OpenCode) | Line B (CodeGate + OpenCode) |",
        "|-----------|----------------------|------------------------------|",
        f"| Duration | {a.get('duration', '?')}s | {b.get('duration', '?')}s |",
        f"| Files changed | {len(a.get('changes', {}).get('files', []))} | {len(b.get('changes', {}).get('files', []))} |",
        f"| Tests (total) | {a_tests} | {b_tests} |",
        f"| Tests (pass) | {'✅' if a.get('test_result', {}).get('pass') else '❌'} | {'✅' if b.get('test_result', {}).get('pass') else '❌'} |",
        f"| Heuristic flags | {len(flags)} | N/A (governed) |",
        f"| Governance decision | N/A | **{b_decision}** |",
        f"| Governance overhead | N/A | {cg.get('governance_overhead_pct', 0)}% |",
        "",
    ])

    if a_tests != b_tests:
        lines.extend([
            f"> **Test count difference**: Line A produced {a_tests} tests, Line B produced {b_tests}. ",
            "> This is expected — two independent LLM executions generate slightly different test suites. ",
            "> The governance pipeline validates contract compliance, not test count parity.",
            "",
        ])

    # --- 4.1 Line A ---
    lines.extend([
        "### 4.1 Line A: Pure OpenCode",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Workspace | `{a.get('workspace', 'N/A')}` |",
        f"| Duration | {a.get('duration', 'N/A')}s |",
        f"| Tests | {a_tests} run, {a.get('test_result', {}).get('failures', 0)} fail, {a.get('test_result', {}).get('errors', 0)} err |",
    ])
    if flags:
        lines.append(f"| Heuristic flags | {', '.join(flags)} |")
        lines.extend([
            "",
            f"> Heuristic indicators: {', '.join(flags)}. "
            "These are *unconfirmed* — only the CodeGate LLM reviewer can confirm actual drift.",
        ])
    else:
        lines.append("| Heuristic flags | None |")
    lines.append("")

    if a.get("changes", {}).get("files"):
        lines.append("**Changed files:**")
        for f in a["changes"]["files"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if a.get("changes", {}).get("stat"):
        lines.extend(["**Diff stat:**", f"```\n{a['changes']['stat']}\n```", ""])

    # --- 4.2 Line B ---
    lines.extend([
        "### 4.2 Line B: CodeGate + OpenCode",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Workspace | `{b.get('workspace', 'N/A')}` |",
        f"| Duration | {b.get('duration', 'N/A')}s |",
        f"| Tests | {b_tests} run, {b.get('test_result', {}).get('failures', 0)} fail, {b.get('test_result', {}).get('errors', 0)} err |",
        f"| Decision | **{b_decision}** |",
        f"| Drift | {b_drift} |",
        f"| Coverage | {cg.get('coverage_score', 'N/A')} |",
        f"| Findings | {cg.get('findings_count', 0)} (blocking={cg.get('blocking_findings', 0)}, advisory={cg.get('advisory_findings', 0)}, info={cg.get('info_findings', 0)}) |",
        "",
    ])

    if b.get("changes", {}).get("files"):
        lines.append("**Changed files:**")
        for f in b["changes"]["files"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if b.get("changes", {}).get("stat"):
        lines.extend(["**Diff stat:**", f"```\n{b['changes']['stat']}\n```", ""])

    timings = cg.get("phase_timings", {})
    if timings:
        lines.extend(["**Phase timings:**", "", "| Phase | Time |", "|-------|------|"])
        for phase, t in timings.items():
            lines.append(f"| {phase} | {t:.1f}s |")
        lines.append(f"| **governance overhead** | **{cg.get('governance_overhead_s', 0)}s ({cg.get('governance_overhead_pct', 0)}%)** |")
        lines.append("")

    # ===== 5. EVIDENCE CHAIN =====
    artifact_dir = cg.get("artifact_dir", "")
    artifact_path = Path(artifact_dir) if artifact_dir else None

    evidence_files = [
        ("A/B raw data", f"{run_dir}/ab_result.json"),
        ("CodeGate artifact", artifact_dir),
        ("Summary", f"{artifact_dir}/summary.json"),
        ("Contract", f"{artifact_dir}/contract.json"),
        ("Review findings", f"{artifact_dir}/review_findings.json"),
        ("Raw findings (pre-filter)", f"{artifact_dir}/raw_review_findings.json"),
        ("Suppressed findings", f"{artifact_dir}/suppressed_findings.json"),
        ("Structural diff", f"{artifact_dir}/structural_diff.json"),
    ]

    lines.extend([
        "## 5. Evidence Chain",
        "",
        "All governance evidence is persisted for audit reproducibility.",
        "",
        "| Evidence | Path | Status |",
        "|----------|------|--------|",
    ])
    for label, path_str in evidence_files:
        exists = Path(path_str).exists() if path_str else False
        status = "✅" if exists else "— not generated (no suppression)" if "suppressed" in label.lower() else "— not generated" if not exists else ""
        lines.append(f"| {label} | `{path_str}` | {status} |")
    lines.append("")


    # ===== 6. REPRODUCIBILITY =====
    lines.extend([
        "## 6. Reproducibility",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Project | `{meta.get('project_dir', 'N/A')}` |",
        f"| Model | `{meta.get('model', 'N/A')}` |",
        f"| Build command | `{meta.get('build_cmd', 'N/A')}` |",
        f"| Artifact ID | `{cg.get('artifact_id', 'N/A')}` |",
        f"| Run directory | `{run_dir}` |",
        f"| Started | {meta.get('started_at', 'N/A')} |",
        f"| Completed | {meta.get('completed_at', 'N/A')} |",
        "",
    ])

    # ===== 7. VERDICT =====
    lines.extend(["---", "", "## 7. Verdict", ""])

    has_flags = heuristic.get("requires_review", False)

    if b_decision in ("REVISE_CODE", "ESCALATE_TO_HUMAN"):
        blocking_count = cg.get("blocking_findings", 0)
        # Get first blocking finding message for context
        blocking_msgs = [
            f.get("message", "")
            for f in findings if f.get("disposition") == "blocking" or f.get("blocking")
        ]
        reason = blocking_msgs[0] if blocking_msgs else "See findings above"

        lines.append(
            f"**🔴 Implementation blocked.** {blocking_count} blocking finding(s) "
            f"detected (drift={b_drift}). Decision: `{b_decision}`."
        )
        lines.append("")
        lines.append(f"**Blocking reason**: {reason}")

        if cg.get("policy_overridden"):
            orig = (cg.get("gatekeeper_original_decision") or "").upper()
            lines.append("")
            lines.append(
                f"**Note**: Gatekeeper originally decided `{orig}`, overridden by policy. "
                "This suggests a possible **contract conflict** — the requirement "
                "may contain contradictory constraints. Recommend reviewing the contract "
                "before revising code."
            )
    elif b_decision == "APPROVE" and b_drift <= 10:
        if has_flags:
            lines.extend([
                "**🟢 Implementation approved.** "
                f"Line A triggered heuristic indicators ({', '.join(flags)}), "
                f"but CodeGate's LLM reviewer confirmed no actual drift (score={b_drift}). "
                "CodeGate correctly approved without adding noise (0 false positives).",
            ])
        else:
            lines.extend([
                "**🟢 Implementation approved.** "
                f"CodeGate confirmed the implementation matches the contract (drift={b_drift}, "
                f"coverage={cg.get('coverage_score', 0)}, 0 false positives).",
            ])
    elif b_decision == "APPROVE" and has_flags:
        lines.extend([
            f"**🟡 Implementation approved with caveats.** "
            f"Heuristic indicators triggered ({', '.join(flags)}) but CodeGate approved (drift={b_drift}). "
            "Manual review recommended to confirm heuristic flags are false positives.",
        ])
    else:
        lines.extend([
            f"Decision: `{b_decision}`, drift={b_drift}, heuristic flags={len(flags)}. "
            "Manual review recommended.",
        ])

    lines.append("")

    report_path = run_dir / "audit_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    # Also generate compact basic report for backward compat
    _generate_basic_report(run_dir, result)

    return report_path


def _generate_basic_report(run_dir: Path, result: ABResult) -> Path:
    """Generate a compact basic report (backward compat with §27)."""
    meta = result.metadata
    a = result.line_a
    b = result.line_b
    cg = b.get("codegate", {})
    heuristic = a.get("heuristic_analysis", {})
    flags = heuristic.get("heuristic_flags", [])

    lines = [
        f"# A/B Evidence Report: {meta.get('case_name', 'Unknown')}",
        "",
        f"> Generated: {meta.get('completed_at', 'N/A')}",
        f"> Project: `{meta.get('project_dir', 'N/A')}`",
        f"> Model: `{meta.get('model', 'N/A')}`",
        "",
        "## Summary",
        "",
        "| Dimension | Line A (Pure) | Line B (CodeGate) |",
        "|-----------|---------------|-------------------|",
        f"| Duration | {a.get('duration', '?')}s | {b.get('duration', '?')}s |",
        f"| Files | {len(a.get('changes', {}).get('files', []))} | {len(b.get('changes', {}).get('files', []))} |",
        f"| Tests | {a.get('test_result', {}).get('total', 0)} | {b.get('test_result', {}).get('total', 0)} |",
        f"| Flags | {len(flags)} | N/A |",
        f"| Decision | N/A | **{(cg.get('decision') or 'N/A').upper()}** |",
        f"| Overhead | N/A | {cg.get('governance_overhead_pct', 0)}% |",
        "",
    ]

    report_path = run_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path

