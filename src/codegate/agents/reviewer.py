"""Contract Drift Reviewer — audits implementation against the approved contract.

This is CodeGate's core differentiator: checking not just "is the code good?"
but "does the code match what was agreed upon?"

Architecture (as of V2.4):
  1. STRUCTURAL PRE-CHECK (deterministic) — code diffs baseline vs current
  2. LLM REVIEW (interpretive) — auditor judges contract compliance
  3. POST-FILTER (deterministic) — suppresses false positives

Design principle: facts by code, judgment by LLM.
"""

from __future__ import annotations

import logging
from typing import Optional

from codegate.analysis.baseline_diff import (
    BaselineDiffResult,
    compute_baseline_diff,
    post_filter_findings,
)
from codegate.config import get_config
from codegate.llm import call_llm_json, load_prompt
from codegate.schemas.review import ReviewFinding
from codegate.schemas.work_item import WorkflowStatus
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


def run_reviewer(state: GovernanceState) -> GovernanceState:
    """Run the Review Gate node.

    Pipeline:
      1. compute_baseline_diff() — deterministic structural diff
      2. _build_review_prompt() — inject structured diff into LLM prompt
      3. call_llm_json() — LLM interpretive review
      4. post_filter_findings() — suppress false positives
    """
    if state.contract is None or state.execution_report is None:
        state.error = "Cannot review: missing contract or execution report"
        return state

    config = get_config()
    model = config.models.review_model
    system_prompt = load_prompt("reviewer")

    # --- Step 1: Structural Pre-Check (deterministic) ---
    diff_result: Optional[BaselineDiffResult] = None
    report = state.execution_report

    if report.baseline_content and report.files_content:
        diff_result = compute_baseline_diff(
            baseline_content=report.baseline_content,
            files_content=report.files_content,
        )
        logger.info(
            f"Structural pre-check: "
            f"{len(diff_result.removed_from_baseline)} removed, "
            f"{len(diff_result.added_not_in_baseline)} added, "
            f"{len(diff_result.unchanged_baseline)} preserved"
        )

    # --- Step 2: Build prompt with structured diff ---
    user_message = _build_review_prompt(state, diff_result)

    # --- Step 3: LLM Review ---
    result, tokens = call_llm_json(
        model=model,
        system_prompt=system_prompt,
        user_message=user_message,
    )
    state.add_tokens("reviewer", tokens)

    try:
        findings, drift_score, coverage_score = _parse_review(result)

        # --- Step 4: Post-filter false positives ---
        raw_findings = list(findings)  # preserve LLM's original output
        suppressed = []
        if diff_result is not None:
            findings, suppressed = post_filter_findings(
                findings,
                diff_result,
                baseline_content=report.baseline_content or None,
            )

        state.review_findings = findings
        state.review_drift_score = drift_score
        state.review_coverage_score = coverage_score

        # --- Store audit evidence ---
        if diff_result is not None:
            state.structural_diff = diff_result.to_dict()
        state.raw_review_findings = raw_findings
        state.suppressed_findings = [
            {
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
                "contract_clause_ref": f.contract_clause_ref,
                "code_location": f.code_location,
                "blocking": f.blocking,
                "suppression_reason": "ghost_pattern_not_in_baseline",
            }
            for f in suppressed
        ]

        blocking_count = sum(1 for f in findings if f.blocking)
        logger.info(
            f"Review complete: {len(findings)} findings "
            f"({blocking_count} blocking), "
            f"drift={drift_score}, coverage={coverage_score}"
        )
        if suppressed:
            logger.info(
                f"Post-filter suppressed {len(suppressed)} false positive(s): "
                + "; ".join(f.message[:60] for f in suppressed)
            )
    except Exception as e:
        logger.error(f"Failed to parse review findings: {e}")
        state.error = f"Review parsing failed: {e}"

    return state


def _build_review_prompt(
    state: GovernanceState,
    diff_result: Optional[BaselineDiffResult] = None,
) -> str:
    """Build the prompt for the reviewer with contract + implementation side by side."""
    contract = state.contract
    report = state.execution_report
    assert contract is not None and report is not None

    parts = [
        "## APPROVED CONTRACT\n",
        "### Goals",
    ]
    for i, g in enumerate(contract.goals):
        parts.append(f"  [{i}] {g}")

    parts.append("\n### Non-Goals")
    for i, ng in enumerate(contract.non_goals):
        parts.append(f"  [{i}] {ng}")

    parts.append("\n### Acceptance Criteria")
    for i, ac in enumerate(contract.acceptance_criteria):
        parts.append(f"  [{i}] [{ac.priority}] {ac.description}")
        parts.append(f"      Verify: {ac.verification}")

    if contract.constraints:
        parts.append("\n### Constraints")
        for i, c in enumerate(contract.constraints):
            parts.append(f"  [{i}] {c}")

    if contract.assumed_defaults:
        parts.append("\n### Assumed Defaults (watch for these)")
        for d in contract.assumed_defaults:
            parts.append(f"  - {d.topic}: {d.assumed_value} ({d.reason})")

    parts.append("\n---\n")
    parts.append("## IMPLEMENTATION\n")
    parts.append(f"### Executor Summary\n{report.summary}\n")
    parts.append(f"### Executor: {report.executor_name}\n")
    parts.append(f"### Files\n{', '.join(report.file_list) if report.file_list else 'N/A'}\n")

    if report.goals_addressed:
        parts.append(f"### Goals Addressed (self-reported): {report.goals_addressed}")
    if report.unresolved_items:
        parts.append("\n### Unresolved Items (self-reported)")
        for item in report.unresolved_items:
            parts.append(f"  - {item}")

    # Prefer structured files_content over flat code_output
    if report.files_content:
        parts.append("\n### File Contents (from real executor)\n")
        for filepath, content in sorted(report.files_content.items()):
            parts.append(f"#### {filepath}\n```\n{content}\n```\n")
    else:
        parts.append(f"\n### Code\n```\n{report.code_output}\n```\n")

    # --- Structural Pre-Check Results (GROUND TRUTH) ---
    if diff_result is not None:
        parts.append(
            "\n### 🔬 STRUCTURAL BASELINE DIFF (deterministic — computed by code, not LLM)\n\n"
            "The following diff was computed by comparing the CLEAN BASELINE "
            "(git HEAD before any changes) against the CURRENT implementation. "
            "This is **ground truth** — use it as the authoritative source for "
            "Section 7 (Silent Behavioral Change) auditing.\n\n"
            "**Rules for using this diff:**\n"
            "- Items in 🔴 REMOVED FROM BASELINE were genuinely in the original code "
            "and are now missing. These are potential silent behavioral changes — "
            "flag them as drift findings.\n"
            "- Items in 🟢 ADDED were NOT in the original code. The executor created them. "
            "If they were also removed in a later iteration, that is cleanup, "
            "NOT a behavioral change. Do NOT flag removal of executor-added patterns.\n"
            "- Items in ⚪ PRESERVED are still present and unchanged — no action needed.\n"
            "- **DO NOT create any 'removed' drift finding for a pattern that is NOT "
            "listed in 🔴 REMOVED FROM BASELINE.** If it's not in the removed list, "
            "it was never in the baseline.\n\n"
        )
        parts.append(diff_result.summary_text())
        parts.append("")

    # --- Raw Baseline Content (for context) ---
    if report.baseline_content and diff_result is None:
        # Fallback: if structural diff wasn't computed, still show raw baseline
        parts.append(
            "\n### 📋 BASELINE CONTENT (original code before any changes)\n"
            "Use this to determine what EXISTED in the codebase before the executor "
            "made changes. When checking for 'Silent Behavioral Changes' (Section 7), "
            "compare against THIS baseline — not against a previous iteration's output.\n"
            "If a pattern (annotation, handler, method signature) exists in the baseline "
            "but is missing in the implementation, it was REMOVED by the executor.\n"
            "If a pattern does NOT exist in the baseline, the executor ADDED it — "
            "removing it in a later iteration is cleanup, not a behavioral change.\n"
        )
        for filepath, content in sorted(report.baseline_content.items()):
            parts.append(f"#### BASELINE: {filepath}\n```\n{content}\n```\n")

    # --- Timeout & Partial Evidence Warning ---
    if report.timed_out:
        parts.append("\n### ⚠️ EXECUTOR TIMED OUT\n")
        parts.append(
            "The executor was killed due to timeout. "
            "Any files shown above are PARTIAL changes found on disk after "
            "the timeout. The executor did NOT complete normally.\n"
        )
        parts.append(
            "Pay special attention to:\n"
            "- Incomplete implementations\n"
            "- Missing test stubs or unfinished methods\n"
            "- Compilation errors from half-written code\n"
        )

    # --- Post-run Validation Result ---
    if report.validation_result:
        vr = report.validation_result
        parts.append("\n### 🧪 Post-run Validation Result\n")
        parts.append(f"Command: `{vr.command}`\n")
        parts.append(f"Result: **{'PASSED' if vr.passed else 'FAILED'}** "
                      f"(exit code {vr.exit_code})\n")
        if vr.tests_run:
            parts.append(f"Tests run: {vr.tests_run}, "
                          f"failed: {vr.tests_failed}\n")
        if vr.error_summary:
            parts.append(
                f"Error summary:\n```\n{vr.error_summary}\n```\n"
            )
            parts.append(
                "**IMPORTANT**: If validation failed due to compilation errors, "
                "these are REAL defects. Report them as P0 findings with the "
                "specific error message and root cause (e.g., wrong API version, "
                "missing import, type mismatch).\n"
            )


    parts.append(
        "## Your Task\n\n"
        "Audit this implementation against the contract.\n"
        "Check: goal coverage, drift, non-goal violations, constraint compliance, "
        "correctness, security.\n\n"
        "Respond with JSON:\n"
        "```json\n"
        "{\n"
        '  "findings": [\n'
        "    {\n"
        '      "category": "drift|completeness|correctness|security|maintainability",\n'
        '      "severity": "P0|P1|P2",\n'
        '      "disposition": "blocking|advisory|info",\n'
        '      "message": "...",\n'
        '      "contract_clause_ref": "goal[0]|acceptance_criteria[1]|...",\n'
        '      "code_location": "file:line or function name",\n'
        '      "suggestion": "..."\n'
        "    }\n"
        "  ],\n"
        '  "drift_score": 0-100,\n'
        '  "coverage_score": 0-100\n'
        "}\n"
        "```"
    )

    return "\n".join(parts)


def _parse_review(data: dict) -> tuple[list[ReviewFinding], int, int]:
    """Parse LLM output into ReviewFindings + scores.

    Handles both new 'disposition' field and legacy 'blocking' boolean.
    """
    findings = []
    for f in data.get("findings", []):
        if isinstance(f, dict):
            # Determine disposition: prefer explicit 'disposition', fall back to 'blocking'
            disposition = f.get("disposition")
            if disposition not in ("blocking", "advisory", "info"):
                # Legacy: convert boolean blocking → disposition
                blocking = f.get("blocking", False)
                disposition = "blocking" if blocking else "advisory"

            findings.append(ReviewFinding(
                category=f.get("category", "correctness"),
                severity=f.get("severity", "P2"),
                disposition=disposition,
                message=f.get("message", ""),
                contract_clause_ref=f.get("contract_clause_ref", ""),
                code_location=f.get("code_location", ""),
                suggestion=f.get("suggestion", ""),
            ))

    drift_score = int(data.get("drift_score", 50))
    coverage_score = int(data.get("coverage_score", 50))

    return findings, drift_score, coverage_score

