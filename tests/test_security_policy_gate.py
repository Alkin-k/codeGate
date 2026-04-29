"""Security Policy Gate tests.

Validates that the security policy correctly:
  - T5 pattern passes (scoped guest via meta.guest, token logic preserved)
  - T6 pattern blocks (global guest bypass, unscoped auth weakening)
  - Deletion of getToken blocks
  - Weakened !isPublic && !token conditions block
  - Irrelevant UI changes don't block
  - Proper revise_code vs escalate_to_human decisions
"""

from __future__ import annotations

from codegate.policies.engine import evaluate_policies
from codegate.policies.security import evaluate_security_policies
from codegate.schemas.gate import GateDecision
from codegate.schemas.work_item import WorkItem
from codegate.workflow.state import GovernanceState

# ---------------------------------------------------------------------------
# Test fixtures: structural_diff data mirroring real extractor output
# ---------------------------------------------------------------------------

def _make_pattern(file: str, pattern: str, kind: str, line: int = 0) -> dict:
    return {
        "file": file,
        "pattern": pattern,
        "kind": kind,
        "line_number": line,
        "context": pattern,
    }


def _t5_structural_diff() -> dict:
    """T5: Scoped guest via meta.guest, token logic preserved.

    Baseline → Current changes:
      - Added: route_meta with guest: true on /workspace only
      - Added: guard_condition checking to.meta?.guest
      - Preserved: token check, isPublic check, getToken import
    """
    return {
        "removed_from_baseline": [],
        "added_not_in_baseline": [
            _make_pattern("src/router/index.ts",
                         "meta: { guest: true }",
                         "route_meta", 8),
            _make_pattern("src/router/index.ts",
                         "isPublic || to.meta?.guest",
                         "guard_condition", 22),
        ],
        "unchanged_baseline": [
            _make_pattern("src/router/index.ts",
                         "router.beforeEach(to, from, next)",
                         "router_guard", 18),
            _make_pattern("src/router/index.ts",
                         "getToken()",
                         "auth_condition", 19),
            _make_pattern("src/router/index.ts",
                         "!token",
                         "auth_condition", 25),
            _make_pattern("src/router/index.ts",
                         "isPublic",
                         "auth_condition", 21),
            _make_pattern("src/router/index.ts",
                         "meta: { public: true }",
                         "route_meta", 6),
        ],
    }


def _t6_structural_diff() -> dict:
    """T6: Global guest bypass — !token weakened with !guest.

    Baseline → Current changes:
      - Added: isGuestMode import, guest auth condition, guest storage access
      - Removed: the original !token guard condition (replaced with !token && !guest)
      - No route_meta with guest scoping added
    """
    return {
        "removed_from_baseline": [
            _make_pattern("src/router/index.ts",
                         "!token",
                         "guard_condition", 25),
        ],
        "added_not_in_baseline": [
            _make_pattern("src/router/index.ts",
                         "import { getToken, isGuestMode } from '@/platform/auth-storage'",
                         "import", 2),
            _make_pattern("src/router/index.ts",
                         "isGuestMode()",
                         "auth_condition", 20),
            _make_pattern("src/router/index.ts",
                         "guest",
                         "auth_condition", 23),
            _make_pattern("src/router/index.ts",
                         "!token && !guest",
                         "guard_condition", 25),
            _make_pattern("src/platform/auth-storage.ts",
                         "localStorage.getItem('guest_mode')",
                         "storage_access", 18),
            _make_pattern("src/platform/auth-storage.ts",
                         "localStorage.setItem('guest_mode')",
                         "storage_access", 22),
        ],
        "unchanged_baseline": [
            _make_pattern("src/router/index.ts",
                         "router.beforeEach(to, from, next)",
                         "router_guard", 18),
            _make_pattern("src/router/index.ts",
                         "getToken()",
                         "auth_condition", 19),
            _make_pattern("src/router/index.ts",
                         "isPublic",
                         "auth_condition", 21),
        ],
    }


def _guard_deleted_diff() -> dict:
    """Router guard entirely deleted."""
    return {
        "removed_from_baseline": [
            _make_pattern("src/router/index.ts",
                         "router.beforeEach(to, from, next)",
                         "router_guard", 18),
            _make_pattern("src/router/index.ts",
                         "getToken()",
                         "auth_condition", 19),
            _make_pattern("src/router/index.ts",
                         "!token",
                         "auth_condition", 25),
        ],
        "added_not_in_baseline": [],
        "unchanged_baseline": [],
    }


def _gettoken_deleted_diff() -> dict:
    """getToken() removed from router guard without replacement."""
    return {
        "removed_from_baseline": [
            _make_pattern("src/router/index.ts",
                         "getToken()",
                         "auth_condition", 19),
            _make_pattern("src/router/index.ts",
                         "!token",
                         "auth_condition", 25),
        ],
        "added_not_in_baseline": [],
        "unchanged_baseline": [
            _make_pattern("src/router/index.ts",
                         "router.beforeEach(to, from, next)",
                         "router_guard", 18),
            _make_pattern("src/router/index.ts",
                         "isPublic",
                         "auth_condition", 21),
        ],
    }


def _ui_only_diff() -> dict:
    """Only CSS/template changes, no auth modifications."""
    return {
        "removed_from_baseline": [],
        "added_not_in_baseline": [
            _make_pattern("src/views/login/LoginView.vue",
                         "import { ref } from 'vue'",
                         "import", 1),
        ],
        "unchanged_baseline": [
            _make_pattern("src/router/index.ts",
                         "router.beforeEach(to, from, next)",
                         "router_guard", 18),
            _make_pattern("src/router/index.ts",
                         "getToken()",
                         "auth_condition", 19),
            _make_pattern("src/router/index.ts",
                         "!token",
                         "auth_condition", 25),
        ],
    }


def _protected_route_public_diff() -> dict:
    """Workspace route changed from protected to public."""
    return {
        "removed_from_baseline": [],
        "added_not_in_baseline": [
            _make_pattern(
                "src/router/index.ts",
                "route(path='/workspace', name='workspace', "
                "component=WorkspaceView, title='写作工作台', "
                "meta: { title: '写作工作台', public: true })",
                "route_meta",
                8,
            ),
        ],
        "unchanged_baseline": [
            _make_pattern(
                "src/router/index.ts",
                "router.beforeEach(to, from, next)",
                "router_guard",
                18,
            ),
        ],
    }


def _token_weakened_with_guest_diff() -> dict:
    """!isPublic && !token condition modified to add || isGuestMode bypass."""
    return {
        "removed_from_baseline": [
            _make_pattern("src/router/index.ts",
                         "!isPublic && !token",
                         "guard_condition", 25),
        ],
        "added_not_in_baseline": [
            _make_pattern("src/router/index.ts",
                         "!isPublic && !token && !guest",
                         "guard_condition", 25),
            _make_pattern("src/router/index.ts",
                         "guest",
                         "auth_condition", 20),
        ],
        "unchanged_baseline": [
            _make_pattern("src/router/index.ts",
                         "router.beforeEach(to, from, next)",
                         "router_guard", 18),
        ],
    }


# ---------------------------------------------------------------------------
# Helper to build full GovernanceState with structural_diff
# ---------------------------------------------------------------------------

def _state_with_diff(structural_diff: dict, decision: str = "approve") -> GovernanceState:
    work_item = WorkItem(raw_request="security policy test")
    return GovernanceState(
        work_item=work_item,
        structural_diff=structural_diff,
        gate_decision=GateDecision(
            work_item_id=work_item.id,
            decision=decision,
            drift_score=0,
            coverage_score=100,
        ),
    )


# ---------------------------------------------------------------------------
# Tests: Security Policy direct
# ---------------------------------------------------------------------------


class TestT5PatternPasses:
    """T5: Scoped guest via meta.guest, token logic preserved → approve."""

    def test_t5_no_security_violations(self) -> None:
        result = evaluate_security_policies(_t5_structural_diff())
        assert result.security_violations == [], \
            f"T5 should pass, got violations: {result.security_violations}"

    def test_t5_override_is_none(self) -> None:
        result = evaluate_security_policies(_t5_structural_diff())
        assert result.override_decision is None

    def test_t5_may_have_advisory_warnings(self) -> None:
        """T5 may produce warnings (SEC-3 scoped guest advisory), but no violations."""
        result = evaluate_security_policies(_t5_structural_diff())
        assert result.override_decision is None  # Warnings don't override


class TestT6PatternBlocks:
    """T6: Global guest bypass → revise_code or escalate_to_human."""

    def test_t6_has_security_violations(self) -> None:
        result = evaluate_security_policies(_t6_structural_diff())
        assert len(result.security_violations) > 0, \
            f"T6 should have violations, got: {result.security_violations}"

    def test_t6_override_is_not_none(self) -> None:
        result = evaluate_security_policies(_t6_structural_diff())
        assert result.override_decision in ("revise_code", "escalate_to_human"), \
            f"T6 should revise or escalate, got: {result.override_decision}"

    def test_t6_has_rule_triggers(self) -> None:
        result = evaluate_security_policies(_t6_structural_diff())
        assert len(result.rule_triggers) > 0
        triggered_rules = {t["rule"] for t in result.rule_triggers}
        # Should trigger SEC-2 (guest storage) and/or SEC-3 (unscoped guest)
        assert triggered_rules, f"Expected rule triggers, got: {result.rule_triggers}"

    def test_t6_detects_unscoped_guest(self) -> None:
        """SEC-3 should detect guest bypass without route meta scoping."""
        result = evaluate_security_policies(_t6_structural_diff())
        sec3_triggers = [t for t in result.rule_triggers if t["rule"] == "SEC-3"]
        assert len(sec3_triggers) > 0, \
            f"Expected SEC-3 trigger, got rules: {[t['rule'] for t in result.rule_triggers]}"


class TestDeletedGetTokenBlocks:
    """Deletion of getToken() should trigger security violation."""

    def test_gettoken_deletion_blocks(self) -> None:
        result = evaluate_security_policies(_gettoken_deleted_diff())
        assert len(result.security_violations) > 0, \
            f"Deleting getToken should violate, got: {result.security_violations}"

    def test_gettoken_deletion_triggers_sec4(self) -> None:
        result = evaluate_security_policies(_gettoken_deleted_diff())
        sec4_triggers = [t for t in result.rule_triggers if t["rule"] == "SEC-4"]
        assert len(sec4_triggers) > 0, \
            f"Expected SEC-4 trigger, got: {[t['rule'] for t in result.rule_triggers]}"

    def test_gettoken_deletion_decision(self) -> None:
        result = evaluate_security_policies(_gettoken_deleted_diff())
        assert result.override_decision == "revise_code"


class TestGuardDeletionEscalates:
    """Deleting the entire router guard should escalate."""

    def test_guard_deletion_blocks(self) -> None:
        result = evaluate_security_policies(_guard_deleted_diff())
        assert len(result.security_violations) > 0

    def test_guard_deletion_triggers_sec1(self) -> None:
        result = evaluate_security_policies(_guard_deleted_diff())
        sec1_triggers = [t for t in result.rule_triggers if t["rule"] == "SEC-1"]
        assert len(sec1_triggers) > 0

    def test_guard_deletion_escalates(self) -> None:
        result = evaluate_security_policies(_guard_deleted_diff())
        assert result.override_decision == "escalate_to_human"


class TestWeakenedAuthConditionBlocks:
    """!isPublic && !token modified to add || isGuestMode → violation."""

    def test_weakened_condition_blocks(self) -> None:
        result = evaluate_security_policies(_token_weakened_with_guest_diff())
        assert len(result.security_violations) > 0, \
            f"Weakened auth condition should block, got: {result.security_violations}"


class TestUIOnlyChangesPass:
    """Adding CSS/template changes without auth modifications → no security violation."""

    def test_ui_only_no_violations(self) -> None:
        result = evaluate_security_policies(_ui_only_diff())
        assert result.security_violations == [], \
            f"UI-only changes should pass, got: {result.security_violations}"

    def test_ui_only_no_override(self) -> None:
        result = evaluate_security_policies(_ui_only_diff())
        assert result.override_decision is None


class TestNoDiffNoViolation:
    """No structural_diff → no security evaluation."""

    def test_none_diff_passes(self) -> None:
        result = evaluate_security_policies(None)
        assert result.security_violations == []
        assert result.override_decision is None

    def test_empty_diff_passes(self) -> None:
        result = evaluate_security_policies({
            "removed_from_baseline": [],
            "added_not_in_baseline": [],
            "unchanged_baseline": [],
        })
        assert result.security_violations == []


# ---------------------------------------------------------------------------
# Tests: Policy Engine integration (Rule 11)
# ---------------------------------------------------------------------------


class TestPolicyEngineIntegration:
    """Test that Security Policy results are integrated into the main policy engine."""

    def test_t5_approved_through_policy_engine(self) -> None:
        """T5 should pass through the full policy engine."""
        state = _state_with_diff(_t5_structural_diff())
        result = evaluate_policies(state)
        # T5 has no violations from any rule
        security_violations = [v for v in result.violations if "[SECURITY]" in v]
        assert len(security_violations) == 0

    def test_t6_blocked_by_policy_engine(self) -> None:
        """T6 should be blocked by Rule 11 in the policy engine."""
        state = _state_with_diff(_t6_structural_diff())
        result = evaluate_policies(state)
        security_violations = [v for v in result.violations if "[SECURITY]" in v]
        assert len(security_violations) > 0, \
            f"T6 should have [SECURITY] violations, got: {result.violations}"
        assert result.override_decision in ("revise_code", "escalate_to_human")

    def test_guard_deletion_escalated_by_policy_engine(self) -> None:
        """Guard deletion should escalate via Rule 11."""
        state = _state_with_diff(_guard_deleted_diff())
        result = evaluate_policies(state)
        assert result.override_decision == "escalate_to_human"

    def test_ui_only_passes_policy_engine(self) -> None:
        """UI-only changes should have no policy violations."""
        state = _state_with_diff(_ui_only_diff())
        result = evaluate_policies(state)
        security_violations = [v for v in result.violations if "[SECURITY]" in v]
        assert len(security_violations) == 0


# ---------------------------------------------------------------------------
# Tests: Decision tiering (revise vs escalate)
# ---------------------------------------------------------------------------


class TestDecisionTiering:
    """Test that security violations produce correct revise/escalate decisions."""

    def test_sec1_guard_removed_escalates(self) -> None:
        result = evaluate_security_policies(_guard_deleted_diff())
        assert result.override_decision == "escalate_to_human"

    def test_sec4_token_deleted_revises(self) -> None:
        result = evaluate_security_policies(_gettoken_deleted_diff())
        assert result.override_decision == "revise_code"

    def test_sec3_global_bypass_escalates(self) -> None:
        """Global guest bypass without any route meta scoping should escalate."""
        result = evaluate_security_policies(_t6_structural_diff())
        sec3_triggers = [t for t in result.rule_triggers if t["rule"] == "SEC-3"]
        if sec3_triggers:
            # SEC-3 with global_guest_bypass case should escalate
            decisions = [t.get("decision", "") for t in sec3_triggers]
            assert "escalate_to_human" in decisions, \
                f"Global bypass SEC-3 should escalate, got: {decisions}"

    def test_sec5_protected_route_public_revises(self) -> None:
        """Protected route exposed via public:true should be blocked."""
        result = evaluate_security_policies(_protected_route_public_diff())
        sec5 = [t for t in result.rule_triggers if t["rule"] == "SEC-5"]
        assert sec5, f"Expected SEC-5 trigger, got: {result.rule_triggers}"
        assert sec5[0]["case"] == "protected_route_public"
        assert result.override_decision == "revise_code"


# ---------------------------------------------------------------------------
# Tests: SEC-4 sub-cases (deleted vs weakened vs refactored)
# ---------------------------------------------------------------------------


def _token_weakened_guard_diff() -> dict:
    """Token check weakened: !token → !token && !guest (guard_condition level)."""
    return {
        "removed_from_baseline": [
            _make_pattern("src/router/index.ts",
                         "!token",
                         "guard_condition", 25),
        ],
        "added_not_in_baseline": [
            _make_pattern("src/router/index.ts",
                         "!token && !guest",
                         "guard_condition", 25),
        ],
        "unchanged_baseline": [
            _make_pattern("src/router/index.ts",
                         "router.beforeEach(to, from, next)",
                         "router_guard", 18),
        ],
    }


def _token_refactored_diff() -> dict:
    """Token check refactored: !token → !getAuthToken() (no guest bypass)."""
    return {
        "removed_from_baseline": [
            _make_pattern("src/router/index.ts",
                         "!token",
                         "auth_condition", 25),
        ],
        "added_not_in_baseline": [
            _make_pattern("src/router/index.ts",
                         "!getAuthToken()",
                         "auth_condition", 25),
        ],
        "unchanged_baseline": [
            _make_pattern("src/router/index.ts",
                         "router.beforeEach(to, from, next)",
                         "router_guard", 18),
        ],
    }


class TestSEC4SubCases:
    """Test SEC-4 correctly distinguishes deleted, weakened, and refactored."""

    def test_token_deleted_case(self) -> None:
        """Token fully deleted → violation with 'token_deleted' case."""
        result = evaluate_security_policies(_gettoken_deleted_diff())
        sec4 = [t for t in result.rule_triggers if t["rule"] == "SEC-4"]
        assert len(sec4) > 0
        assert sec4[0]["case"] == "token_deleted"
        assert result.override_decision == "revise_code"

    def test_token_weakened_case(self) -> None:
        """Token weakened with guest → violation with 'token_weakened' case."""
        result = evaluate_security_policies(_token_weakened_guard_diff())
        sec4 = [t for t in result.rule_triggers if t["rule"] == "SEC-4"]
        assert len(sec4) > 0
        assert sec4[0]["case"] == "token_weakened", \
            f"Expected 'token_weakened', got: {sec4[0]['case']}"
        # Should still produce a violation
        assert any("weakened" in v.lower() for v in result.security_violations), \
            f"Expected 'weakened' in violation text: {result.security_violations}"

    def test_token_refactored_case(self) -> None:
        """Token refactored without guest → warning only, no violation."""
        result = evaluate_security_policies(_token_refactored_diff())
        sec4 = [t for t in result.rule_triggers if t["rule"] == "SEC-4"]
        assert len(sec4) > 0
        assert sec4[0]["case"] == "token_refactored"
        # Should be advisory, not a violation
        assert sec4[0]["decision"] == "advisory"
        # No override for refactoring
        assert result.override_decision is None
