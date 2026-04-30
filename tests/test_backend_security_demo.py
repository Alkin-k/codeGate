"""Snapshot tests for the backend security demo fixture.

Validates that the demo scenarios T7-T12 produce the expected decisions
when run through the security gate pipeline.
"""

import pytest
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

FIXTURE_DIR = PROJECT_ROOT / "benchmarks" / "fixtures" / "backend_security_demo"

LANGUAGES = [
    ("python_fastapi", {".py"}),
    ("java_spring", {".java"}),
    ("node_express", {".ts"}),
]


def load_fixture(fixture_name):
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


def run_gate(baseline_files, changed_files):
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

    return evaluate_security_policies(result.to_dict(), changed_files)


def assert_triggered_rule(result, expected_rule):
    triggered = {
        t.get("rule")
        for t in result.rule_triggers
        if t.get("decision") != "advisory"
    }
    assert expected_rule in triggered, (
        f"expected {expected_rule}, got triggers={result.rule_triggers}, "
        f"violations={result.security_violations}"
    )


@pytest.fixture(scope="module")
def baseline():
    return load_fixture("baseline")


class TestBackendSecurityDemo:
    """Snapshot tests for T7-T12 demo scenarios."""

    def test_t7_auth_preserved_approves(self, baseline):
        """T7: auth unchanged → approve for all languages"""
        changed = load_fixture("t7_auth_preserved")
        for lang, _ in LANGUAGES:
            result = run_gate(baseline[lang], changed[lang])
            assert result.override_decision is None, \
                f"T7 {lang}: expected approve, got {result.override_decision}"

    def test_t8_auth_removed_escalates(self, baseline):
        """T8: auth removed → escalate for all languages"""
        changed = load_fixture("t8_auth_removed")
        for lang, _ in LANGUAGES:
            result = run_gate(baseline[lang], changed[lang])
            assert result.override_decision == "escalate_to_human", \
                f"T8 {lang}: expected escalate_to_human, got {result.override_decision}"
            assert_triggered_rule(result, "SEC-6")

    def test_t9_tenant_preserved_approves(self, baseline):
        """T9: tenant scope unchanged → approve for all languages"""
        changed = load_fixture("t9_tenant_scope_preserved")
        for lang, _ in LANGUAGES:
            result = run_gate(baseline[lang], changed[lang])
            assert result.override_decision is None, \
                f"T9 {lang}: expected approve, got {result.override_decision}"

    def test_t10_tenant_removed_escalates_python(self, baseline):
        """T10: tenant scope removed (Python) → escalate"""
        changed = load_fixture("t10_tenant_scope_removed")
        result = run_gate(baseline["python_fastapi"], changed["python_fastapi"])
        assert result.override_decision == "escalate_to_human"
        assert_triggered_rule(result, "SEC-8")

    def test_t10_tenant_removed_escalates_java(self, baseline):
        """T10: tenant scope removed (Java) → escalate"""
        changed = load_fixture("t10_tenant_scope_removed")
        result = run_gate(baseline["java_spring"], changed["java_spring"])
        assert result.override_decision == "escalate_to_human"
        assert_triggered_rule(result, "SEC-8")

    def test_t10_tenant_removed_escalates_express(self, baseline):
        """T10: tenant scope removed (Express) → escalate"""
        changed = load_fixture("t10_tenant_scope_removed")
        result = run_gate(baseline["node_express"], changed["node_express"])
        assert result.override_decision == "escalate_to_human"
        assert_triggered_rule(result, "SEC-8")

    def test_t11_role_trusted_revises_python(self, baseline):
        """T11: user-controlled privilege (Python) → revise_code"""
        changed = load_fixture("t11_user_role_trusted")
        result = run_gate(baseline["python_fastapi"], changed["python_fastapi"])
        assert result.override_decision == "revise_code"
        assert any("SEC-9" in v for v in result.security_violations)

    def test_t12_config_relaxed_revises_python(self, baseline):
        """T12: security config relaxed (Python) → revise_code"""
        changed = load_fixture("t12_security_config_relaxed")
        result = run_gate(baseline["python_fastapi"], changed["python_fastapi"])
        assert result.override_decision == "revise_code"
        assert any("SEC-10" in v for v in result.security_violations)

    def test_t12_config_relaxed_revises_express(self, baseline):
        """T12: security config relaxed (Express) → revise_code"""
        changed = load_fixture("t12_security_config_relaxed")
        result = run_gate(baseline["node_express"], changed["node_express"])
        assert result.override_decision == "revise_code"
        assert any("SEC-10" in v for v in result.security_violations)
