"""Tests for backend security policy gate (SEC-6 ~ SEC-10).

Tests the deterministic security rules that detect:
  SEC-6: Auth boundary removal
  SEC-7: Authorization check weakening (3 tiers)
  SEC-8: Tenant/org scope removal
  SEC-9: User-controlled privilege trust
  SEC-10: Security config relaxation
"""

import pytest
from codegate.policies.security import evaluate_security_policies, SecurityPolicyResult


def _make_pattern(pattern: str, kind: str, file: str = "test.py") -> dict:
    """Create a pattern dict matching the structural_diff format."""
    return {"pattern": pattern, "kind": kind, "file": file, "line_number": 1}


def _make_diff(
    removed=None, added=None, unchanged=None
) -> dict:
    """Create a structural_diff dict."""
    return {
        "removed_from_baseline": removed or [],
        "added_not_in_baseline": added or [],
        "unchanged_baseline": unchanged or [],
    }


# ===========================================================================
# SEC-6: Auth Boundary Removal
# ===========================================================================


class TestSEC6AuthBoundaryRemoval:
    """SEC-6: Auth decorator/middleware/dependency removal."""

    def test_python_depends_removed_escalates(self):
        """Depends(get_current_user) removed → escalate_to_human"""
        diff = _make_diff(removed=[
            _make_pattern("Depends(get_current_user)", "auth_boundary"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "escalate_to_human"
        assert any("SEC-6" in v for v in result.security_violations)
        assert any(t["rule"] == "SEC-6" and t["decision"] == "escalate_to_human"
                    for t in result.rule_triggers)

    def test_java_preauthorize_removed_escalates(self):
        """@PreAuthorize removed → escalate_to_human"""
        diff = _make_diff(removed=[
            _make_pattern('@PreAuthorize("isAuthenticated()")', "auth_boundary"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "escalate_to_human"
        assert any("SEC-6" in v for v in result.security_violations)

    def test_express_middleware_removed_escalates(self):
        """app.use(authMiddleware) removed → escalate_to_human"""
        diff = _make_diff(removed=[
            _make_pattern("app.use(authMiddleware)", "auth_boundary"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "escalate_to_human"

    def test_auth_refactored_warns_only(self):
        """Auth boundary removed + re-added = warning, no violation"""
        diff = _make_diff(
            removed=[_make_pattern("Depends(get_current_user)", "auth_boundary")],
            added=[_make_pattern("Depends(authenticate)", "auth_boundary")],
        )
        result = evaluate_security_policies(diff)
        assert result.override_decision is None  # No violation
        assert len(result.security_warnings) >= 1
        assert any("SEC-6" in w for w in result.security_warnings)

    def test_no_auth_change_passes(self):
        """Auth unchanged → no violation"""
        diff = _make_diff(unchanged=[
            _make_pattern("Depends(get_current_user)", "auth_boundary"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision is None
        assert len(result.security_violations) == 0


# ===========================================================================
# SEC-7: Authorization Check Weakening
# ===========================================================================


class TestSEC7AuthorizationWeakening:
    """SEC-7: Admin/owner/role/permission check deletion or weakening."""

    def test_admin_check_removed_revises(self):
        """SEC-7a: authorization_check removed → revise_code"""
        diff = _make_diff(removed=[
            _make_pattern("Depends(require_admin)", "authorization_check"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "revise_code"
        assert any("SEC-7" in v for v in result.security_violations)
        assert any(t["rule"] == "SEC-7" and t["case"] == "authz_deleted"
                    for t in result.rule_triggers)

    def test_admin_check_changed_warns(self):
        """SEC-7b: authorization_check changed → warning only"""
        diff = _make_diff(
            removed=[_make_pattern("@Secured({\"ROLE_ADMIN\"})", "authorization_check")],
            added=[_make_pattern("@RolesAllowed({\"ADMIN\"})", "authorization_check")],
        )
        result = evaluate_security_policies(diff)
        assert result.override_decision is None  # No violation
        assert any("SEC-7" in w for w in result.security_warnings)

    def test_always_allow_added_escalates(self):
        """SEC-7c: permitAll added → escalate_to_human"""
        diff = _make_diff(added=[
            _make_pattern("@PermitAll", "authorization_check"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "escalate_to_human"
        assert any("SEC-7" in v for v in result.security_violations)
        assert any(t["rule"] == "SEC-7" and t["case"] == "always_allow"
                    for t in result.rule_triggers)

    def test_return_true_escalates(self):
        """SEC-7c: 'return true' pattern → escalate_to_human"""
        diff = _make_diff(added=[
            _make_pattern("return true", "authorization_check"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "escalate_to_human"

    def test_secured_replaced_by_permit_all_escalates(self):
        """SEC-7c: @Secured → @PermitAll should use always-allow tier."""
        diff = _make_diff(
            removed=[
                _make_pattern(
                    '@Secured({"ROLE_ADMIN"})', "authorization_check"
                )
            ],
            added=[_make_pattern("@PermitAll", "authorization_check")],
        )
        result = evaluate_security_policies(diff)
        assert result.override_decision == "escalate_to_human"
        assert any(
            t["rule"] == "SEC-7" and t["case"] == "always_allow"
            for t in result.rule_triggers
        )

    def test_authorization_preserved_passes(self):
        """No change → no violation"""
        diff = _make_diff(unchanged=[
            _make_pattern("@PreAuthorize(\"hasRole('ADMIN')\")", "authorization_check"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision is None


# ===========================================================================
# SEC-8: Tenant Scope Removal
# ===========================================================================


class TestSEC8TenantScopeRemoval:
    """SEC-8: Tenant/org scope filter removal."""

    def test_tenant_filter_removed_escalates(self):
        """tenant_scope removed → escalate_to_human"""
        diff = _make_diff(removed=[
            _make_pattern("findByIdAndTenantId", "tenant_scope"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "escalate_to_human"
        assert any("SEC-8" in v for v in result.security_violations)

    def test_tenant_filter_preserved_passes(self):
        """tenant_scope unchanged → no violation"""
        diff = _make_diff(unchanged=[
            _make_pattern("findByIdAndTenantId", "tenant_scope"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision is None

    def test_tenant_refactored_warns(self):
        """tenant_scope removed + re-added = warning"""
        diff = _make_diff(
            removed=[_make_pattern("findByIdAndTenantId", "tenant_scope")],
            added=[_make_pattern(".filter(tenant_id=", "tenant_scope")],
        )
        result = evaluate_security_policies(diff)
        assert result.override_decision is None
        assert any("SEC-8" in w for w in result.security_warnings)


# ===========================================================================
# SEC-9: User-Controlled Privilege Trust
# ===========================================================================


class TestSEC9UserControlledPrivilege:
    """SEC-9: Trusting role/isAdmin from request body."""

    def test_body_role_trusted_revises(self):
        """user_controlled_privilege added → revise_code"""
        diff = _make_diff(added=[
            _make_pattern("req.body.role", "user_controlled_privilege"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "revise_code"
        assert any("SEC-9" in v for v in result.security_violations)

    def test_multiple_privileges_revises(self):
        """Multiple user_controlled_privilege patterns → still revise_code"""
        diff = _make_diff(added=[
            _make_pattern("req.body.role", "user_controlled_privilege"),
            _make_pattern("req.body.isAdmin", "user_controlled_privilege"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "revise_code"

    def test_no_user_privilege_passes(self):
        """No user_controlled_privilege → no violation"""
        diff = _make_diff(added=[
            _make_pattern("req.body.name", "request_param"),
        ])
        result = evaluate_security_policies(diff)
        # Should not trigger SEC-9
        assert not any("SEC-9" in v for v in result.security_violations)


# ===========================================================================
# SEC-10: Security Config Relaxation
# ===========================================================================


class TestSEC10SecurityConfigRelaxation:
    """SEC-10: CORS, cookie, CSRF, JWT config relaxation."""

    def test_cors_origin_star_revises(self):
        """cors origin: '*' → revise_code"""
        diff = _make_diff(added=[
            _make_pattern("cors({ origin: '*' })", "security_config"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "revise_code"
        assert any("SEC-10" in v for v in result.security_violations)

    def test_cookie_secure_false_revises(self):
        """secure: false → revise_code"""
        diff = _make_diff(added=[
            _make_pattern("cookie({ secure: false })", "security_config"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "revise_code"

    def test_strict_config_preserved_passes(self):
        """Config unchanged → no violation"""
        diff = _make_diff(unchanged=[
            _make_pattern("cors({ origin: 'https://app.example.com' })", "security_config"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision is None

    def test_config_added_stricter_passes(self):
        """New restriction added → not a violation"""
        diff = _make_diff(added=[
            _make_pattern("SESSION_COOKIE_SECURE = True", "security_config"),
        ])
        result = evaluate_security_policies(diff)
        # SEC-10 should not trigger for adding stricter config
        assert not any("SEC-10" in v for v in result.security_violations)

    def test_config_removed_revises(self):
        """Security config removed without replacement → revise_code"""
        diff = _make_diff(removed=[
            _make_pattern("SESSION_COOKIE_SECURE = True", "security_config"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "revise_code"
        assert any("SEC-10" in v for v in result.security_violations)

    def test_session_cookie_relaxed_revises(self):
        """SESSION_COOKIE_SECURE = False → revise_code"""
        diff = _make_diff(added=[
            _make_pattern("SESSION_COOKIE_SECURE = False", "security_config"),
        ])
        result = evaluate_security_policies(diff)
        assert result.override_decision == "revise_code"
