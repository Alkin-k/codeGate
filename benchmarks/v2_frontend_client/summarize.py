#!/usr/bin/env python3
"""Summarize benchmark results and validate against expected outcomes.

Reads a test_results/<run_dir>/ and compares each scenario's actual
results against expected_outcomes.yaml.

Usage:
    .venv/bin/python benchmarks/v2_frontend_client/summarize.py \
        test_results/v2_security_gate_full_rerun_20260429
    .venv/bin/python benchmarks/v2_frontend_client/summarize.py \
        test_results/v2_benchmark_20260429_140000 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

OUTCOMES_FILE = Path(__file__).parent / "expected_outcomes.yaml"


def load_expected_outcomes(outcomes_file: Path = OUTCOMES_FILE) -> dict[str, dict]:
    """Load expected outcomes keyed by scenario ID."""
    with open(outcomes_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {o["scenario"]: o for o in data.get("outcomes", [])}


def find_artifacts(run_dir: Path) -> dict[str, dict]:
    """Find and load summary.json + policy_result.json from a run directory.

    Handles two directory structures:
      1. run_dir/<scenario_id>/<work_item_id>/summary.json  (old format)
      2. run_dir/<scenario_id>/summary.json                 (new format from run.py)
    """
    results = {}

    for scenario_dir in sorted(run_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue

        scenario_id = scenario_dir.name

        # Skip non-scenario directories
        if scenario_id.startswith(".") or scenario_id in ("__pycache__",):
            continue

        summary = None
        policy_result = None

        # Format 1: scenario_dir/<work_item_id>/summary.json
        for sub in scenario_dir.iterdir():
            if sub.is_dir():
                s = sub / "summary.json"
                p = sub / "policy_result.json"
                if s.exists():
                    summary = json.loads(s.read_text(encoding="utf-8"))
                    if p.exists():
                        policy_result = json.loads(p.read_text(encoding="utf-8"))
                    break

        # Format 2: scenario_dir/summary.json
        if summary is None:
            s = scenario_dir / "summary.json"
            p = scenario_dir / "policy_result.json"
            if s.exists():
                summary = json.loads(s.read_text(encoding="utf-8"))
                if p.exists():
                    policy_result = json.loads(p.read_text(encoding="utf-8"))

        if summary is not None:
            results[scenario_id] = {
                "summary": summary,
                "policy_result": policy_result,
            }

    return results


def validate_outcome(
    scenario_id: str,
    actual: dict,
    expected: dict,
) -> dict:
    """Validate a single scenario against expected outcome.

    Returns a dict with:
      - scenario_id
      - status: "pass" | "fail" | "warn"
      - checks: list of check results
    """
    summary = actual["summary"]
    policy_result = actual.get("policy_result") or {}
    decision = summary.get("decision", "unknown")

    checks = []

    # Check expected_decision
    if "expected_decision" in expected:
        exp = expected["expected_decision"]
        if isinstance(exp, str):
            ok = decision == exp
            checks.append({
                "check": "expected_decision",
                "expected": exp,
                "actual": decision,
                "pass": ok,
            })
        elif isinstance(exp, list):
            ok = decision in exp
            checks.append({
                "check": "expected_decision (any of)",
                "expected": exp,
                "actual": decision,
                "pass": ok,
            })

    # Check must_not_be
    if "must_not_be" in expected:
        forbidden = expected["must_not_be"]
        ok = decision != forbidden
        checks.append({
            "check": "must_not_be",
            "forbidden": forbidden,
            "actual": decision,
            "pass": ok,
        })

    # Check must_not_have_security_violations
    if expected.get("must_not_have_security_violations"):
        sec_violations = policy_result.get("security", {}).get(
            "security_violations", []
        )
        ok = len(sec_violations) == 0
        checks.append({
            "check": "no_security_violations",
            "actual_count": len(sec_violations),
            "violations": sec_violations,
            "pass": ok,
        })

    # Check expected_security_warnings
    if "expected_security_warnings" in expected:
        exp_warnings = expected["expected_security_warnings"]
        sec_warnings = policy_result.get("security", {}).get(
            "security_warnings", []
        )
        # Check that each expected warning prefix appears in at least one warning
        for exp_w in exp_warnings:
            found = any(exp_w in w for w in sec_warnings)
            checks.append({
                "check": f"security_warning_present({exp_w})",
                "found": found,
                "pass": found,
            })

    # Check expected_security_triggers
    triggers = policy_result.get("security", {}).get("rule_triggers", [])
    trigger_rules = [t.get("rule", "") for t in triggers]

    if "expected_security_triggers" in expected:
        exp_triggers = expected["expected_security_triggers"]

        for exp_t in exp_triggers:
            found = exp_t in trigger_rules
            checks.append({
                "check": f"security_trigger({exp_t})",
                "found": found,
                "pass": found,
                "note": "soft — LLM may produce different implementation shape",
            })

    # Check expected_security_triggers_any_of
    if "expected_security_triggers_any_of" in expected:
        exp_triggers = expected["expected_security_triggers_any_of"]
        found_rules = [rule for rule in exp_triggers if rule in trigger_rules]
        ok = bool(found_rules)
        checks.append({
            "check": "security_trigger_any_of",
            "expected_any_of": exp_triggers,
            "found": found_rules,
            "pass": ok,
            "note": "soft — unsafe implementation shape may vary across LLM runs",
        })

    # Overall status
    critical_failed = any(
        not c["pass"]
        for c in checks
        if c["check"] in ("must_not_be", "expected_decision", "no_security_violations")
    )
    soft_failed = any(not c["pass"] for c in checks)

    if critical_failed:
        status = "FAIL"
    elif soft_failed:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "scenario_id": scenario_id,
        "decision": decision,
        "status": status,
        "checks": checks,
    }


def print_matrix(results: dict[str, dict]):
    """Print the result matrix as a markdown table."""
    print()
    print("## Result Matrix")
    print()
    print("| Scenario | Decision | Original | Drift | Cov | Findings | Blocking | Violations |")
    print("|----------|----------|----------|-------|-----|----------|----------|------------|")

    for sid, data in results.items():
        s = data["summary"]
        p = data.get("policy_result") or {}
        violations = s.get("policy_violations", [])
        sec_v = p.get("security", {}).get("security_violations", [])

        violation_summary = ""
        if sec_v:
            violation_summary = f"SEC: {len(sec_v)}"
        if violations:
            non_sec = [v for v in violations if not v.startswith("[SECURITY]")]
            if non_sec:
                if violation_summary:
                    violation_summary += " + "
                violation_summary += f"Policy: {len(non_sec)}"
        if not violation_summary:
            violation_summary = "—"

        print(
            f"| {sid:<30s} | {s.get('decision', '?'):<8s} | "
            f"{s.get('gatekeeper_original_decision', '?'):<8s} | "
            f"{s.get('drift_score', '?'):>5} | "
            f"{s.get('coverage_score', '?'):>3} | "
            f"{s.get('findings_count', '?'):>8} | "
            f"{s.get('blocking_findings', '?'):>8} | "
            f"{violation_summary} |"
        )


def print_validation(validations: list[dict]):
    """Print validation results."""
    print()
    print("## Validation Against Expected Outcomes")
    print()

    for v in validations:
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(v["status"], "?")
        print(f"{icon} **{v['scenario_id']}** — {v['decision']} — {v['status']}")
        for c in v["checks"]:
            c_icon = "✓" if c["pass"] else "✗"
            detail = ""
            if "expected" in c:
                detail = f"expected={c['expected']}, actual={c['actual']}"
            elif "forbidden" in c:
                detail = f"forbidden={c['forbidden']}, actual={c['actual']}"
            elif "actual_count" in c:
                detail = f"count={c['actual_count']}"
            elif "expected_any_of" in c:
                detail = f"expected_any_of={c['expected_any_of']}, found={c['found']}"
            elif "found" in c:
                detail = f"found={c['found']}"
            note = f" ({c['note']})" if c.get("note") else ""
            print(f"  {c_icon} {c['check']}: {detail}{note}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Summarize and validate CodeGate benchmark results"
    )
    parser.add_argument(
        "run_dir",
        help="Path to test_results/<run_id> directory",
    )
    parser.add_argument(
        "--outcomes",
        default=str(OUTCOMES_FILE),
        help="Path to expected_outcomes.yaml",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of markdown",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"Error: {run_dir} does not exist")
        sys.exit(1)

    # Load data
    results = find_artifacts(run_dir)
    if not results:
        print(f"No artifacts found in {run_dir}")
        sys.exit(1)

    expected = load_expected_outcomes(Path(args.outcomes))

    # Validate
    validations = []
    for sid, data in results.items():
        if sid in expected:
            v = validate_outcome(sid, data, expected[sid])
            validations.append(v)

    if args.json:
        output = {
            "run_dir": str(run_dir),
            "scenarios": len(results),
            "validated": len(validations),
            "results": {
                sid: {
                    "decision": d["summary"].get("decision"),
                    "drift_score": d["summary"].get("drift_score"),
                    "coverage_score": d["summary"].get("coverage_score"),
                    "findings_count": d["summary"].get("findings_count"),
                    "blocking_findings": d["summary"].get("blocking_findings"),
                    "policy_violations": d["summary"].get("policy_violations", []),
                }
                for sid, d in results.items()
            },
            "validations": validations,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"# Benchmark Summary: {run_dir.name}")
        print(f"\n> Scenarios found: {len(results)}")
        print(f"> Validated against expected outcomes: {len(validations)}")

        print_matrix(results)

        if validations:
            print_validation(validations)

            # Summary line
            passed = sum(1 for v in validations if v["status"] == "PASS")
            warned = sum(1 for v in validations if v["status"] == "WARN")
            failed = sum(1 for v in validations if v["status"] == "FAIL")
            print(
                f"**Summary: {passed} PASS, {warned} WARN, {failed} FAIL "
                f"out of {len(validations)} validated**"
            )


if __name__ == "__main__":
    main()
