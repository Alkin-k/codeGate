"""Python / FastAPI / Django / Flask security pattern extractor.

Extracts security-relevant patterns from Python backend source files.

Extraction targets:
  - Auth boundary: Depends(get_current_user), @login_required, etc.
  - Authorization check: Depends(require_admin), @permission_required, etc.
  - Tenant scope: .filter(tenant_id=...), .filter(org_id=...)
  - User-controlled privilege: request.body.role, data['is_admin'], etc.
  - Security config: CORS_ORIGINS, SESSION_COOKIE_SECURE, etc.

Design boundary: this module produces FACTS, not judgments.
Policy rules in codegate.policies.security consume these facts.
"""

from __future__ import annotations

import re
from typing import List

from codegate.analysis.baseline_diff import PatternMatch


# ---------------------------------------------------------------------------
# Pattern regexes
# ---------------------------------------------------------------------------

# FastAPI auth dependency injection patterns
# Matches: Depends(get_current_user), Depends(require_admin), etc.
_FASTAPI_AUTH_DEPENDS_RE = re.compile(
    r"Depends\s*\(\s*(get_current_user|get_current_active_user|require_admin|"
    r"require_role|require_admin_role|require_auth|get_user|current_user|verify_token|"
    r"check_permission|require_permission|auth_required|get_authenticated_user)\s*"
    r"(?:\([^)]*\))?\s*\)",
    re.MULTILINE,
)

# General Depends() for tenant/org scoping
# Matches: Depends(get_tenant), Depends(get_org), etc.
_FASTAPI_TENANT_DEPENDS_RE = re.compile(
    r"Depends\s*\(\s*(get_tenant|get_org|get_organization|get_org_context|"
    r"get_tenant_id|get_org_id|verify_tenant|require_tenant|get_tenant_context)\s*"
    r"(?:\([^)]*\))?\s*\)",
    re.MULTILINE,
)

# Flask/Django auth decorators
# Matches: @login_required, @permission_required(...), @user_passes_test(...)
_PYTHON_AUTH_DECORATOR_RE = re.compile(
    r"@(login_required|permission_required|user_passes_test|"
    r"staff_member_required|admin_required|requires_auth|"
    r"jwt_required|auth_required|token_required|requires_login)"
    r"(?:\([^)]*\))?",
    re.MULTILINE,
)

# ORM tenant/user scope in queries
# Matches: .filter(tenant_id=...), .filter(org_id=...), .filter(user_id=current_user.id)
_PYTHON_TENANT_QUERY_RE = re.compile(
    r"\.\s*filter\s*\(\s*(?:\w+__)?(?:tenant_id|org_id|organization_id|user_id)\s*=",
    re.MULTILINE,
)

# SQLAlchemy tenant scope patterns
# Matches: .where(Model.tenant_id == ...), Model.tenant_id ==
_PYTHON_SA_TENANT_RE = re.compile(
    r"\.(?:where|filter)\s*\([^)]*(?:tenant_id|org_id|organization_id)\s*==",
    re.MULTILINE,
)

# User-controlled privilege patterns (DANGEROUS — should never trust client data for auth)
# Matches: request.json.get('role'), data['is_admin'], body.role, req.body.userId
_PYTHON_USER_PRIVILEGE_RE = re.compile(
    r"(?:request\.(?:json|data|form|args|values)(?:\.get)?\s*\[\s*['\"]"
    r"(?:role|is_admin|isAdmin|user_id|userId|tenant_id|tenantId|permissions?)"
    r"['\"]\s*\]"
    r"|request\.(?:json|data|form|args|values)\.get\s*\(\s*['\"]"
    r"(?:role|is_admin|isAdmin|user_id|userId|tenant_id|tenantId|permissions?)"
    r"['\"]"
    r"|(?:body|data|payload)\s*(?:\[|\.)\s*['\"]?"
    r"(?:role|is_admin|isAdmin|user_id|userId|tenant_id|tenantId)['\"]?\s*[\].]?)",
    re.MULTILINE,
)

# Security configuration patterns
# Matches: CORS_ORIGINS, CSRF_TRUSTED_ORIGINS, SESSION_COOKIE_SECURE, etc.
_PYTHON_SECURITY_CONFIG_RE = re.compile(
    r"^\s*(?:CORS_ORIGIN\w*|CSRF_\w+|SESSION_COOKIE_SECURE|SESSION_COOKIE_HTTPONLY|"
    r"SESSION_COOKIE_SAMESITE|SECURE_SSL_REDIRECT|SECURE_HSTS_\w+|"
    r"JWT_VERIFY\w*|JWT_SECRET\w*|SECRET_KEY|ALLOWED_HOSTS)\s*=\s*(.+)",
    re.MULTILINE,
)

# FastAPI CORS middleware configuration
# Matches: CORSMiddleware, allow_origins=..., allow_credentials=...
_FASTAPI_CORS_RE = re.compile(
    r"(?:CORSMiddleware|add_middleware\s*\(\s*CORSMiddleware)\s*[,(]\s*"
    r"|allow_origins\s*=\s*(\[[^\]]*\]|[^\s,)]+)"
    r"|allow_credentials\s*=\s*(True|False)",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_python_security_patterns(
    filepath: str, content: str,
) -> List[PatternMatch]:
    """Extract security-relevant patterns from a Python source file.

    Returns PatternMatch objects with kinds:
      - "auth_boundary": auth decorators and dependencies
      - "authorization_check": role/permission checks
      - "tenant_scope": tenant/org/user scope filters
      - "user_controlled_privilege": trusting client-supplied auth data
      - "security_config": CORS, CSRF, cookie, JWT configuration
    """
    lines = content.split("\n")
    patterns: List[PatternMatch] = []

    # --- 1. FastAPI auth Depends() ---
    for m in _FASTAPI_AUTH_DEPENDS_RE.finditer(content):
        line_num = _line_number(content, m.start())
        dep_name = m.group(1)
        # require_admin/require_role/require_permission → authorization_check
        if any(kw in dep_name for kw in ("admin", "role", "permission")):
            kind = "authorization_check"
        else:
            kind = "auth_boundary"
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind=kind,
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 2. FastAPI tenant Depends() ---
    for m in _FASTAPI_TENANT_DEPENDS_RE.finditer(content):
        line_num = _line_number(content, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="tenant_scope",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 3. Flask/Django auth decorators ---
    for m in _PYTHON_AUTH_DECORATOR_RE.finditer(content):
        line_num = _line_number(content, m.start())
        dec_name = m.group(1)
        if any(kw in dec_name for kw in ("permission", "admin", "staff")):
            kind = "authorization_check"
        else:
            kind = "auth_boundary"
        patterns.append(PatternMatch(
            file=filepath,
            pattern=f"@{m.group(0).strip().lstrip('@')}",
            kind=kind,
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 4. ORM tenant/user scope queries ---
    for m in _PYTHON_TENANT_QUERY_RE.finditer(content):
        line_num = _line_number(content, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="tenant_scope",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 4b. SQLAlchemy tenant scope ---
    for m in _PYTHON_SA_TENANT_RE.finditer(content):
        line_num = _line_number(content, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="tenant_scope",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 5. User-controlled privilege (DANGEROUS) ---
    for m in _PYTHON_USER_PRIVILEGE_RE.finditer(content):
        line_num = _line_number(content, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="user_controlled_privilege",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 6. Security configuration ---
    for m in _PYTHON_SECURITY_CONFIG_RE.finditer(content):
        line_num = _line_number(content, m.start())
        # Include the value in the pattern for SEC-10 value-change detection
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="security_config",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 7. FastAPI CORS middleware ---
    for m in _FASTAPI_CORS_RE.finditer(content):
        line_num = _line_number(content, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="security_config",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    return _deduplicate(patterns)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_number(content: str, char_offset: int) -> int:
    """Convert character offset to 1-based line number."""
    return content[:char_offset].count("\n") + 1


def _context_line(lines: List[str], line_num: int) -> str:
    """Get the line at 1-based line_num, or empty string."""
    if 1 <= line_num <= len(lines):
        return lines[line_num - 1].strip()
    return ""


def _deduplicate(patterns: List[PatternMatch]) -> List[PatternMatch]:
    """Remove duplicate patterns (same pattern text + kind)."""
    seen: set[tuple[str, str]] = set()
    result: List[PatternMatch] = []
    for p in patterns:
        key = (p.pattern.strip(), p.kind)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result
