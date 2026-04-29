"""Security Policy Gate — auth/routing risk detection for frontend code changes.

Consumes structural_diff facts (produced by TypeScript/Vue extractors)
to detect auth bypass, token logic deletion, and unscoped guest access.

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
            "evidence": [p.get("pattern", "") for p in removed_guards],
            "decision": "escalate_to_human",
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
            "decision": "escalate_to_human",
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
            "decision": "escalate_to_human",
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
            "evidence": [p.get("pattern", "") for p in guest_storage],
            "decision": "advisory",
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
            "evidence": [p.get("pattern", "") for p in all_guest_in_guard],
            "decision": "advisory",
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
            "evidence": [p.get("pattern", "") for p in all_guest_in_guard],
            "decision": "revise_code",
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
            "evidence": [p.get("pattern", "") for p in all_guest_in_guard],
            "decision": "escalate_to_human",
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
                "decision": "revise_code",
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
                "decision": "advisory",
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
            "decision": "revise_code",
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
                    "evidence": p.get("pattern", ""),
                    "context": p.get("context", ""),
                    "file": p.get("file", ""),
                    "protected_keyword": keyword,
                    "decision": "revise_code",
                })
                break


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


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
