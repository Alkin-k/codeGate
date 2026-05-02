"""Tests for security policy severity calibration (v0.5.0).

Ensures that rule triggers result in the correct severity and decision levels
based on the specific scenario (deleted vs refactored vs relaxed).
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


def _get_trigger(result, rule: str):
    for t in result.rule_triggers:
        if t.get("rule") == rule:
            return t
    return None


@pytest.mark.parametrize("rule,removed_pats,added_pats,expected_decision,expected_severity", [
    # SEC-6: Auth Boundary
    ("SEC-6", ["Depends(get_user)"], [], "escalate_to_human", "violation"),
    ("SEC-6", ["Depends(get_user)"], ["Depends(auth)"], "advisory", "advisory"),

    # SEC-7: Authorization
    ("SEC-7", ["Depends(require_admin)"], [], "revise_code", "violation"),
    ("SEC-7", ["Depends(require_admin)"], ["Depends(require_role)"], "advisory", "advisory"),
    ("SEC-7", [], ["@PermitAll"], "escalate_to_human", "violation"),

    # SEC-8: Tenant Scope
    ("SEC-8", ["Depends(get_tenant)"], [], "escalate_to_human", "violation"),
    ("SEC-8", ["Depends(get_tenant)"], ["Depends(get_org)"], "advisory", "advisory"),

    # SEC-9: User-controlled Privilege
    ("SEC-9", [], ["data['role']"], "revise_code", "violation"),

    # SEC-10: Security Config
    ("SEC-10", [], ["origin: '*'"], "revise_code", "violation"),
    ("SEC-10", ["origin: 'domain.com'"], [], "revise_code", "violation"),
    ("SEC-10", ["origin: 'domain.com'"], ["origin: 'other.com'"], "advisory", "advisory"),
])
def test_severity_calibration(rule, removed_pats, added_pats, expected_decision, expected_severity):
    removed = [_make_pattern(p, "auth_boundary" if rule == "SEC-6" else 
                             "authorization_check" if rule == "SEC-7" else
                             "tenant_scope" if rule == "SEC-8" else
                             "user_controlled_privilege" if rule == "SEC-9" else
                             "security_config") for p in removed_pats]
    added = [_make_pattern(p, "auth_boundary" if rule == "SEC-6" else 
                             "authorization_check" if rule == "SEC-7" else
                             "tenant_scope" if rule == "SEC-8" else
                             "user_controlled_privilege" if rule == "SEC-9" else
                             "security_config") for p in added_pats]
    
    diff = _make_diff(removed=removed, added=added)
    result = evaluate_security_policies(diff)
    trigger = _get_trigger(result, rule)
    
    assert trigger is not None, f"Expected trigger for {rule}"
    assert trigger["decision"] == expected_decision
    assert trigger["severity"] == expected_severity
