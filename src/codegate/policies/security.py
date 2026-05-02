"""Security Policy Gate — auth/routing/API risk detection.

Consumes structural_diff facts (produced by language-aware extractors)
to detect auth bypass, token logic deletion, tenant scope removal,
and privilege escalation.

Design principles:
  - INPUT: structured facts from extractors (not raw code scanning)
  - OUTPUT: SecurityPolicyResult merged into PolicyResult
  - BOUNDARY: this module makes governance JUDGMENTS from extractor FACTS

Rule inventory:
  SEC-1: Auth guard bypass — global guard modified to bypass token check
  SEC-2: Global guest flag — new guest/guestMode storage key without scope
  SEC-3: Unscoped guest access — guest condition in global guard without
         route-meta scoping (semantic detection, not route count threshold)
  SEC-4: Token logic deletion/weakening — getToken/!isPublic/!token removed
         or weakened by adding guest bypass conditions
  SEC-5: Protected route exposed — auth-gated pages get guest fallback
  SEC-6: Auth boundary removal — auth decorator/middleware/dependency deleted
  SEC-7: Admin/owner check weakening — authorization_check deleted or weakened
  SEC-8: Tenant/org scope removal — tenant_id/org_id scope filter deleted
  SEC-9: User-controlled privilege trust — role/isAdmin from request body
  SEC-10: Security config relaxation — CORS/cookie/CSRF/JWT verify relaxed
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Sensitive route path fragments that require authentication.
# If a guest fallback is added to routes matching these, SEC-5 triggers.
_PROTECTED_ROUTE_KEYWORDS = {
    "membership", "workspace", "admin", "dashboard", "settings",
    "profile", "billing", "payment", "account", "manage",
    "工作台", "会员", "设置", "账户", "账号", "管理", "支付", "账单",
}

# Auth-condition patterns that indicate token/auth checking
_TOKEN_AUTH_PATTERNS = {
    "token", "gettoken", "!token", "isAuthenticated",
    "isLoggedIn", "!isPublic",
}

# Guest-related patterns that weaken auth
_GUEST_BYPASS_PATTERNS = {
    "guest", "guestmode", "isguestmode", "!guest",
}


@dataclass
class SecurityPolicyResult:
    """Result of security-specific policy evaluation."""

    security_violations: List[str] = field(default_factory=list)
    security_warnings: List[str] = field(default_factory=list)
    override_decision: Optional[str] = None  # "revise_code" | "escalate_to_human"
    rule_triggers: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_security_policies(
    structural_diff: Optional[Dict],
    files_content: Optional[Dict[str, str]] = None,
) -> SecurityPolicyResult:
    """Run security-specific policy rules against structural diff output.

    Consumes the structured facts from compute_baseline_diff() — specifically
    the PatternMatch objects with kinds like "router_guard", "auth_condition",
    "guard_condition", "storage_access", "route_meta".

    Args:
        structural_diff: Serialized BaselineDiffResult dict with keys
            "removed_from_baseline", "added_not_in_baseline", "unchanged_baseline".
        files_content: Optional current file contents for deeper analysis.

    Returns:
        SecurityPolicyResult with violations, warnings, and override decision.
    """
    result = SecurityPolicyResult()

    if not structural_diff:
        return result

    removed = structural_diff.get("removed_from_baseline", [])
    added = structural_diff.get("added_not_in_baseline", [])
    unchanged = structural_diff.get("unchanged_baseline", [])

    # Build lookup indexes by kind
    removed_by_kind = _group_by_kind(removed)
    added_by_kind = _group_by_kind(added)
    unchanged_by_kind = _group_by_kind(unchanged)

    # --- SEC-1: Auth guard bypass ---
    _check_sec1_auth_guard_bypass(
        result, removed_by_kind, added_by_kind, unchanged_by_kind, files_content,
    )

    # --- SEC-2: Global guest flag ---
    _check_sec2_global_guest_flag(
        result, added_by_kind,
    )

    # --- SEC-3: Unscoped guest access ---
    _check_sec3_unscoped_guest_access(
        result, added_by_kind, unchanged_by_kind, files_content,
    )

    # --- SEC-4: Token logic deletion ---
    _check_sec4_token_logic_deletion(
        result, removed_by_kind, added_by_kind, files_content,
    )

    # --- SEC-5: Protected route exposed ---
    _check_sec5_protected_route_exposed(
        result, added_by_kind,
    )

    # --- SEC-6: Auth boundary removal (v0.4) ---
    _check_sec6_auth_boundary_removal(
        result, removed_by_kind, added_by_kind,
    )

    # --- SEC-8: Tenant scope removal (v0.4) ---
    _check_sec8_tenant_scope_removal(
        result, removed_by_kind, added_by_kind,
    )

    # --- SEC-7: Authorization check weakening (v0.4) ---
    _check_sec7_authorization_weakening(
        result, removed_by_kind, added_by_kind,
    )

    # --- SEC-9: User-controlled privilege trust (v0.4) ---
    _check_sec9_user_controlled_privilege(
        result, added_by_kind,
    )

    # --- SEC-10: Security config relaxation (v0.4) ---
    _check_sec10_security_config_relaxation(
        result, removed_by_kind, added_by_kind,
    )

    # Determine final override decision (highest severity wins)
    if result.security_violations:
        # Check if any rule triggered escalation
        escalate_rules = {
            t["rule"]
            for t in result.rule_triggers
            if t.get("decision") == "escalate_to_human"
        }
        if escalate_rules:
            result.override_decision = "escalate_to_human"
        else:
            result.override_decision = "revise_code"

    if result.security_violations:
        logger.warning(
            f"Security policy violations: {result.security_violations}, "
            f"override: {result.override_decision}"
        )

    return result


# ---------------------------------------------------------------------------
# Individual rule checkers
# ---------------------------------------------------------------------------


def _check_sec1_auth_guard_bypass(
    result: SecurityPolicyResult,
    removed_by_kind: Dict[str, List[Dict]],
    added_by_kind: Dict[str, List[Dict]],
    unchanged_by_kind: Dict[str, List[Dict]],
    files_content: Optional[Dict[str, str]],
) -> None:
    """SEC-1: Auth guard bypass.

    Triggers when:
      - router_guard is in removed (guard was deleted)
      - OR auth_condition with token/!isPublic is removed AND
        a guest-related condition is added in its place
      - OR guard_condition shows token check weakened with guest bypass
    """
    # Case A: Router guard itself removed
    removed_guards = removed_by_kind.get("router_guard", [])
    if removed_guards:
        result.security_violations.append(
            "SEC-1: router.beforeEach guard was removed — "
            "authentication enforcement may be completely disabled"
        )
        result.rule_triggers.append({
            "rule": "SEC-1",
            "case": "guard_removed",
            "removed": [p.get("pattern", "") for p in removed_guards],
            "severity": "violation",
            "decision": "escalate_to_human",
            "reason": "router.beforeEach guard was removed; authentication enforcement may be completely disabled.",
            "evidence": _build_evidence(
                baseline=removed_guards,
                summary=_evidence_summary_oneliner(removed_guards),
            ),
        })
        return

    # Case B: Auth condition weakened — token check removed + guest bypass added
    removed_auth = removed_by_kind.get("auth_condition", [])
    added_auth = added_by_kind.get("auth_condition", [])
    removed_guard_conds = removed_by_kind.get("guard_condition", [])
    added_guard_conds = added_by_kind.get("guard_condition", [])

    removed_token_checks = [
        p for p in removed_auth
        if _is_token_auth_pattern(p.get("pattern", ""))
    ]
    added_guest_conditions = [
        p for p in added_auth
        if _is_guest_pattern(p.get("pattern", ""))
    ]

    # Also check guard_condition kind for weakened conditions
    removed_guard_token = [
        p for p in removed_guard_conds
        if _is_token_auth_pattern(p.get("pattern", ""))
    ]
    added_guard_guest = [
        p for p in added_guard_conds
        if _is_guest_pattern(p.get("pattern", ""))
    ]

    if removed_token_checks and added_guest_conditions:
        result.security_violations.append(
            f"SEC-1: Token auth condition removed ({_patterns_summary(removed_token_checks)}) "
            f"and replaced with guest bypass ({_patterns_summary(added_guest_conditions)}) — "
            f"authentication may be circumvented"
        )
        result.rule_triggers.append({
            "rule": "SEC-1",
            "case": "token_replaced_by_guest",
            "removed": [p.get("pattern", "") for p in removed_token_checks],
            "added": [p.get("pattern", "") for p in added_guest_conditions],
            "severity": "violation",
            "decision": "escalate_to_human",
            "reason": "Token auth condition removed and replaced with guest bypass; authentication may be circumvented.",
            "evidence": _build_evidence(
                baseline=removed_token_checks,
                candidate=added_guest_conditions,
                summary=_evidence_summary_oneliner(removed_token_checks, added_guest_conditions),
            ),
        })

    unscoped_added_guard_guest = [
        p for p in added_guard_guest
        if not _is_scoped_guest_guard_condition(p, added_by_kind, files_content)
    ]

    if removed_guard_token and unscoped_added_guard_guest:
        result.security_violations.append(
            f"SEC-1: Guard condition weakened — token check "
            f"({_patterns_summary(removed_guard_token)}) replaced with "
            f"guest bypass ({_patterns_summary(unscoped_added_guard_guest)})"
        )
        result.rule_triggers.append({
            "rule": "SEC-1",
            "case": "guard_condition_weakened",
            "removed": [p.get("pattern", "") for p in removed_guard_token],
            "added": [p.get("pattern", "") for p in unscoped_added_guard_guest],
            "severity": "violation",
            "decision": "escalate_to_human",
            "reason": "Guard condition weakened; token check replaced with unscoped guest bypass.",
            "evidence": _build_evidence(
                baseline=removed_guard_token,
                candidate=unscoped_added_guard_guest,
                summary=_evidence_summary_oneliner(removed_guard_token, unscoped_added_guard_guest),
            ),
        })


def _check_sec2_global_guest_flag(
    result: SecurityPolicyResult,
    added_by_kind: Dict[str, List[Dict]],
) -> None:
    """SEC-2: Global guest flag.

    Triggers when localStorage/sessionStorage operations are added
    with guest-related keys (guest, guestMode, guest_token, etc.).
    """
    added_storage = added_by_kind.get("storage_access", [])
    guest_storage = [
        p for p in added_storage
        if _is_guest_storage_key(p.get("pattern", ""))
    ]

    if guest_storage:
        result.security_warnings.append(
            f"SEC-2: New guest-related storage key(s) added: "
            f"{_patterns_summary(guest_storage)} — "
            f"verify that guest state does not bypass authentication"
        )
        result.rule_triggers.append({
            "rule": "SEC-2",
            "case": "guest_storage_added",
            "added": [p.get("pattern", "") for p in guest_storage],
            "severity": "advisory",
            "decision": "advisory",
            "reason": "New guest-related storage key(s) added; verify that guest state does not bypass authentication.",
            "evidence": _build_evidence(
                candidate=guest_storage,
                summary=_evidence_summary_oneliner(None, guest_storage),
            ),
        })


def _check_sec3_unscoped_guest_access(
    result: SecurityPolicyResult,
    added_by_kind: Dict[str, List[Dict]],
    unchanged_by_kind: Dict[str, List[Dict]],
    files_content: Optional[Dict[str, str]],
) -> None:
    """SEC-3: Unscoped guest access.

    Primary detection: guest/auth-bypass condition appears in global
    beforeEach guard AND bypass is NOT scoped to explicit route meta
    or allowlist.

    This is the SEMANTIC detection — not a route count threshold.

    Triggers when:
      - guard_condition with guest bypass is added
      - AND no corresponding route_meta with guest scoping is added
      - OR guard_condition shows a top-level guest early-return
        (e.g., `if (guest) return next()` without route check)
    """
    added_guard_conds = added_by_kind.get("guard_condition", [])
    added_auth = added_by_kind.get("auth_condition", [])
    added_route_meta = added_by_kind.get("route_meta", [])

    # Find guest-related guard conditions
    guest_guard_conds = [
        p for p in added_guard_conds
        if _is_guest_pattern(p.get("pattern", ""))
    ]

    # Also check auth_conditions for guest patterns in router files
    guest_auth_in_router = [
        p for p in added_auth
        if _is_guest_pattern(p.get("pattern", ""))
        and _is_router_file(p.get("file", ""))
    ]

    all_guest_in_guard = guest_guard_conds + guest_auth_in_router

    if not all_guest_in_guard:
        return

    # Check if guest access is scoped via route meta
    has_guest_meta_scoping = any(
        "guest" in p.get("pattern", "").lower()
        for p in added_route_meta
    )

    # Check if the guard condition itself references to.meta
    has_meta_check_in_condition = any(
        "to.meta" in p.get("pattern", "").lower()
        or "meta.guest" in p.get("pattern", "").lower()
        or "meta?.guest" in p.get("pattern", "").lower()
        for p in all_guest_in_guard
    )

    # Secondary check: the guard condition may use a variable derived from
    # to.meta?.guest (e.g., `const isGuest = Boolean(to.meta?.guest)`).
    # In this case the condition `isGuest && !token` IS scoped, even though
    # `to.meta` doesn't appear literally in the condition expression.
    if not has_meta_check_in_condition and has_guest_meta_scoping and files_content:
        # Look for `to.meta?.guest` or `to.meta.guest` in router files
        for fpath, content in (files_content or {}).items():
            if not _is_router_file(fpath):
                continue
            lower_content = content.lower()
            if ("to.meta?.guest" in lower_content
                    or "to.meta.guest" in lower_content):
                has_meta_check_in_condition = True
                break

    if has_meta_check_in_condition:
        # Guest is scoped to route meta — this is the T5 pattern
        result.security_warnings.append(
            "SEC-3: Guest access condition added with route meta scoping — "
            "verify that only intended routes are accessible"
        )
        result.rule_triggers.append({
            "rule": "SEC-3",
            "case": "scoped_guest_access",
            "added": [p.get("pattern", "") for p in all_guest_in_guard],
            "severity": "advisory",
            "decision": "advisory",
            "reason": "Guest access condition added with route meta scoping; verify that only intended routes are accessible.",
            "evidence": _build_evidence(
                candidate=all_guest_in_guard,
                summary=_evidence_summary_oneliner(None, all_guest_in_guard),
            ),
        })
        return

    # Guest condition exists but no meta scoping — unscoped bypass
    # Severity depends on whether ANY meta scoping was added elsewhere
    if has_guest_meta_scoping:
        # Some meta scoping exists but the guard condition itself doesn't check it
        result.security_violations.append(
            f"SEC-3: Guest bypass condition in global guard "
            f"({_patterns_summary(all_guest_in_guard)}) does not reference "
            f"route meta — guard may bypass authentication for all routes"
        )
        result.rule_triggers.append({
            "rule": "SEC-3",
            "case": "unscoped_despite_meta",
            "added": [p.get("pattern", "") for p in all_guest_in_guard],
            "severity": "violation",
            "decision": "revise_code",
            "reason": "Guest bypass condition in global guard does not reference route meta; guard may bypass authentication for all routes.",
            "evidence": _build_evidence(
                candidate=all_guest_in_guard,
                summary=_evidence_summary_oneliner(None, all_guest_in_guard),
            ),
        })
    else:
        # No meta scoping at all — this is the T6 pattern (global bypass)
        result.security_violations.append(
            f"SEC-3: Guest bypass in global guard "
            f"({_patterns_summary(all_guest_in_guard)}) with no route meta scoping — "
            f"this creates a global authentication bypass"
        )
        result.rule_triggers.append({
            "rule": "SEC-3",
            "case": "global_guest_bypass",
            "added": [p.get("pattern", "") for p in all_guest_in_guard],
            "severity": "violation",
            "decision": "escalate_to_human",
            "reason": "Guest bypass in global guard with no route meta scoping; this creates a global authentication bypass.",
            "evidence": _build_evidence(
                candidate=all_guest_in_guard,
                summary=_evidence_summary_oneliner(None, all_guest_in_guard),
            ),
        })


def _check_sec4_token_logic_deletion(
    result: SecurityPolicyResult,
    removed_by_kind: Dict[str, List[Dict]],
    added_by_kind: Dict[str, List[Dict]],
    files_content: Optional[Dict[str, str]],
) -> None:
    """SEC-4: Token logic deletion or weakening.

    Two sub-cases:
      - token_deleted: token/auth check removed with no replacement at all
      - token_weakened: token check still present but additional guest/OR
        condition weakens its enforcement (e.g., `!token` → `!token && !guest`)

    Both are violations; the distinction affects messaging accuracy.
    """
    removed_auth = removed_by_kind.get("auth_condition", [])
    added_auth = added_by_kind.get("auth_condition", [])
    removed_guard_conds = removed_by_kind.get("guard_condition", [])
    added_guard_conds = added_by_kind.get("guard_condition", [])

    # Token-related patterns that were removed
    deleted_token_logic = [
        p for p in removed_auth
        if _is_token_auth_pattern(p.get("pattern", ""))
    ]
    deleted_guard_token = [
        p for p in removed_guard_conds
        if _is_token_auth_pattern(p.get("pattern", ""))
    ]
    all_deleted = deleted_token_logic + deleted_guard_token

    if not all_deleted:
        return

    # Check if token logic was re-added in auth_conditions
    re_added_auth_token = [
        p for p in added_auth
        if _is_token_auth_pattern(p.get("pattern", ""))
    ]

    # Check if token logic reappears in new guard_conditions
    # (e.g., `!token` removed → `!token && !guest` added)
    re_added_guard_token = [
        p for p in added_guard_conds
        if _is_token_auth_pattern(p.get("pattern", ""))
    ]

    all_re_added = re_added_auth_token + re_added_guard_token

    if all_re_added:
        # Token logic still exists in some form — check if it was weakened
        weakened_with_guest = [
            p for p in all_re_added
            if _is_guest_pattern(p.get("pattern", ""))
            and not _is_scoped_guest_guard_condition(
                p, added_by_kind, files_content
            )
        ]

        if weakened_with_guest:
            # Token check weakened by adding guest bypass condition
            result.security_violations.append(
                f"SEC-4: Token/auth condition weakened — "
                f"original ({_patterns_summary(all_deleted)}) now includes "
                f"guest bypass ({_patterns_summary(weakened_with_guest)})"
            )
            result.rule_triggers.append({
                "rule": "SEC-4",
                "case": "token_weakened",
                "removed": [p.get("pattern", "") for p in all_deleted],
                "added": [p.get("pattern", "") for p in weakened_with_guest],
                "severity": "violation",
                "decision": "revise_code",
                "reason": "Token/auth condition weakened; original check now includes unscoped guest bypass.",
                "evidence": _build_evidence(
                    baseline=all_deleted,
                    candidate=weakened_with_guest,
                    summary=_evidence_summary_oneliner(all_deleted, weakened_with_guest),
                ),
            })
        else:
            # Token logic was refactored without adding guest bypass
            result.security_warnings.append(
                "SEC-4: Token logic was modified (removed and re-added) — "
                "verify the new implementation is equivalent"
            )
            result.rule_triggers.append({
                "rule": "SEC-4",
                "case": "token_refactored",
                "removed": [p.get("pattern", "") for p in all_deleted],
                "added": [p.get("pattern", "") for p in all_re_added],
                "severity": "advisory",
                "decision": "advisory",
                "reason": "Token logic was modified (removed and re-added); verify the new implementation is equivalent.",
                "evidence": _build_evidence(
                    baseline=all_deleted,
                    candidate=all_re_added,
                    summary=_evidence_summary_oneliner(all_deleted, all_re_added),
                ),
            })
    else:
        # Token logic deleted without any replacement
        result.security_violations.append(
            f"SEC-4: Token/auth check deleted ({_patterns_summary(all_deleted)}) "
            f"without replacement — authentication may be disabled"
        )
        result.rule_triggers.append({
            "rule": "SEC-4",
            "case": "token_deleted",
            "removed": [p.get("pattern", "") for p in all_deleted],
            "severity": "violation",
            "decision": "revise_code",
            "reason": "Token/auth check deleted without replacement; authentication may be disabled.",
            "evidence": _build_evidence(
                baseline=all_deleted,
                summary=_evidence_summary_oneliner(all_deleted),
            ),
        })


def _check_sec5_protected_route_exposed(
    result: SecurityPolicyResult,
    added_by_kind: Dict[str, List[Dict]],
) -> None:
    """SEC-5: Protected route exposed.

    Triggers when protected routes gain unauthenticated exposure through
    `public: true`. Route-scoped `guest: true` is handled by SEC-3 because it
    can be valid when the guard checks `to.meta?.guest && !token`.
    """
    added_meta = added_by_kind.get("route_meta", [])

    for p in added_meta:
        pattern = p.get("pattern", "").lower()
        evidence = " ".join(
            str(p.get(key, ""))
            for key in ("pattern", "context", "file")
        ).lower()
        file_path = p.get("file", "").lower()

        exposes_public = _has_public_true(pattern)
        if not exposes_public:
            continue

        for keyword in _PROTECTED_ROUTE_KEYWORDS:
            if keyword in file_path or keyword in evidence:
                result.security_violations.append(
                    f"SEC-5: public access added to protected route "
                    f"containing '{keyword}' — {p.get('file', '')}:{p.get('line_number', '?')}"
                )
                result.rule_triggers.append({
                    "rule": "SEC-5",
                    "case": "protected_route_public",
                    "added": [p.get("pattern", "")],
                    "severity": "violation",
                    "decision": "revise_code",
                    "reason": f"public access added to protected route containing '{keyword}'; verify that this route is intended to be public.",
                    "evidence": _build_evidence(
                        candidate=[p],
                        summary=f"candidate {p.get('file', '?')}:{p.get('line_number', '?')} {p.get('pattern', '')[:40]}",
                    ),
                    "protected_keyword": keyword,
                })
                break


def _check_sec6_auth_boundary_removal(
    result: SecurityPolicyResult,
    removed_by_kind: Dict[str, List[Dict]],
    added_by_kind: Dict[str, List[Dict]],
) -> None:
    """SEC-6: Auth boundary removal.

    Triggers when auth_boundary patterns (decorators, middleware,
    Depends(), annotations) are removed from the baseline.

    Two sub-cases:
      - auth_deleted: auth boundary removed with no replacement → escalate
      - auth_refactored: auth boundary removed AND re-added → warning
    """
    removed_auth = removed_by_kind.get("auth_boundary", [])
    if not removed_auth:
        return

    added_auth = added_by_kind.get("auth_boundary", [])

    if added_auth:
        # Auth boundary was refactored (removed + re-added)
        result.security_warnings.append(
            f"SEC-6: Auth boundary modified — "
            f"removed ({_patterns_summary(removed_auth)}), "
            f"re-added ({_patterns_summary(added_auth)}) — "
            f"verify the new implementation is equivalent"
        )
        result.rule_triggers.append({
            "rule": "SEC-6",
            "case": "auth_refactored",
            "removed": [p.get("pattern", "") for p in removed_auth],
            "added": [p.get("pattern", "") for p in added_auth],
            "severity": "advisory",
            "decision": "advisory",
            "reason": "Auth boundary was refactored (removed and re-added); verify equivalence.",
            "evidence": _build_evidence(
                baseline=removed_auth,
                candidate=added_auth,
                summary=_evidence_summary_oneliner(removed_auth, added_auth),
            ),
        })
    else:
        # Auth boundary deleted without replacement
        result.security_violations.append(
            f"SEC-6: Auth boundary removed ({_patterns_summary(removed_auth)}) "
            f"without replacement — authentication enforcement may be disabled"
        )
        result.rule_triggers.append({
            "rule": "SEC-6",
            "case": "auth_deleted",
            "removed": [p.get("pattern", "") for p in removed_auth],
            "severity": "violation",
            "decision": "escalate_to_human",
            "reason": "Auth boundary removed without replacement; authentication enforcement may be disabled.",
            "evidence": _build_evidence(
                baseline=removed_auth,
                summary=_evidence_summary_oneliner(removed_auth),
            ),
        })


def _check_sec8_tenant_scope_removal(
    result: SecurityPolicyResult,
    removed_by_kind: Dict[str, List[Dict]],
    added_by_kind: Dict[str, List[Dict]],
) -> None:
    """SEC-8: Tenant/org scope removal.

    Triggers when tenant_scope patterns (query filters, repository methods)
    are removed from the baseline.

    Two sub-cases:
      - scope_deleted: tenant scope removed with no replacement → escalate
      - scope_refactored: tenant scope removed AND re-added → warning
    """
    removed_scope = removed_by_kind.get("tenant_scope", [])
    if not removed_scope:
        return

    added_scope = added_by_kind.get("tenant_scope", [])

    if added_scope:
        # Scope was refactored (removed + re-added)
        result.security_warnings.append(
            f"SEC-8: Tenant/org scope modified — "
            f"removed ({_patterns_summary(removed_scope)}), "
            f"re-added ({_patterns_summary(added_scope)}) — "
            f"verify the new scope is equivalent"
        )
        result.rule_triggers.append({
            "rule": "SEC-8",
            "case": "scope_refactored",
            "removed": [p.get("pattern", "") for p in removed_scope],
            "added": [p.get("pattern", "") for p in added_scope],
            "severity": "advisory",
            "decision": "advisory",
            "reason": "Tenant/org scope was refactored (removed and re-added); verify equivalence.",
            "evidence": _build_evidence(
                baseline=removed_scope,
                candidate=added_scope,
                summary=_evidence_summary_oneliner(removed_scope, added_scope),
            ),
        })
    else:
        # Scope deleted without replacement — cross-tenant access risk
        result.security_violations.append(
            f"SEC-8: Tenant/org scope removed ({_patterns_summary(removed_scope)}) "
            f"without replacement — cross-tenant data access may be possible"
        )
        result.rule_triggers.append({
            "rule": "SEC-8",
            "case": "scope_deleted",
            "removed": [p.get("pattern", "") for p in removed_scope],
            "severity": "violation",
            "decision": "escalate_to_human",
            "reason": "Tenant/org scope removed without replacement; cross-tenant data access may be possible.",
            "evidence": _build_evidence(
                baseline=removed_scope,
                summary=_evidence_summary_oneliner(removed_scope),
            ),
        })


# Obvious always-allow patterns that should never replace real authorization checks
_ALWAYS_ALLOW_PATTERNS = {
    "permitall", "anyrequest().permitall()", "return true",
    "if true", "|| true", "or true", "allowall", "permit_all",
    "allow_all", ".permitall()", "@permitall",
}


def _check_sec7_authorization_weakening(
    result: SecurityPolicyResult,
    removed_by_kind: Dict[str, List[Dict]],
    added_by_kind: Dict[str, List[Dict]],
) -> None:
    """SEC-7: Admin/owner/role/permission check weakening.

    Three tiers:
      SEC-7a (deletion): authorization_check removed, no replacement → violation (revise_code)
      SEC-7b (weakening): authorization_check changed → warning only
      SEC-7c (always-allow): obvious permitAll/if True pattern added → violation (escalate)
    """
    removed_authz = removed_by_kind.get("authorization_check", [])
    added_authz = added_by_kind.get("authorization_check", [])

    # SEC-7c: Check for always-allow patterns in added authorization checks
    always_allow_added = [
        p for p in added_authz
        if any(aa in p.get("pattern", "").lower() for aa in _ALWAYS_ALLOW_PATTERNS)
    ]
    if always_allow_added:
        result.security_violations.append(
            f"SEC-7: Always-allow pattern added ({_patterns_summary(always_allow_added)}) "
            f"— authorization check effectively disabled"
        )
        result.rule_triggers.append({
            "rule": "SEC-7",
            "case": "always_allow",
            "added": [p.get("pattern", "") for p in always_allow_added],
            "severity": "violation",
            "decision": "escalate_to_human",
            "reason": "Always-allow pattern added; authorization check effectively disabled.",
            "evidence": _build_evidence(
                candidate=always_allow_added,
                summary=_evidence_summary_oneliner(None, always_allow_added),
            ),
        })
        return

    if not removed_authz:
        return

    if added_authz:
        # SEC-7b: Authorization check changed (removed + re-added) → warning
        result.security_warnings.append(
            f"SEC-7: Authorization check modified — "
            f"removed ({_patterns_summary(removed_authz)}), "
            f"replaced with ({_patterns_summary(added_authz)}) — "
            f"verify the new check is equivalent"
        )
        result.rule_triggers.append({
            "rule": "SEC-7",
            "case": "authz_changed",
            "removed": [p.get("pattern", "") for p in removed_authz],
            "added": [p.get("pattern", "") for p in added_authz],
            "severity": "advisory",
            "decision": "advisory",
            "reason": "Authorization check was modified; verify the new check is equivalent.",
            "evidence": _build_evidence(
                baseline=removed_authz,
                candidate=added_authz,
                summary=_evidence_summary_oneliner(removed_authz, added_authz),
            ),
        })
    else:
        # SEC-7a: Authorization check deleted without replacement → violation
        result.security_violations.append(
            f"SEC-7: Authorization check removed ({_patterns_summary(removed_authz)}) "
            f"without replacement — admin/owner access control may be disabled"
        )
        result.rule_triggers.append({
            "rule": "SEC-7",
            "case": "authz_deleted",
            "removed": [p.get("pattern", "") for p in removed_authz],
            "severity": "violation",
            "decision": "revise_code",
            "reason": "Authorization check removed without replacement; access control may be disabled.",
            "evidence": _build_evidence(
                baseline=removed_authz,
                summary=_evidence_summary_oneliner(removed_authz),
            ),
        })


def _check_sec9_user_controlled_privilege(
    result: SecurityPolicyResult,
    added_by_kind: Dict[str, List[Dict]],
) -> None:
    """SEC-9: User-controlled privilege trust.

    Triggers when user_controlled_privilege patterns are added.
    Trusting role/isAdmin/userId/tenantId from request body/query
    is always a violation — client-supplied privilege must never be trusted.

    Decision: revise_code
    """
    added_priv = added_by_kind.get("user_controlled_privilege", [])
    if not added_priv:
        return

    result.security_violations.append(
        f"SEC-9: User-controlled privilege trusted ({_patterns_summary(added_priv)}) "
        f"— role/admin/userId from request body must not be trusted for authorization"
    )
    result.rule_triggers.append({
        "rule": "SEC-9",
        "case": "privilege_from_body",
        "added": [p.get("pattern", "") for p in added_priv],
        "severity": "violation",
        "decision": "revise_code",
        "reason": "User-controlled privilege from request body must not be trusted for authorization.",
        "evidence": _build_evidence(
            candidate=added_priv,
            summary=_evidence_summary_oneliner(None, added_priv),
        ),
    })


# Relaxed security config indicators
_RELAXED_CONFIG_PATTERNS = {
    "origin: '*'", 'origin: "*"', "origin: *", "origins: ['*']",
    "allow_origins=[\"*\"]", "allow_origins=['*']",
    "secure: false", "httponly: false", "httpOnly: false",
    "samesite: 'none'", "samesite: none", "sameSite: 'none'",
    "csrf: false", "verify: false", "cors()",
    "credentials: false", "SESSION_COOKIE_SECURE = False",
    "SESSION_COOKIE_HTTPONLY = False", "SECURE_SSL_REDIRECT = False",
}


def _check_sec10_security_config_relaxation(
    result: SecurityPolicyResult,
    removed_by_kind: Dict[str, List[Dict]],
    added_by_kind: Dict[str, List[Dict]],
) -> None:
    """SEC-10: Security config relaxation.

    Triggers when:
      - security_config kind in removed (strict config removed)
        AND relaxed config added in its place
      - OR security_config kind removed with no replacement

    New security restrictions being added are NOT violations.

    Decision: revise_code
    """
    removed_config = removed_by_kind.get("security_config", [])
    added_config = added_by_kind.get("security_config", [])

    # Check for relaxed patterns in added configs
    relaxed_added = [
        p for p in added_config
        if any(
            rp in p.get("pattern", "").lower()
            for rp in (r.lower() for r in _RELAXED_CONFIG_PATTERNS)
        )
    ]

    if relaxed_added:
        result.security_violations.append(
            f"SEC-10: Security config relaxed ({_patterns_summary(relaxed_added)}) "
            f"\u2014 CORS/cookie/CSRF/JWT settings weakened"
        )
        result.rule_triggers.append({
            "rule": "SEC-10",
            "case": "config_relaxed",
            "added": [p.get("pattern", "") for p in relaxed_added],
            "severity": "violation",
            "decision": "revise_code",
            "reason": "Security config relaxed; CORS/cookie/CSRF/JWT settings weakened.",
            "evidence": _build_evidence(
                candidate=relaxed_added,
                summary=_evidence_summary_oneliner(None, relaxed_added),
            ),
        })
        return

    if removed_config and not added_config:
        # Security config deleted without replacement
        result.security_violations.append(
            f"SEC-10: Security config removed ({_patterns_summary(removed_config)}) "
            f"without replacement \u2014 security settings may be at defaults"
        )
        result.rule_triggers.append({
            "rule": "SEC-10",
            "case": "config_deleted",
            "removed": [p.get("pattern", "") for p in removed_config],
            "severity": "violation",
            "decision": "revise_code",
            "reason": "Security config removed without replacement; settings may be at insecure defaults.",
            "evidence": _build_evidence(
                baseline=removed_config,
                summary=_evidence_summary_oneliner(removed_config),
            ),
        })
    elif removed_config and added_config and not relaxed_added:
        # Config changed but not to a known-relaxed pattern \u2014 advisory
        result.security_warnings.append(
            f"SEC-10: Security config modified \u2014 "
            f"removed ({_patterns_summary(removed_config)}), "
            f"replaced with ({_patterns_summary(added_config)}) \u2014 "
            f"verify the new config is equivalent or stricter"
        )
        result.rule_triggers.append({
            "rule": "SEC-10",
            "case": "config_changed",
            "removed": [p.get("pattern", "") for p in removed_config],
            "added": [p.get("pattern", "") for p in added_config],
            "severity": "advisory",
            "decision": "advisory",
            "reason": "Security config was modified; verify the new config is equivalent or stricter.",
            "evidence": _build_evidence(
                baseline=removed_config,
                candidate=added_config,
                summary=_evidence_summary_oneliner(removed_config, added_config),
            ),
        })



# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _evidence_point(p: Dict) -> Dict:
    """Convert a raw pattern dict into an evidence point."""
    return {
        "file": p.get("file", ""),
        "line": p.get("line_number", 0),
        "kind": p.get("kind", ""),
        "pattern": p.get("pattern", ""),
        "snippet": p.get("context", "") or p.get("pattern", ""),
    }


def _build_evidence(
    baseline: Optional[List[Dict]] = None,
    candidate: Optional[List[Dict]] = None,
    summary: str = "",
) -> Dict:
    """Convert raw pattern dicts into a structured evidence block.

    Returns a dict suitable for inclusion in rule_triggers:
        {
            "baseline": [{"file": ..., "line": ..., "kind": ..., "pattern": ...}, ...],
            "candidate": [...],
            "summary": "Human-readable explanation of the evidence"
        }
    """
    return {
        "baseline": [_evidence_point(p) for p in (baseline or [])],
        "candidate": [_evidence_point(p) for p in (candidate or [])],
        "summary": summary,
    }


def _evidence_summary_oneliner(
    baseline_patterns: Optional[List[Dict]] = None,
    candidate_patterns: Optional[List[Dict]] = None,
) -> str:
    """Build a compact one-line evidence summary for display.

    Format: 'baseline file:line pattern → candidate file:line pattern'
    or 'baseline file:line pattern → candidate none'
    """
    parts = []
    for label, pats in [("baseline", baseline_patterns), ("candidate", candidate_patterns)]:
        if pats:
            items = []
            for p in pats[:2]:
                f = p.get("file", "?").rsplit("/", 1)[-1]
                ln = p.get("line_number", "?")
                pat = p.get("pattern", "?")[:40]
                items.append(f"{f}:{ln} {pat}")
            parts.append(f"{label} " + ", ".join(items))
        else:
            parts.append(f"{label} none")
    return " → ".join(parts)


def _group_by_kind(patterns: List[Dict]) -> Dict[str, List[Dict]]:
    """Group pattern dicts by their 'kind' field."""
    groups: Dict[str, List[Dict]] = {}
    for p in patterns:
        kind = p.get("kind", "other")
        groups.setdefault(kind, []).append(p)
    return groups


def _is_token_auth_pattern(pattern: str) -> bool:
    """Check if a pattern represents a token/auth check."""
    lower = pattern.lower().strip()
    return any(kw in lower for kw in _TOKEN_AUTH_PATTERNS)


def _is_guest_pattern(pattern: str) -> bool:
    """Check if a pattern represents a guest bypass condition."""
    lower = pattern.lower().strip()
    return any(kw in lower for kw in _GUEST_BYPASS_PATTERNS)


def _is_guest_storage_key(pattern: str) -> bool:
    """Check if a storage access pattern uses a guest-related key."""
    lower = pattern.lower()
    guest_keys = {"guest", "guestmode", "guest_mode", "guest_token", "is_guest"}
    return any(k in lower for k in guest_keys)


def _has_public_true(pattern: str) -> bool:
    """Check whether a route meta pattern explicitly enables public access."""
    return bool(re.search(r"\bpublic\s*:\s*true\b", pattern, re.IGNORECASE))


def _is_scoped_guest_guard_condition(
    pattern: Dict,
    added_by_kind: Dict[str, List[Dict]],
    files_content: Optional[Dict[str, str]],
) -> bool:
    """Return True when a guest condition is scoped to route metadata.

    T5-style implementations often assign a route-scoped alias first, e.g.
    `const isGuest = Boolean(to.meta?.guest)`, then use the alias in the
    guard condition. That is different from T6-style global guest state such
    as `const guest = isGuestMode()`.
    """
    pattern_text = pattern.get("pattern", "").lower()

    if (
        "to.meta" in pattern_text
        or "meta.guest" in pattern_text
        or "meta?.guest" in pattern_text
    ):
        return True

    has_guest_route_meta = any(
        "guest" in p.get("pattern", "").lower()
        for p in added_by_kind.get("route_meta", [])
    )
    if not has_guest_route_meta or not files_content:
        return False

    aliases = _route_guest_aliases(files_content)
    return any(alias in pattern_text for alias in aliases)


def _route_guest_aliases(files_content: Dict[str, str]) -> set[str]:
    """Find variables assigned from to.meta.guest in router files."""
    aliases: set[str] = set()

    alias_re = re.compile(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
        r"(?:Boolean\s*\(\s*)?(?:!!\s*)?to\.meta\??\.guest\s*\)?",
        re.IGNORECASE,
    )

    for fpath, content in files_content.items():
        if not _is_router_file(fpath):
            continue
        for match in alias_re.finditer(content):
            aliases.add(match.group(1).lower())

    return aliases


def _is_router_file(filepath: str) -> bool:
    """Check if a file path is likely a router configuration file."""
    lower = filepath.lower()
    return "router" in lower or "route" in lower


def _patterns_summary(patterns: List[Dict], max_items: int = 3) -> str:
    """Create a brief summary string from a list of pattern dicts."""
    items = [p.get("pattern", "?")[:60] for p in patterns[:max_items]]
    summary = ", ".join(items)
    if len(patterns) > max_items:
        summary += f" (+{len(patterns) - max_items} more)"
    return summary
