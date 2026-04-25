"""Regenerate batch_summary.json + batch_report.md from existing artifacts.

Reads each case's codegate_artifacts to rebuild missing fields
(policy_overridden, gatekeeper_original_decision, blocking_finding_messages),
then re-generates the batch report using the current ab_batch code.

Usage:
    python scripts/regenerate_batch_report.py ab_results/batch_1777103598
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow importing from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.eval.ab_runner import _load_codegate_artifacts  # noqa: E402
from codegate.eval.ab_batch import BatchResult, _generate_batch_report, _save_batch_summary  # noqa: E402


def regenerate(batch_dir: str) -> None:
    batch_path = Path(batch_dir)

    # Load existing batch_summary.json
    summary_path = batch_path / "batch_summary.json"
    if not summary_path.exists():
        print(f"ERROR: {summary_path} not found")
        sys.exit(1)

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    metadata = data["metadata"]
    cases = data["cases"]

    print(f"Loaded {len(cases)} cases from {summary_path}")

    # Enrich each case from its codegate_artifacts
    for case in cases:
        if case.get("status") != "completed":
            continue

        # Find case directory
        case_dirs = [
            d for d in batch_path.iterdir()
            if d.is_dir() and d.name.startswith(case["name"].replace(" ", "_").lower().split("_")[0])
        ]

        # More robust: find by artifact_id
        artifact_id = case.get("artifact_id", "")
        codegate_dir = None
        for d in batch_path.iterdir():
            if not d.is_dir():
                continue
            artifacts_dir = d / "codegate_artifacts"
            if artifacts_dir.exists():
                for sub in artifacts_dir.iterdir():
                    if sub.is_dir() and sub.name == artifact_id:
                        codegate_dir = artifacts_dir
                        break
            if codegate_dir:
                break

        if not codegate_dir:
            print(f"  Case {case['index']} ({case['name']}): codegate_artifacts not found, skipping")
            continue

        # Re-load artifacts with current code
        cg = _load_codegate_artifacts(codegate_dir)

        # Enrich missing fields
        enriched = False

        if "policy_overridden" not in case or not case.get("policy_overridden"):
            if cg.get("policy_overridden"):
                case["policy_overridden"] = True
                case["gatekeeper_original_decision"] = cg.get("gatekeeper_original_decision")
                enriched = True

        # Always refresh blocking messages from artifacts (may have been truncated before)
        if True:
            findings = cg.get("findings", [])
            blocking_msgs = [
                f.get("message", "")[:300]
                for f in findings
                if f.get("disposition") == "blocking" or f.get("blocking")
            ]
            if blocking_msgs:
                case["blocking_finding_messages"] = blocking_msgs
                enriched = True

        status = "enriched" if enriched else "unchanged"
        print(f"  Case {case['index']} ({case['name']}): {status}")
        if enriched:
            print(f"    policy_overridden={case.get('policy_overridden')}")
            print(f"    gatekeeper_original={case.get('gatekeeper_original_decision')}")
            print(f"    blocking_msgs={len(case.get('blocking_finding_messages', []))}")

    # Rebuild result object
    result = BatchResult()
    result.metadata = metadata
    result.cases = cases

    # Backup old files
    old_summary = summary_path.with_suffix(".json.bak")
    old_report = (batch_path / "batch_report.md").with_suffix(".md.bak")

    if summary_path.exists():
        summary_path.rename(old_summary)
        print(f"\nBacked up: {old_summary}")

    report_path = batch_path / "batch_report.md"
    if report_path.exists():
        report_path.rename(old_report)
        print(f"Backed up: {old_report}")

    # Save enriched summary
    _save_batch_summary(batch_path, result)
    print(f"Saved: {batch_path / 'batch_summary.json'}")

    # Regenerate batch report
    new_report = _generate_batch_report(batch_path, result)
    print(f"Generated: {new_report}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/regenerate_batch_report.py <batch_dir>")
        sys.exit(1)

    regenerate(sys.argv[1])
