"""Safe refactor regression tests (v0.5.0).

Verifies that CodeGate correctly identifies common security-equivalent 
refactorings (T13-T16) as non-blocking (advisory) rather than violations.

Note: These tests use synthetic structural_diff facts to represent 
extractor-visible changes.
"""

import pytest
from codegate.policies.security import evaluate_security_policies


def _make_pattern(pattern: str, kind: str) -> dict:
    return {"pattern": pattern, "kind": kind, "file": "app.py", "line_number": 10, "context": "context"}


def _make_diff(removed=None, added=None) -> dict:
    return {
        "removed_from_baseline": removed or [],
        "added_not_in_baseline": added or [],
        "unchanged_baseline": [],
    }


def test_t13_auth_boundary_rename_non_blocking():
    """T13: Auth decorator/dependency renamed - non-blocking."""
    diff = _make_diff(
        removed=[_make_pattern("Depends(get_current_user)", "auth_boundary")],
        added=[_make_pattern("Depends(get_authenticated_user)", "auth_boundary")]
    )
    result = evaluate_security_policies(diff)
    
    # Should NOT be revise_code or escalate_to_human
    assert result.override_decision not in ("revise_code", "escalate_to_human")
    
    # Should have a trigger with advisory decision
    triggers = [t for t in result.rule_triggers if t["rule"] == "SEC-6"]
    assert len(triggers) == 1
    assert triggers[0]["decision"] == "advisory"
    assert "refactored" in triggers[0]["case"]


def test_t14_tenant_scope_rename_non_blocking():
    """T14: Tenant scope dependency renamed - non-blocking."""
    diff = _make_diff(
        removed=[_make_pattern("Depends(get_tenant)", "tenant_scope")],
        added=[_make_pattern("Depends(get_org_context)", "tenant_scope")]
    )
    result = evaluate_security_policies(diff)
    
    assert result.override_decision not in ("revise_code", "escalate_to_human")
    
    triggers = [t for t in result.rule_triggers if t["rule"] == "SEC-8"]
    assert len(triggers) == 1
    assert triggers[0]["decision"] == "advisory"
    assert "refactored" in triggers[0]["case"]


def test_t15_admin_check_rename_non_blocking():
    """T15: Admin check dependency renamed - non-blocking."""
    diff = _make_diff(
        removed=[_make_pattern("Depends(require_admin)", "authorization_check")],
        added=[_make_pattern("Depends(require_admin_role)", "authorization_check")]
    )
    result = evaluate_security_policies(diff)
    
    assert result.override_decision not in ("revise_code", "escalate_to_human")
    
    triggers = [t for t in result.rule_triggers if t["rule"] == "SEC-7"]
    assert len(triggers) == 1
    assert triggers[0]["decision"] == "advisory"
    assert "authz_changed" in triggers[0]["case"]


def test_t16_config_to_env_non_blocking():
    """T16: Hardcoded config moved to dynamic/env-based - non-blocking."""
    diff = _make_diff(
        removed=[_make_pattern('CORS_ORIGINS = ["https://app.com"]', "security_config")],
        added=[_make_pattern('ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS")', "security_config")]
    )
    result = evaluate_security_policies(diff)
    
    assert result.override_decision not in ("revise_code", "escalate_to_human")
    
    triggers = [t for t in result.rule_triggers if t["rule"] == "SEC-10"]
    assert len(triggers) == 1
    assert triggers[0]["decision"] == "advisory"
    assert "config_changed" in triggers[0]["case"]
