#!/usr/bin/env python3
"""Backend Security Gate Demo — zero-LLM reproducible demonstration.

Runs the CodeGate security policy gate (SEC-6~10) on pre-built backend
fixtures to demonstrate detection of auth removal, tenant scope deletion,
user-controlled privilege trust, and security config relaxation.

No API keys, no LLM calls, no network access required.

Usage:
    .venv/bin/python benchmarks/fixtures/backend_security_demo/run_demo.py

Scenarios:
    T7:  auth preserved        → approve
    T8:  auth removed          → escalate_to_human  (SEC-6)
    T9:  tenant scope preserved → approve
    T10: tenant scope removed  → escalate_to_human  (SEC-8)
    T11: user role trusted     → revise_code         (SEC-9)
    T12: security config relaxed → revise_code       (SEC-10)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

FIXTURE_DIR = Path(__file__).resolve().parent

# Language configs: (subdir, extensions)
LANGUAGES = [
    ("python_fastapi", {".py"}),
    ("java_spring", {".java"}),
    ("node_express", {".ts"}),
]


def load_fixture(fixture_name: str) -> Dict[str, Dict[str, str]]:
    """Load files from a fixture directory, grouped by language.

    Returns: {language_name: {relative_path: content}}
    """
    result = {}
    for lang_name, extensions in LANGUAGES:
        lang_dir = FIXTURE_DIR / fixture_name / lang_name
        files = {}
        if lang_dir.exists():
            for f in lang_dir.rglob("*"):
                if f.is_file() and f.suffix in extensions:
                    rel = str(f.relative_to(lang_dir))
                    files[rel] = f.read_text(encoding="utf-8")
        result[lang_name] = files
    return result


def run_security_gate(
    baseline_files: Dict[str, str],
    changed_files: Dict[str, str],
    language: str,
) -> dict:
    """Run the deterministic security gate pipeline on a single language."""
    from codegate.analysis.baseline_diff import (
        BaselineDiffResult,
        _extract_patterns_regex_fallback,
    )
    from codegate.policies.security import evaluate_security_policies

    result = BaselineDiffResult()
    all_files = set(baseline_files.keys()) | set(changed_files.keys())

    for filepath in sorted(all_files):
        b_content = baseline_files.get(filepath, "")
        c_content = changed_files.get(filepath, "")

        b_patterns = _extract_patterns_regex_fallback(filepath, b_content) if b_content else []
        c_patterns = _extract_patterns_regex_fallback(filepath, c_content) if c_content else []

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

    diff_dict = result.to_dict()
    sec_result = evaluate_security_policies(diff_dict, changed_files)

    return {
        "language": language,
        "structural_diff": {
            "removed": len(result.removed_from_baseline),
            "added": len(result.added_not_in_baseline),
            "preserved": len(result.unchanged_baseline),
        },
        "security_violations": sec_result.security_violations,
        "security_warnings": sec_result.security_warnings,
        "override_decision": sec_result.override_decision,
        "rule_triggers": [
            {"rule": t.get("rule", "?"), "case": t.get("case", ""),
             "decision": t.get("decision", "")}
            for t in sec_result.rule_triggers
        ],
    }


def run_scenario(
    scenario_name: str,
    scenario_dir: str,
    baseline: Dict[str, Dict[str, str]],
    expected_per_lang: Dict[str, Optional[str]],
    expected_rules: List[str],
) -> Tuple[bool, dict]:
    """Run a scenario across all languages with per-language expectations.

    expected_per_lang: {language_name: expected_decision_or_None_for_approve}
    """
    changed = load_fixture(scenario_dir)
    all_results = []
    all_pass = True

    for lang_name, _ in LANGUAGES:
        b_files = baseline.get(lang_name, {})
        c_files = changed.get(lang_name, {})

        if not b_files and not c_files:
            continue

        result = run_security_gate(b_files, c_files, lang_name)
        result["scenario"] = scenario_name
        all_results.append(result)

        # Check expected decision for this language
        expected = expected_per_lang.get(lang_name)
        actual = result["override_decision"]
        trigger_rules = {
            t.get("rule")
            for t in result.get("rule_triggers", [])
            if t.get("decision") != "advisory"
        }
        if expected is None:
            if actual is not None:
                all_pass = False
        elif actual != expected:
            all_pass = False
        elif expected_rules and not (trigger_rules & set(expected_rules)):
            result["rule_mismatch"] = (
                f"expected one of {expected_rules}, got {sorted(trigger_rules)}"
            )
            all_pass = False

    # Compute aggregate expected for display
    unique_expected = set(expected_per_lang.values())
    if unique_expected == {None}:
        display_expected = "approve"
    else:
        non_none = [v for v in unique_expected if v is not None]
        display_expected = non_none[0] if non_none else "approve"

    return all_pass, {
        "scenario": scenario_name,
        "expected": display_expected,
        "expected_per_lang": expected_per_lang,
        "expected_rules": expected_rules,
        "results": all_results,
        "pass": all_pass,
    }


def print_scenario(data: dict) -> None:
    """Print a scenario result."""
    scenario = data["scenario"]
    expected = data["expected"]
    passed = data["pass"]
    expected_per_lang = data.get("expected_per_lang", {})

    badge = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{'=' * 70}")
    print(f"  {scenario}")
    print(f"  Expected: {expected}  |  {badge}")
    print(f"{'=' * 70}")

    for r in data["results"]:
        lang = r["language"]
        actual = r["override_decision"] or "approve"
        diff = r["structural_diff"]
        lang_expected = expected_per_lang.get(lang) or "approve"
        match = "✅" if (actual == lang_expected) else "❌"

        print(f"\n  [{lang}] {match} decision={actual} (expected={lang_expected})")
        print(f"    diff: {diff['removed']} removed, {diff['added']} added, {diff['preserved']} preserved")

        if r["security_violations"]:
            for v in r["security_violations"][:3]:
                print(f"    ❌ {v[:80]}")
        if r["security_warnings"]:
            for w in r["security_warnings"][:2]:
                print(f"    ⚠️  {w[:80]}")
        if r.get("rule_mismatch"):
            print(f"    ❌ Rule mismatch: {r['rule_mismatch']}")
        if r["rule_triggers"]:
            for t in r["rule_triggers"][:3]:
                print(f"    📋 [{t['rule']}] {t['case']} → {t['decision']}")


# Shorthand for all-approve
ALL_APPROVE = {
    "python_fastapi": None,
    "java_spring": None,
    "node_express": None,
}


def main():
    print("=" * 70)
    print("  CodeGate Backend Security Gate Demo — Zero-LLM Reproducible")
    print("  Demonstrates: SEC-6 ~ SEC-10 across Python/Java/Express")
    print("=" * 70)

    baseline = load_fixture("baseline")

    scenarios = [
        ("T7: Auth Preserved", "t7_auth_preserved",
         ALL_APPROVE, []),

        ("T8: Auth Removed", "t8_auth_removed",
         {"python_fastapi": "escalate_to_human",
          "java_spring": "escalate_to_human",
          "node_express": "escalate_to_human"},
         ["SEC-6"]),

        ("T9: Tenant Scope Preserved", "t9_tenant_scope_preserved",
         ALL_APPROVE, []),

        ("T10: Tenant Scope Removed", "t10_tenant_scope_removed",
         {"python_fastapi": "escalate_to_human",
          "java_spring": "escalate_to_human",
          "node_express": "escalate_to_human"},
         ["SEC-8"]),

        ("T11: User Role Trusted", "t11_user_role_trusted",
         {"python_fastapi": "revise_code",
          "java_spring": None,   # baseline copy, no change
          "node_express": None}, # baseline copy, no change
         ["SEC-9"]),

        ("T12: Security Config Relaxed", "t12_security_config_relaxed",
         {"python_fastapi": "revise_code",
          "java_spring": None,       # baseline copy, no change
          "node_express": "revise_code"},
         ["SEC-10"]),
    ]

    results = []
    for name, dir_name, expected, rules in scenarios:
        passed, data = run_scenario(name, dir_name, baseline, expected, rules)
        print_scenario(data)
        results.append(data)

    # Summary
    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    print(f"  {'Scenario':35s} {'Expected':20s} {'Result':10s}")
    print(f"  {'-' * 65}")
    for r in results:
        badge = "✅" if r["pass"] else "❌"
        print(f"  {r['scenario']:35s} {r['expected']:20s} {badge}")

    all_pass = all(r["pass"] for r in results)
    print()
    if all_pass:
        print("  ✅ All scenarios passed!")
        return 0
    else:
        failed = [r["scenario"] for r in results if not r["pass"]]
        print(f"  ❌ Failed scenarios: {', '.join(failed)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
