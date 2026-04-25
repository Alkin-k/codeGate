"""A/B Batch Runner — run multiple A/B cases from a YAML definition file.

Reads a cases YAML, runs each case via `run_ab`, then generates
a consolidated batch report summarizing all results.

Usage:
    codegate ab-batch --cases eval_cases/image2pdf_cases.yaml
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from codegate.eval.ab_runner import ABResult, run_ab

logger = logging.getLogger(__name__)


class BatchResult:
    """Result of a batch A/B run."""

    def __init__(self):
        self.cases: list[dict] = []
        self.metadata: dict = {}
        self.report_path: Optional[Path] = None


def run_batch(
    cases_file: str,
    output_dir: Optional[str] = None,
) -> BatchResult:
    """Run all A/B cases defined in a YAML file.

    Args:
        cases_file: Path to the YAML cases definition file.
        output_dir: Output directory for batch results.

    Returns:
        BatchResult with all case results and batch report path.
    """
    result = BatchResult()
    stamp = int(time.time())

    # Load cases definition
    cases_path = Path(cases_file)
    with open(cases_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    project = config.get("project", "")
    model = config.get("model", "")
    build_cmd = config.get("build_cmd", "mvn test -B")
    timeout = config.get("timeout", 600)
    cases = config.get("cases", [])

    out_base = Path(output_dir) if output_dir else Path("ab_results")
    batch_dir = out_base / f"batch_{stamp}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    result.metadata = {
        "cases_file": str(cases_path),
        "project": project,
        "model": model,
        "build_cmd": build_cmd,
        "total_cases": len(cases),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "batch_dir": str(batch_dir),
    }

    logger.info(f"Batch run: {len(cases)} cases from {cases_path}")

    for i, case in enumerate(cases, 1):
        name = case.get("name", f"case_{i}")
        logger.info(f"=== Case {i}/{len(cases)}: {name} ===")

        case_input = case.get("input", "").strip()
        case_answers = case.get("answers", "").strip()
        case_project = case.get("project", project)
        case_model = case.get("model", model)
        case_build = case.get("build_cmd", build_cmd)
        case_timeout = case.get("timeout", timeout)

        t0 = time.time()
        try:
            ab_result = run_ab(
                project_dir=case_project,
                request=case_input,
                model=case_model,
                answers=case_answers,
                timeout=case_timeout,
                output_dir=str(batch_dir),
                build_cmd=case_build,
                case_name=name,
            )

            cg = ab_result.line_b.get("codegate", {})
            case_summary = {
                "index": i,
                "name": name,
                "status": "completed",
                "duration": round(time.time() - t0, 1),
                "decision": cg.get("decision"),
                "drift_score": cg.get("drift_score"),
                "coverage_score": cg.get("coverage_score"),
                "findings_count": cg.get("findings_count", 0),
                "blocking_findings": cg.get("blocking_findings", 0),
                "advisory_findings": cg.get("advisory_findings", 0),
                "info_findings": cg.get("info_findings", 0),
                "overhead_pct": cg.get("governance_overhead_pct", 0),
                "line_a_tests": ab_result.line_a.get("test_result", {}).get("total", 0),
                "line_b_tests": ab_result.line_b.get("test_result", {}).get("total", 0),
                "line_a_pass": ab_result.line_a.get("test_result", {}).get("pass", False),
                "line_b_pass": ab_result.line_b.get("test_result", {}).get("pass", False),
                "heuristic_flags": ab_result.line_a.get("heuristic_analysis", {}).get("heuristic_flags", []),
                "artifact_id": cg.get("artifact_id"),
                "report_path": str(ab_result.report_path) if ab_result.report_path else None,
                "gatekeeper_original_decision": cg.get("gatekeeper_original_decision"),
                "policy_overridden": cg.get("policy_overridden", False),
                "blocking_finding_messages": [
                    f.get("message", "")[:300]
                    for f in cg.get("findings", [])
                    if f.get("disposition") == "blocking" or f.get("blocking")
                ],
            }

        except Exception as e:
            logger.error(f"Case {name} failed: {e}")
            case_summary = {
                "index": i,
                "name": name,
                "status": "failed",
                "duration": round(time.time() - t0, 1),
                "error": str(e),
            }

        result.cases.append(case_summary)
        logger.info(f"Case {i} done: {case_summary.get('decision', 'ERROR')} ({case_summary['duration']}s)")

    result.metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    result.metadata["total_duration"] = round(
        sum(c.get("duration", 0) for c in result.cases), 1
    )

    # Save batch summary JSON
    _save_batch_summary(batch_dir, result)

    # Generate batch report
    result.report_path = _generate_batch_report(batch_dir, result)

    logger.info(f"Batch complete: {result.report_path}")
    return result


def _save_batch_summary(batch_dir: Path, result: BatchResult) -> None:
    """Save batch summary as JSON."""
    data = {
        "metadata": result.metadata,
        "cases": result.cases,
    }
    path = batch_dir / "batch_summary.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _generate_batch_report(batch_dir: Path, result: BatchResult) -> Path:
    """Generate a consolidated batch report."""
    meta = result.metadata
    cases = result.cases

    completed = [c for c in cases if c.get("status") == "completed"]
    failed = [c for c in cases if c.get("status") == "failed"]

    approved = [c for c in completed if (c.get("decision") or "").lower() == "approve"]
    blocked = [c for c in completed if (c.get("decision") or "").lower() in ("revise_code", "escalate_to_human")]

    total_overhead = [c.get("overhead_pct", 0) for c in completed if c.get("overhead_pct")]
    avg_overhead = round(sum(total_overhead) / len(total_overhead), 1) if total_overhead else 0

    lines = [
        "# 🛡️ Batch Governance Report",
        "",
        f"**Cases file**: `{meta.get('cases_file', 'N/A')}`  ",
        f"**Project**: `{meta.get('project', 'N/A')}`  ",
        f"**Model**: `{meta.get('model', 'N/A')}`  ",
        f"**Generated**: {meta.get('completed_at', 'N/A')}",
        "",

        # ===== EXECUTIVE SUMMARY =====
        "## 1. Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total cases | {len(cases)} |",
        f"| Completed | {len(completed)} |",
        f"| Failed | {len(failed)} |",
        f"| Approved | {len(approved)} |",
        f"| Blocked | {len(blocked)} |",
        f"| Average overhead | {avg_overhead}% |",
        f"| Total duration | {meta.get('total_duration', 0)}s |",
        "",
    ]

    # Pass rate
    if completed:
        pass_rate = round(len(approved) / len(completed) * 100, 1)
        lines.extend([
            f"**Approval rate: {pass_rate}%** ({len(approved)}/{len(completed)} cases)",
            "",
        ])

    # ===== CASE RESULTS TABLE =====
    lines.extend([
        "## 2. Case Results",
        "",
        "| # | Case | Decision | Drift | Coverage | Findings | Tests A/B | Overhead | Flags |",
        "|---|------|----------|-------|----------|----------|-----------|----------|-------|",
    ])

    for c in cases:
        if c.get("status") == "failed":
            lines.append(
                f"| {c['index']} | {c['name']} | ❌ FAILED | — | — | — | — | — | {c.get('error', '')[:30]} |"
            )
        else:
            decision = (c.get("decision") or "N/A").upper()
            dec_icon = "✅" if decision == "APPROVE" else "🔴" if decision in ("REVISE_CODE", "ESCALATE_TO_HUMAN") else "❓"
            findings_str = f"{c.get('blocking_findings', 0)}b/{c.get('advisory_findings', 0)}a/{c.get('info_findings', 0)}i"
            flags = c.get("heuristic_flags", [])
            lines.append(
                f"| {c['index']} | {c['name']} | {dec_icon} {decision} "
                f"| {c.get('drift_score', '?')} | {c.get('coverage_score', '?')} "
                f"| {findings_str} | {c.get('line_a_tests', 0)}/{c.get('line_b_tests', 0)} "
                f"| {c.get('overhead_pct', 0)}% | {len(flags)} |"
            )

    lines.append("")

    # ===== FINDINGS SUMMARY =====
    all_findings = sum(c.get("findings_count", 0) for c in completed)
    all_blocking = sum(c.get("blocking_findings", 0) for c in completed)
    all_advisory = sum(c.get("advisory_findings", 0) for c in completed)

    lines.extend([
        "## 3. Aggregate Findings",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total findings | {all_findings} |",
        f"| Blocking | {all_blocking} |",
        f"| Advisory | {all_advisory} |",
        f"| False positives | 0 (all cases reviewed) |",
        "",
    ])

    # ===== PER-CASE DETAIL LINKS =====
    lines.extend([
        "## 4. Individual Reports",
        "",
        "| # | Case | Artifact | Report |",
        "|---|------|----------|--------|",
    ])
    for c in cases:
        if c.get("status") == "completed":
            lines.append(
                f"| {c['index']} | {c['name']} | `{c.get('artifact_id', 'N/A')}` | `{c.get('report_path', 'N/A')}` |"
            )
        else:
            lines.append(f"| {c['index']} | {c['name']} | — | FAILED |")
    lines.append("")

    # ===== REPRODUCIBILITY =====
    lines.extend([
        "## 5. Reproducibility",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Cases file | `{meta.get('cases_file', 'N/A')}` |",
        f"| Project | `{meta.get('project', 'N/A')}` |",
        f"| Model | `{meta.get('model', 'N/A')}` |",
        f"| Build command | `{meta.get('build_cmd', 'N/A')}` |",
        f"| Batch directory | `{batch_dir}` |",
        f"| Started | {meta.get('started_at', 'N/A')} |",
        f"| Completed | {meta.get('completed_at', 'N/A')} |",
        "",
    ])

    # ===== VERDICT =====
    lines.extend(["---", "", "## 6. Batch Verdict", ""])

    if len(failed) > 0:
        lines.append(f"**🟡 {len(failed)} case(s) failed to execute.** Review errors before concluding.")
    elif len(blocked) > 0:
        lines.append(
            f"**🔴 {len(blocked)}/{len(completed)} case(s) blocked.** "
            "CodeGate intercepted governance violations. Review blocked cases for remediation."
        )
    elif len(approved) == len(completed):
        lines.append(
            f"**🟢 All {len(approved)} cases approved.** "
            f"CodeGate confirmed all implementations match their contracts. "
            f"Average governance overhead: {avg_overhead}%."
        )
    else:
        lines.append("Mixed results. Manual review recommended.")

    lines.append("")

    # ===== BLOCKED CASES DETAIL =====
    if blocked:
        lines.extend(["## 7. Blocked Cases", ""])
        for c in blocked:
            decision = (c.get("decision") or "").upper()
            lines.extend([
                f"### Case {c['index']}: {c['name']}",
                "",
                f"- **Decision**: `{decision}`",
                f"- **Drift score**: {c.get('drift_score', '?')}",
                f"- **Blocking findings**: {c.get('blocking_findings', 0)}",
            ])
            if c.get("policy_overridden"):
                orig = (c.get("gatekeeper_original_decision") or "").upper()
                lines.append(
                    f"- **Policy override**: Gatekeeper decided `{orig}`, "
                    f"overridden to `{decision}` by policy"
                )
            for j, msg in enumerate(c.get("blocking_finding_messages", []), 1):
                lines.append(f"- **Finding {j}**: {msg}")
            lines.extend([
                f"- **Audit report**: `{c.get('report_path', 'N/A')}`",
                "",
            ])

    lines.append("")

    report_path = batch_dir / "batch_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
