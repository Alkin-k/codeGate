"""Test: Audit Evidence Persistence Pipeline.

Validates that structural_diff.json, raw_review_findings.json, and
suppressed_findings.json are correctly persisted through the full
reviewer → state → artifact_store chain.

This test bypasses the LLM by directly invoking the post-filter and
state persistence logic with controlled inputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codegate.analysis.baseline_diff import (
    BaselineDiffResult,
    compute_baseline_diff,
    post_filter_findings,
)
from codegate.schemas.review import ReviewFinding
from codegate.schemas.work_item import WorkItem
from codegate.store.artifact_store import ArtifactStore
from codegate.workflow.state import GovernanceState


def test_audit_evidence_persistence(tmp_path) -> None:
    """Test the full persistence chain for audit evidence.

    Simulates:
    1. compute_baseline_diff() → structural_diff
    2. LLM produces 3 findings (1 ghost + 2 real)
    3. post_filter_findings() → suppresses 1 ghost
    4. State stores raw/suppressed/final findings
    5. ArtifactStore persists all 3 JSON files + summary
    """
    print("\n" + "=" * 70)
    print("🔬 AUDIT EVIDENCE PERSISTENCE TEST")
    print("=" * 70)

    # --- Step 1: Compute structural diff ---
    baseline = {
        "ConvertController.java": (
            "@RestController\n"
            "public class ConvertController {\n"
            "    @PostMapping(\"/api/convert\")\n"
            "    public ApiResponse<ConvertResponse> convert(\n"
            '        @RequestParam(value = "dpi", required = false) @Min(72) Integer dpi\n'
            "    ) { return null; }\n"
            "}\n"
        ),
        "GlobalExceptionHandler.java": (
            "@RestControllerAdvice\n"
            "public class GlobalExceptionHandler {\n"
            "    @ExceptionHandler(IllegalArgumentException.class)\n"
            "    public ResponseEntity<ApiResponse<Void>> handleBadRequest(IllegalArgumentException ex) {\n"
            "        return null;\n"
            "    }\n"
            "}\n"
        ),
    }

    current = {
        "ConvertController.java": (
            "@RestController\n"
            "public class ConvertController {\n"
            "    @PostMapping(\"/api/convert\")\n"
            "    public ApiResponse<ConvertResponse> convert(\n"
            '        @RequestParam(value = "dpi", required = false) Integer dpi\n'
            "    ) {\n"
            "        if (dpi != null && (dpi < 72 || dpi > 600)) {\n"
            '            throw new IllegalArgumentException("INVALID_DPI");\n'
            "        }\n"
            "        return null;\n"
            "    }\n"
            "}\n"
        ),
        "GlobalExceptionHandler.java": baseline["GlobalExceptionHandler.java"],
    }

    diff_result = compute_baseline_diff(baseline, current)

    print(f"  Structural diff: {len(diff_result.removed_from_baseline)} removed, "
          f"{len(diff_result.added_not_in_baseline)} added, "
          f"{len(diff_result.unchanged_baseline)} preserved")

    # --- Step 2: Simulate LLM producing findings (including 1 ghost) ---
    llm_findings = [
        ReviewFinding(
            category="drift", severity="P1",
            message="Removed @Min(72) annotation from dpi parameter, violating baseline preservation.",
            contract_clause_ref="constraints[0]",
            code_location="ConvertController.java:5",
            blocking=True,
            suggestion="Restore @Min(72) annotation.",
        ),
        ReviewFinding(
            category="drift", severity="P1",
            message="Removed HandlerMethodValidationException handler from GlobalExceptionHandler, "
                    "which was handling validation errors.",
            contract_clause_ref="constraints[0]",
            code_location="GlobalExceptionHandler.java:10",
            blocking=True,
            suggestion="Restore the handler.",
        ),
        ReviewFinding(
            category="completeness", severity="P1",
            message="No MockMvc tests provided for boundary cases.",
            contract_clause_ref="goal[1]",
            code_location="(missing)",
            blocking=True,
            suggestion="Add MockMvc tests.",
        ),
    ]

    print(f"  LLM raw findings: {len(llm_findings)}")

    # --- Step 3: Post-filter ---
    raw_findings = list(llm_findings)
    final_findings, suppressed = post_filter_findings(
        llm_findings, diff_result, baseline_content=baseline
    )

    print(f"  Final findings: {len(final_findings)}")
    print(f"  Suppressed: {len(suppressed)}")
    for s in suppressed:
        print(f"    [{s.severity}] {s.message[:80]}")

    # --- Step 4: Build state ---
    work_item = WorkItem(
        raw_request="DPI validation test",
        context="fixture",
        constraints=["preserve @Min(72)"],
        risk_level="medium",
    )

    state = GovernanceState(
        work_item=work_item,
        review_findings=final_findings,
        raw_review_findings=raw_findings,
        suppressed_findings=[
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
        ],
        structural_diff=diff_result.to_dict(),
    )

    # --- Step 5: Persist ---
    store = ArtifactStore(base_dir=tmp_path)
    run_dir = store.save_run(state)

    # --- Step 6: Verify persisted files ---
    print("\n--- Verification ---")
    results = {}

    # Check structural_diff.json
    sd_path = run_dir / "structural_diff.json"
    sd_exists = sd_path.exists()
    results["structural_diff"] = sd_exists
    print(f"  structural_diff.json: {'✅' if sd_exists else '❌'}")
    if sd_exists:
        sd = json.loads(sd_path.read_text())
        print(f"    removed: {len(sd['removed_from_baseline'])}, "
              f"added: {len(sd['added_not_in_baseline'])}, "
              f"preserved: {len(sd['unchanged_baseline'])}")

    # Check raw_review_findings.json
    raw_path = run_dir / "raw_review_findings.json"
    raw_exists = raw_path.exists()
    results["raw_review_findings"] = raw_exists
    print(f"  raw_review_findings.json: {'✅' if raw_exists else '❌'}")
    if raw_exists:
        raw = json.loads(raw_path.read_text())
        print(f"    {len(raw)} findings (LLM original)")

    # Check suppressed_findings.json
    sup_path = run_dir / "suppressed_findings.json"
    sup_exists = sup_path.exists()
    results["suppressed_findings"] = sup_exists
    print(f"  suppressed_findings.json: {'✅' if sup_exists else '❌'}")
    if sup_exists:
        sup = json.loads(sup_path.read_text())
        print(f"    {len(sup)} suppressed findings:")
        for f in sup:
            print(f"      [{f['severity']}] {f['message'][:60]}")
            print(f"      reason: {f['suppression_reason']}")

    # Check summary.json
    sum_path = run_dir / "summary.json"
    sum_data = json.loads(sum_path.read_text())
    fc = sum_data.get("findings_count", -1)
    rfc = sum_data.get("raw_findings_count", -1)
    sfc = sum_data.get("suppressed_findings_count", -1)
    results["summary_counts"] = (fc, rfc, sfc)
    print(f"  summary.json:")
    print(f"    findings_count: {fc}")
    print(f"    raw_findings_count: {rfc}")
    print(f"    suppressed_findings_count: {sfc}")

    # Verify invariant: raw = final + suppressed
    invariant_ok = rfc == fc + sfc
    results["invariant"] = invariant_ok
    print(f"  invariant (raw == final + suppressed): {'✅' if invariant_ok else '❌'} ({rfc} == {fc} + {sfc})")

    # Overall
    all_ok = (
        sd_exists and raw_exists and sup_exists and invariant_ok
        and fc == 2 and rfc == 3 and sfc == 1
    )
    results["verdict"] = "PASS" if all_ok else "FAIL"

    if all_ok:
        print(f"\n✅ AUDIT EVIDENCE PERSISTENCE TEST PASSED")
        print(f"  Artifact: {run_dir}")
    else:
        print(f"\n❌ TEST FAILED")

    # Save test result
    result_path = run_dir / "audit_evidence_test_result.json"
    result_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    assert all_ok, f"Audit evidence persistence failed: {results}"


if __name__ == "__main__":
    from pathlib import Path as _Path
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/codegate-audit-test"
    _p = _Path(output_dir)
    _p.mkdir(parents=True, exist_ok=True)
    test_audit_evidence_persistence(_p)
