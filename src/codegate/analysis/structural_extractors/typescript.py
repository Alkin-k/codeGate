"""TypeScript / Vue structural pattern extractor.

Extracts security-relevant and interface-relevant patterns from
TypeScript (.ts/.tsx) and Vue (.vue) files.

Frontend extraction targets:
  - router.beforeEach guard bodies
  - Auth conditions: getToken, !token, isPublic, isGuestMode, guestMode
  - Route meta definitions: meta.public, meta.guest, meta.requiresAuth
  - localStorage/sessionStorage key access
  - Import declarations

Backend extraction targets (v0.4, Express/Nest/Fastify/Hono):
  - Auth middleware: app.use(authMiddleware), router.use(requireAuth)
  - req.user / req.session.user access
  - CORS config: cors({ origin: ... })
  - Cookie config: cookie({ secure: ..., httpOnly: ... })
  - JWT verify: jwt.verify, jsonwebtoken
  - User-controlled privilege: req.body.role, req.body.isAdmin
  - Tenant scope: req.user.tenantId, where tenant_id = req.user.tenantId

Each extracted pattern becomes a PatternMatch with a specific `kind`
that the Security Policy Gate can consume for governance decisions.

Design boundary: this module produces FACTS, not judgments.
"""

from __future__ import annotations

import re
from typing import List

from codegate.analysis.baseline_diff import PatternMatch

# ---------------------------------------------------------------------------
# Vue SFC helpers
# ---------------------------------------------------------------------------

def _extract_script_content(content: str) -> str:
    """Extract <script> or <script setup> block content from a Vue SFC.

    If the file is not a Vue SFC (no <script> tag found), returns the
    full content — it's likely a plain .ts file.
    """
    # Match <script ...> ... </script>, including setup attribute
    pattern = re.compile(
        r"<script\b[^>]*>(.*?)</script>",
        re.DOTALL | re.IGNORECASE,
    )
    matches = pattern.findall(content)
    if matches:
        return "\n".join(matches)
    # No <script> tag — treat entire content as script
    return content


# ---------------------------------------------------------------------------
# Pattern regexes
# ---------------------------------------------------------------------------

# router.beforeEach guard — captures the condition/body signature
_ROUTER_GUARD_RE = re.compile(
    r"router\.beforeEach\s*\(\s*(?:async\s*)?"
    r"(?:\(([^)]*)\)|(\w+))\s*(?:=>|,)",
    re.MULTILINE,
)

# Auth-related conditions — captures the full condition expression
# Matches patterns like: !token, !getToken(), isGuestMode, guestMode,
# isPublic, !isPublic, localStorage.getItem('token')
_AUTH_CONDITION_RE = re.compile(
    r"(?:^|[(\s&|!])(!?\s*(?:token|isPublic|isGuestMode|guestMode|getToken\s*\([^)]*\)|isAuthenticated|isLoggedIn|guest))\b",
    re.MULTILINE,
)

# Route meta definitions — captures meta object with auth-related keys
_ROUTE_META_RE = re.compile(
    r"meta\s*:\s*\{([^}]*)\}",
    re.MULTILINE,
)

# Auth-relevant meta keys inside a meta object
_META_AUTH_KEYS = re.compile(
    r"(public|guest|requiresAuth|requireAuth|auth|isPublic)\s*:",
    re.IGNORECASE,
)

_ROUTE_FIELD_STRING_RE = re.compile(
    r"\b(path|name|title)\s*:\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)

_ROUTE_COMPONENT_RE = re.compile(
    r"\bcomponent\s*:\s*([A-Za-z_$][\w$]*)",
    re.IGNORECASE,
)

# localStorage / sessionStorage operations
_STORAGE_ACCESS_RE = re.compile(
    r"(?:localStorage|sessionStorage)\s*\.\s*"
    r"(getItem|setItem|removeItem)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)

# Import declarations
_TS_IMPORT_RE = re.compile(
    r"^import\s+(.*?)\s+from\s+['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)

# Guard body extractor — extracts lines within router.beforeEach callback
# This captures the full guard body for policy analysis
_GUARD_BODY_RE = re.compile(
    r"router\.beforeEach\s*\(.*?(?:=>|,)\s*\{(.*?)\n\}\s*\)",
    re.DOTALL,
)

# Condition expressions involving guest/token/auth within guard bodies
_GUARD_CONDITION_RE = re.compile(
    r"(?:if|else\s*if)\s*\(\s*(.*?)\s*\)\s*\{",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Backend TS/Node/Express patterns (v0.4)
# ---------------------------------------------------------------------------

# Express middleware registration: app.use(auth), router.use(requireAuth)
_EXPRESS_MIDDLEWARE_RE = re.compile(
    r"(?:app|router)\s*\.\s*use\s*\(\s*"
    r"(auth\w*|requireAuth\w*|authenticate\w*|passport\.\w+|verifyToken\w*|isLoggedIn|ensureAuth\w*)"
    r"\s*(?:\([^)]*\))?\s*\)",
    re.MULTILINE,
)

# Express route handlers: app.get/post/put/delete/patch
_EXPRESS_ROUTE_RE = re.compile(
    r"(?:app|router)\s*\.\s*(get|post|put|delete|patch)\s*\("
    r"\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)

# req.user / req.session.user / req.userId access
_REQ_USER_RE = re.compile(
    r"req\s*\.\s*(user|session\.user|userId|currentUser|auth)"
    r"(?:\s*\.\s*(\w+))?",
    re.MULTILINE,
)

# CORS config: cors({ origin: ... }), cors('*'), cors()
_CORS_CONFIG_RE = re.compile(
    r"cors\s*\(\s*(?:\{[^}]*\}|['\"][^'\"]*['\"]|\s*)"
    r"\s*\)",
    re.DOTALL,
)

# Cookie config: cookie({ secure: ..., httpOnly: ..., sameSite: ... })
_COOKIE_CONFIG_RE = re.compile(
    r"(?:cookie|cookieParser|session)\s*\(\s*\{[^}]*"
    r"(?:secure|httpOnly|httponly|sameSite|samesite)\s*:\s*[^}]*\}",
    re.DOTALL | re.IGNORECASE,
)

# JWT verify: jwt.verify, jwt.sign, jsonwebtoken
_JWT_VERIFY_RE = re.compile(
    r"(?:jwt|jsonwebtoken)\s*\.\s*(verify|sign|decode)\s*\(",
    re.MULTILINE,
)

# User-controlled privilege from request body
# Matches: req.body.role, req.body.isAdmin, req.query.userId, req.body.tenantId
_EXPRESS_USER_PRIVILEGE_RE = re.compile(
    r"req\s*\.\s*(?:body|query|params)\s*\.\s*"
    r"(role|isAdmin|is_admin|userId|user_id|tenantId|tenant_id|permissions?)",
    re.MULTILINE,
)

# Tenant scope patterns: req.user.tenantId, req.user.orgId
_EXPRESS_TENANT_SCOPE_RE = re.compile(
    r"req\s*\.\s*(?:user|auth|session)\s*\.\s*"
    r"(tenantId|tenant_id|orgId|org_id|organizationId|organization_id)",
    re.MULTILINE,
)

# Backend import detection heuristic
_BACKEND_IMPORTS = {
    "express", "koa", "@nestjs", "fastify", "hono",
    "@hapi", "restify", "polka",
}

_BACKEND_PATH_HINTS = {
    "server", "api", "controllers", "controller",
    "middleware", "backend", "routes/api",
}


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_typescript_patterns(filepath: str, content: str) -> List[PatternMatch]:
    """Extract trackable patterns from a TypeScript or Vue file.

    Returns PatternMatch objects with kinds:
      Frontend:
        - "router_guard": router.beforeEach callback presence and params
        - "auth_condition": token/public/guest condition expressions
        - "route_meta": route configuration meta fields
        - "storage_access": localStorage/sessionStorage operations
        - "import": import declarations
        - "guard_body": full guard body content (for policy analysis)
      Backend (Express/Nest/Fastify, when detected):
        - "auth_boundary": auth middleware registration
        - "authorization_check": req.user access
        - "route_handler": Express route definitions
        - "security_config": CORS, cookie, JWT configuration
        - "user_controlled_privilege": req.body.role, req.body.isAdmin
        - "tenant_scope": req.user.tenantId
    """
    # For Vue SFCs, extract only the <script> section
    ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""
    if ext == "vue":
        script_content = _extract_script_content(content)
    else:
        script_content = content

    script_lines = script_content.split("\n")
    patterns: List[PatternMatch] = []

    # --- 1. Router guard ---
    for m in _ROUTER_GUARD_RE.finditer(script_content):
        line_num = _line_number(script_content, m.start())
        params = m.group(1) or m.group(2) or ""
        patterns.append(PatternMatch(
            file=filepath,
            pattern=f"router.beforeEach({params.strip()})",
            kind="router_guard",
            line_number=line_num,
            context=_context_line(script_lines, line_num),
        ))

    # --- 2. Guard body (full content for policy analysis) ---
    for m in _GUARD_BODY_RE.finditer(script_content):
        line_num = _line_number(script_content, m.start())
        body = m.group(1).strip()
        # Extract conditions within the guard body
        for cm in _GUARD_CONDITION_RE.finditer(body):
            condition = cm.group(1).strip()
            cond_line = _line_number(script_content, m.start() + cm.start())
            patterns.append(PatternMatch(
                file=filepath,
                pattern=condition,
                kind="guard_condition",
                line_number=cond_line,
                context=condition,
            ))

    # --- 3. Auth conditions (anywhere in script) ---
    for m in _AUTH_CONDITION_RE.finditer(script_content):
        line_num = _line_number(script_content, m.start())
        condition = m.group(1).strip()
        patterns.append(PatternMatch(
            file=filepath,
            pattern=condition,
            kind="auth_condition",
            line_number=line_num,
            context=_context_line(script_lines, line_num),
        ))

    # --- 4. Route meta ---
    for m in _ROUTE_META_RE.finditer(script_content):
        meta_body = m.group(1)
        # Only emit if meta contains auth-related keys
        if _META_AUTH_KEYS.search(meta_body):
            line_num = _line_number(script_content, m.start())
            route_context = _route_context_for_meta(script_content, m.start())
            route_bits = _route_context_bits(route_context)
            route_prefix = ""
            if route_bits:
                route_prefix = "route(" + ", ".join(route_bits) + ", "
            patterns.append(PatternMatch(
                file=filepath,
                pattern=f"{route_prefix}meta: {{{meta_body.strip()}}}"
                        f"{')' if route_prefix else ''}",
                kind="route_meta",
                line_number=line_num,
                context=route_context or _context_line(script_lines, line_num),
            ))

    # --- 5. Storage access ---
    for m in _STORAGE_ACCESS_RE.finditer(script_content):
        line_num = _line_number(script_content, m.start())
        operation = m.group(1)
        key = m.group(2)
        patterns.append(PatternMatch(
            file=filepath,
            pattern=f"localStorage.{operation}('{key}')",
            kind="storage_access",
            line_number=line_num,
            context=_context_line(script_lines, line_num),
        ))

    # --- 6. Imports ---
    for m in _TS_IMPORT_RE.finditer(script_content):
        line_num = _line_number(script_content, m.start())
        imported = m.group(1).strip()
        source = m.group(2).strip()
        patterns.append(PatternMatch(
            file=filepath,
            pattern=f"import {imported} from '{source}'",
            kind="import",
            line_number=line_num,
            context=_context_line(script_lines, line_num),
        ))

    # --- 7. Backend TS/Node/Express mode (v0.4) ---
    if _is_likely_backend_ts(filepath, content):
        patterns.extend(
            _extract_backend_ts_patterns(filepath, content, script_lines)
        )

    return _deduplicate(patterns)


# ---------------------------------------------------------------------------
# Backend TS/Node/Express extraction (v0.4)
# ---------------------------------------------------------------------------


def _strip_ts_comments(content: str) -> str:
    """Replace TS/JS comments with whitespace to preserve line numbers.

    Handles // line comments and /* */ block comments.
    Replaces non-newline characters with spaces.
    """
    # Strip // line comments
    content = re.sub(r'//[^\n]*', lambda m: ' ' * len(m.group()), content)
    # Strip /* */ block comments (preserve newlines)
    content = re.sub(
        r'/\*.*?\*/',
        lambda m: re.sub(r'[^\n]', ' ', m.group()),
        content,
        flags=re.DOTALL,
    )
    return content

def _is_likely_backend_ts(filepath: str, content: str) -> bool:
    """Heuristic: is this a backend TypeScript file?

    Checks file path segments and import declarations to determine
    if the file is likely a Node/Express/Nest/Fastify backend file.
    Returns False for Vue/React frontend files.
    """
    lower_path = filepath.lower().replace("\\", "/")

    # Path hints
    if any(f"/{hint}/" in f"/{lower_path}/" or lower_path.endswith(f"/{hint}")
           for hint in _BACKEND_PATH_HINTS):
        return True

    # Specific filenames
    basename = lower_path.rsplit("/", 1)[-1] if "/" in lower_path else lower_path
    if basename in ("app.ts", "server.ts", "index.ts", "main.ts"):
        # Check content for backend imports to avoid false positive
        lower_content = content.lower()
        return any(
            f"from '{imp}" in lower_content
            or f"from \"{imp}" in lower_content
            or f"require('{imp}" in lower_content
            or f"require(\"{imp}" in lower_content
            for imp in _BACKEND_IMPORTS
        )

    # Content-only detection: backend imports present
    lower_content = content.lower()
    return any(
        f"from '{imp}" in lower_content
        or f"from \"{imp}" in lower_content
        or f"require('{imp}" in lower_content
        or f"require(\"{imp}" in lower_content
        for imp in _BACKEND_IMPORTS
    )


def _extract_backend_ts_patterns(
    filepath: str, content: str, lines: List[str],
) -> List[PatternMatch]:
    """Extract backend-specific patterns from a Node/Express TS file.

    Returns PatternMatch objects with kinds:
      - "auth_boundary": auth middleware registration
      - "authorization_check": req.user access for authorization
      - "route_handler": Express route definitions
      - "security_config": CORS, cookie, JWT configuration
      - "user_controlled_privilege": req.body.role, req.body.isAdmin
      - "tenant_scope": req.user.tenantId, req.user.orgId
    """
    # Strip comments to avoid false matches on commented-out code
    stripped = _strip_ts_comments(content)
    patterns: List[PatternMatch] = []

    # --- 1. Auth middleware ---
    for m in _EXPRESS_MIDDLEWARE_RE.finditer(stripped):
        line_num = _line_number(stripped, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="auth_boundary",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 2. Route handlers ---
    for m in _EXPRESS_ROUTE_RE.finditer(stripped):
        line_num = _line_number(stripped, m.start())
        method = m.group(1).upper()
        path = m.group(2)
        patterns.append(PatternMatch(
            file=filepath,
            pattern=f"{method} {path}",
            kind="route_handler",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 3. req.user access (authorization evidence) ---
    for m in _REQ_USER_RE.finditer(stripped):
        line_num = _line_number(stripped, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="authorization_check",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 4. CORS config ---
    for m in _CORS_CONFIG_RE.finditer(stripped):
        line_num = _line_number(stripped, m.start())
        # Normalize whitespace for pattern comparison
        config_text = re.sub(r"\s+", " ", m.group(0)).strip()
        patterns.append(PatternMatch(
            file=filepath,
            pattern=config_text,
            kind="security_config",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 5. Cookie config ---
    for m in _COOKIE_CONFIG_RE.finditer(stripped):
        line_num = _line_number(stripped, m.start())
        config_text = re.sub(r"\s+", " ", m.group(0)).strip()
        patterns.append(PatternMatch(
            file=filepath,
            pattern=config_text,
            kind="security_config",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 6. JWT verify ---
    for m in _JWT_VERIFY_RE.finditer(stripped):
        line_num = _line_number(stripped, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="auth_boundary",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 7. User-controlled privilege (DANGEROUS) ---
    for m in _EXPRESS_USER_PRIVILEGE_RE.finditer(stripped):
        line_num = _line_number(stripped, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="user_controlled_privilege",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    # --- 8. Tenant scope ---
    for m in _EXPRESS_TENANT_SCOPE_RE.finditer(stripped):
        line_num = _line_number(stripped, m.start())
        patterns.append(PatternMatch(
            file=filepath,
            pattern=m.group(0).strip(),
            kind="tenant_scope",
            line_number=line_num,
            context=_context_line(lines, line_num),
        ))

    return patterns


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


def _route_context_for_meta(content: str, meta_start: int) -> str:
    """Return the enclosing route object fragment for a meta field.

    This is intentionally lightweight regex/string parsing. Router configs in
    the target apps are object-literal based; for complex dynamic route
    generation we still emit the meta fact, just with less route context.
    """
    object_start = content.rfind("{", 0, meta_start)
    if object_start < 0:
        line_start = content.rfind("\n", 0, meta_start) + 1
        line_end = content.find("\n", meta_start)
        return content[line_start:line_end if line_end >= 0 else len(content)].strip()

    depth = 0
    object_end = len(content)
    for idx in range(object_start, len(content)):
        char = content[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                object_end = idx + 1
                break

    return re.sub(r"\s+", " ", content[object_start:object_end]).strip()


def _route_context_bits(route_context: str) -> List[str]:
    """Extract path/name/component/title summaries from a route object."""
    bits: List[str] = []
    seen: set[str] = set()

    for match in _ROUTE_FIELD_STRING_RE.finditer(route_context):
        key = match.group(1).lower()
        value = match.group(2)
        if key not in seen:
            bits.append(f"{key}='{value}'")
            seen.add(key)

    component_match = _ROUTE_COMPONENT_RE.search(route_context)
    if component_match:
        bits.append(f"component={component_match.group(1)}")

    return bits


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
