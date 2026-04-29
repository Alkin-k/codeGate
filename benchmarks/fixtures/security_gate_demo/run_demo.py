#!/usr/bin/env python3
"""Security Gate Demo — zero-LLM reproducible demonstration.

Runs the CodeGate security policy gate (SEC-1~5) on pre-built fixtures
to demonstrate the T5 vs T6 case study. No API keys, no LLM calls,
no network access required.

Usage:
    .venv/bin/python benchmarks/fixtures/security_gate_demo/run_demo.py

What it does:
    1. Reads baseline + T5/T6 fixture TypeScript files
    2. Runs the deterministic structural extractor (regex, no LLM)
    3. Computes baseline diff (what patterns changed)
    4. Runs SEC-1~5 security policy rules
    5. Prints a side-by-side comparison of decisions
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

FIXTURE_DIR = Path(__file__).resolve().parent


def load_fixture(fixture_name: str) -> dict[str, str]:
    """Load all .ts/.vue files from a fixture directory."""
    fixture_path = FIXTURE_DIR / fixture_name / "src"
    files = {}
    if not fixture_path.exists():
        print(f"ERROR: Fixture directory not found: {fixture_path}")
        sys.exit(1)
    for f in fixture_path.rglob("*"):
        if f.is_file() and f.suffix in (".ts", ".tsx", ".vue"):
            rel = str(f.relative_to(FIXTURE_DIR / fixture_name))
            files[rel] = f.read_text(encoding="utf-8")
    return files


def run_security_gate(
    baseline_files: dict[str, str],
    changed_files: dict[str, str],
    scenario_name: str,
) -> dict:
    """Run the deterministic security gate pipeline.

    Steps:
        1. Extract structural patterns from baseline & changed files
        2. Compute baseline diff (removed / added / preserved patterns)
        3. Evaluate SEC-1~5 security policies
    """
    from codegate.analysis.baseline_diff import (
        BaselineDiffResult,
        PatternMatch,
        _extract_patterns_regex_fallback,
    )
    from codegate.policies.security import evaluate_security_policies

    # Step 1 & 2: Compute baseline diff (regex only, no LLM)
    result = BaselineDiffResult()

    common_files = set(baseline_files.keys()) & set(changed_files.keys())

    for filepath in sorted(common_files):
        b_patterns = _extract_patterns_regex_fallback(
            filepath, baseline_files[filepath]
        )
        c_patterns = _extract_patterns_regex_fallback(
            filepath, changed_files[filepath]
        )

        baseline_set = {(p.pattern.strip(), p.kind) for p in b_patterns}
        current_set = {(p.pattern.strip(), p.kind) for p in c_patterns}

        for p in b_patterns:
            key = (p.pattern.strip(), p.kind)
            if key in (baseline_set - current_set):
                result.removed_from_baseline.append(p)
            elif key in (baseline_set & current_set):
                result.unchanged_baseline.append(p)

        for p in c_patterns:
            key = (p.pattern.strip(), p.kind)
            if key in (current_set - baseline_set):
                result.added_not_in_baseline.append(p)

    # Step 3: Run security policies
    diff_dict = result.to_dict()
    sec_result = evaluate_security_policies(diff_dict, changed_files)

    return {
        "scenario": scenario_name,
        "structural_diff": {
            "removed": len(result.removed_from_baseline),
            "added": len(result.added_not_in_baseline),
            "preserved": len(result.unchanged_baseline),
        },
        "security_violations": sec_result.security_violations,
        "security_warnings": sec_result.security_warnings,
        "override_decision": sec_result.override_decision,
        "rule_triggers": [
            {"rule": t.get("rule", "?"), "message": t.get("message", "")}
            for t in sec_result.rule_triggers
        ],
    }


def print_result(result: dict, color: str = "") -> None:
    """Print a single scenario result."""
    scenario = result["scenario"]
    diff = result["structural_diff"]
    violations = result["security_violations"]
    warnings = result["security_warnings"]
    decision = result["override_decision"]
    triggers = result["rule_triggers"]

    # Decision badge
    if decision is None:
        badge = "✅ APPROVE (no security violations)"
    elif decision == "revise_code":
        badge = "⚠️  REVISE_CODE"
    else:
        badge = f"🚨 {decision.upper()}"

    print(f"\n{'=' * 70}")
    print(f"  {scenario}")
    print(f"{'=' * 70}")
    print(f"  Decision: {badge}")
    print(f"  Structural diff: {diff['removed']} removed, {diff['added']} added, {diff['preserved']} preserved")

    if violations:
        print(f"\n  Violations ({len(violations)}):")
        for v in violations:
            print(f"    ❌ {v}")

    if warnings:
        print(f"\n  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    ⚠️  {w}")

    if triggers:
        print(f"\n  Rule triggers:")
        for t in triggers:
            print(f"    📋 [{t['rule']}] {t['message'][:80]}")

    print()


def main():
    print("=" * 70)
    print("  CodeGate Security Gate Demo — Zero-LLM Reproducible")
    print("  Demonstrates: T5 (constrained) vs T6 (unconstrained)")
    print("=" * 70)

    # Load fixtures
    baseline = load_fixture("baseline")
    t5 = load_fixture("t5_constrained")
    t6 = load_fixture("t6_unconstrained")

    print(f"\n  Baseline files: {list(baseline.keys())}")
    print(f"  T5 files:       {list(t5.keys())}")
    print(f"  T6 files:       {list(t6.keys())}")

    # Run security gate on both scenarios
    t5_result = run_security_gate(
        baseline, t5, "T5: Constrained Guest Mode (scoped meta.guest)"
    )
    t6_result = run_security_gate(
        baseline, t6, "T6: Unconstrained Public Route Exposure (meta.public: true)"
    )

    # Print results
    print_result(t5_result)
    print_result(t6_result)

    # Summary comparison
    print("=" * 70)
    print("  SUMMARY COMPARISON")
    print("=" * 70)
    print(f"  {'':30s} {'T5 (safe)':20s} {'T6 (unsafe)':20s}")
    print(f"  {'-' * 70}")
    print(f"  {'Implementation':30s} {'meta.guest: true':20s} {'meta.public: true':20s}")
    print(f"  {'Scope':30s} {'Per-route':20s} {'Global (all routes)':20s}")
    print(f"  {'SEC violations':30s} {len(t5_result['security_violations']):20d} {len(t6_result['security_violations']):20d}")
    print(f"  {'Decision':30s} {t5_result['override_decision'] or 'approve':20s} {t6_result['override_decision'] or 'approve':20s}")
    print()
    print("  Key insight: Same feature request ('add guest mode'),")
    print("  different safety contract, different deterministic outcome.")
    print()

    # Exit code: 0 if T5=approve and T6=has violations
    t5_ok = t5_result["override_decision"] is None  # no violations = approve
    t6_ok = len(t6_result["security_violations"]) > 0  # should have violations
    if t5_ok and t6_ok:
        print("  ✅ Demo passed: T5 approved, T6 caught by security gate.")
        return 0
    else:
        print("  ❌ Demo FAILED: unexpected results.")
        if not t5_ok:
            print(f"    T5 should approve but got: {t5_result['override_decision']}")
        if not t6_ok:
            print(f"    T6 should have violations but got: {t6_result['security_violations']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
