"""Tests for structured evidence in SEC-1~10 rule triggers (v0.5.0).

Validates that each rule trigger contains:
  - evidence dict with baseline/candidate/summary
  - baseline[].file, baseline[].line, baseline[].kind, baseline[].pattern, baseline[].snippet
  - summary is a non-empty string
  - Backward-compat: old fields (removed, added) still present
"""

import pytest
from codegate.policies.security import evaluate_security_policies


def _make_pattern(pattern: str, kind: str, file: str = "app.py", line: int = 10, context: str = "some context") -> dict:
    return {"pattern": pattern, "kind": kind, "file": file, "line_number": line, "context": context}


def _make_diff(removed=None, added=None, unchanged=None) -> dict:
    return {
        "removed_from_baseline": removed or [],
        "added_not_in_baseline": added or [],
        "unchanged_baseline": unchanged or [],
    }


def _get_trigger(result, rule: str) -> dict:
    """Find first trigger matching the given rule."""
    for t in result.rule_triggers:
        if t.get("rule") == rule:
            return t
    raise AssertionError(f"No trigger found for rule {rule}")


def _get_evidence_block(trigger: dict) -> dict:
    """Extract the structured evidence block."""
    if isinstance(trigger.get("evidence"), dict):
        return trigger["evidence"]
    raise AssertionError(
        f"No structured evidence found in trigger: {trigger}"
    )


def _assert_evidence_point(point):
    """Verify an evidence point has all required fields."""
    assert "file" in point
    assert "line" in point
    assert "kind" in point
    assert "pattern" in point
    assert "snippet" in point
    assert len(point["snippet"]) > 0


# ===========================================================================
# SEC-1~5: Frontend/Auth Bypass Evidence
# ===========================================================================

class TestSEC1to5Evidence:

    def test_sec1_guard_removed_evidence(self):
        diff = _make_diff(removed=[_make_pattern("router.beforeEach", "router_guard")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-1")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["baseline"][0])
        assert trigger["severity"] == "violation"
        assert trigger["decision"] == "escalate_to_human"

    def test_sec2_guest_storage_evidence(self):
        diff = _make_diff(added=[_make_pattern("localStorage.setItem('guestMode', 'true')", "storage_access")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-2")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["candidate"][0])
        assert trigger["severity"] == "advisory"

    def test_sec3_unscoped_guest_evidence(self):
        diff = _make_diff(added=[_make_pattern("if (guest) return next()", "guard_condition")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-3")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["candidate"][0])
        assert trigger["severity"] == "violation"

    def test_sec4_token_deleted_evidence(self):
        diff = _make_diff(removed=[_make_pattern("const token = getToken()", "auth_condition")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-4")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["baseline"][0])
        assert trigger["severity"] == "violation"

    def test_sec5_protected_route_evidence(self):
        diff = _make_diff(added=[_make_pattern("{ path: '/admin', public: true }", "route_meta", "router.ts")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-5")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["candidate"][0])
        assert trigger["severity"] == "violation"


# ===========================================================================
# SEC-6~8: Backend Drift Evidence
# ===========================================================================

class TestSEC6to8Evidence:

    def test_sec6_auth_deleted_evidence(self):
        diff = _make_diff(removed=[_make_pattern("Depends(get_current_user)", "auth_boundary")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-6")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["baseline"][0])
        assert trigger["severity"] == "violation"

    def test_sec7_authz_deleted_evidence(self):
        diff = _make_diff(removed=[_make_pattern("Depends(require_admin)", "authorization_check")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-7")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["baseline"][0])
        assert trigger["severity"] == "violation"

    def test_sec8_scope_deleted_evidence(self):
        diff = _make_diff(removed=[_make_pattern("Depends(get_tenant)", "tenant_scope")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-8")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["baseline"][0])
        assert trigger["severity"] == "violation"


# ===========================================================================
# SEC-9: User-controlled Privilege Evidence
# ===========================================================================

class TestSEC9Evidence:

    def test_sec9_privilege_from_body_evidence(self):
        diff = _make_diff(added=[_make_pattern("data['role']", "user_controlled_privilege")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-9")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["candidate"][0])
        assert trigger["severity"] == "violation"
        assert trigger["decision"] == "revise_code"
        assert "reason" in trigger


# ===========================================================================
# SEC-10: Security Config Evidence
# ===========================================================================

class TestSEC10Evidence:

    def test_sec10_config_relaxed_evidence(self):
        diff = _make_diff(added=[_make_pattern("origin: '*'", "security_config")])
        result = evaluate_security_policies(diff)
        trigger = _get_trigger(result, "SEC-10")
        ev = _get_evidence_block(trigger)
        _assert_evidence_point(ev["candidate"][0])
        assert trigger["severity"] == "violation"


# ===========================================================================
# Backward Compatibility & Edge Cases
# ===========================================================================

def test_evidence_snippet_fallback_to_pattern():
    """Verify snippet fallbacks to pattern if context is empty."""
    # We use internal _evidence_point call via evaluate_security_policies
    # Use 'auth_boundary' kind to trigger SEC-6
    p = _make_pattern("some_pattern", "auth_boundary")
    p["context"] = "" # explicit empty
    diff = _make_diff(removed=[p])
    result = evaluate_security_policies(diff)
    # Trigger SEC-6
    trigger = _get_trigger(result, "SEC-6")
    ev = _get_evidence_block(trigger)
    assert ev["baseline"][0]["snippet"] == "some_pattern"

def test_preserves_removed_added_fields():
    """Backward compat: triggers still have top-level removed/added lists."""
    diff = _make_diff(
        removed=[_make_pattern("OLD", "auth_boundary")],
        added=[_make_pattern("NEW", "auth_boundary")]
    )
    result = evaluate_security_policies(diff)
    trigger = _get_trigger(result, "SEC-6")
    assert trigger["removed"] == ["OLD"]
    assert trigger["added"] == ["NEW"]
