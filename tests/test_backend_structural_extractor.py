"""Tests for backend security structural extractors.

Tests the v0.4 security pattern extraction for:
  - Java/Spring: @PreAuthorize, @Secured, @RolesAllowed, Principal, tenant queries, security config
  - Python/FastAPI: Depends(get_current_user), @login_required, tenant filters, user privilege
  - TypeScript/Express: auth middleware, req.user, CORS, cookie, JWT, tenant scope
"""

import pytest
from codegate.analysis.baseline_diff import _extract_patterns_regex_fallback, PatternMatch
from codegate.analysis.structural_extractors.python import extract_python_security_patterns
from codegate.analysis.structural_extractors.typescript import (
    extract_typescript_patterns,
    _is_likely_backend_ts,
)


# ===========================================================================
# Java Security Extractor Tests
# ===========================================================================


class TestJavaSecurityExtractor:
    """Test Java security pattern extraction in baseline_diff._extract_java_patterns."""

    def test_preauthorize_extracted(self):
        """@PreAuthorize → auth_boundary"""
        code = '''
@PreAuthorize("isAuthenticated()")
public ResponseEntity<User> getUser() { }
'''
        ps = _extract_patterns_regex_fallback("Controller.java", code)
        kinds = {p.kind for p in ps}
        auth_boundary = [p for p in ps if p.kind == "auth_boundary"]
        assert "auth_boundary" in kinds
        assert any("PreAuthorize" in p.pattern for p in auth_boundary)

    def test_secured_extracted(self):
        """@Secured → authorization_check"""
        code = '''
@Secured({"ROLE_ADMIN", "ROLE_OWNER"})
public ResponseEntity<User> deleteUser() { }
'''
        ps = _extract_patterns_regex_fallback("Controller.java", code)
        authz = [p for p in ps if p.kind == "authorization_check"]
        assert len(authz) >= 1
        assert any("Secured" in p.pattern for p in authz)

    def test_roles_allowed_extracted(self):
        """@RolesAllowed → authorization_check"""
        code = '''
@RolesAllowed({"ADMIN"})
public void adminAction() { }
'''
        ps = _extract_patterns_regex_fallback("Controller.java", code)
        authz = [p for p in ps if p.kind == "authorization_check"]
        assert len(authz) >= 1
        assert any("RolesAllowed" in p.pattern for p in authz)

    def test_tenant_repository_extracted(self):
        """findByTenantId → tenant_scope"""
        code = '''
public interface UserRepository extends JpaRepository<User, String> {
    List<User> findByTenantId(String tenantId);
    User findByIdAndTenantId(String id, String tenantId);
}
'''
        ps = _extract_patterns_regex_fallback("UserRepository.java", code)
        tenant = [p for p in ps if p.kind == "tenant_scope"]
        assert len(tenant) >= 2
        assert any("findByTenantId" in p.pattern for p in tenant)
        assert any("findByIdAndTenantId" in p.pattern for p in tenant)

    def test_principal_param_extracted(self):
        """Principal parameter → auth_boundary"""
        code = '''
public ResponseEntity<User> getUser(Principal principal) {
    String userId = principal.getName();
}
'''
        ps = _extract_patterns_regex_fallback("Controller.java", code)
        auth = [p for p in ps if p.kind == "auth_boundary"]
        assert any("Principal" in p.pattern for p in auth)

    def test_security_config_extracted(self):
        """.hasRole() → security_config"""
        code = '''
http
    .authorizeRequests()
    .antMatchers("/api/admin/**").hasRole("ADMIN")
    .antMatchers("/api/**").authenticated()
    .anyRequest().permitAll();
'''
        ps = _extract_patterns_regex_fallback("SecurityConfig.java", code)
        config = [p for p in ps if p.kind == "security_config"]
        assert len(config) >= 3

    def test_tenant_scope_in_comment_ignored(self):
        """Commented tenant-scope names should not mask real deletion."""
        code = '''
public ResponseEntity<Page<User>> listUsers(Pageable pageable) {
    // TENANT SCOPE REMOVED: was findByTenantId
    Page<User> users = userRepository.findAll(pageable);
    return ResponseEntity.ok(users);
}
'''
        ps = _extract_patterns_regex_fallback("Controller.java", code)
        tenant = [p for p in ps if p.kind == "tenant_scope"]
        assert tenant == []

    def test_permit_all_extracted_as_authorization_check(self):
        """@PermitAll should feed SEC-7 always-allow detection."""
        code = '''
@PermitAll
public ResponseEntity<User> adminAction() { }
'''
        ps = _extract_patterns_regex_fallback("Controller.java", code)
        authz = [p for p in ps if p.kind == "authorization_check"]
        assert any("@PermitAll" in p.pattern for p in authz)

    def test_existing_validation_unaffected(self):
        """@NotNull, @Valid still produce annotation kind"""
        code = '''
public ResponseEntity<User> create(@Valid @RequestBody User user) { }
'''
        ps = _extract_patterns_regex_fallback("Controller.java", code)
        annotations = [p for p in ps if p.kind == "annotation"]
        assert any("Valid" in p.pattern for p in annotations)
        assert any("RequestBody" in p.pattern for p in annotations)


# ===========================================================================
# Python Security Extractor Tests
# ===========================================================================


class TestPythonSecurityExtractor:
    """Test Python security pattern extraction."""

    def test_depends_current_user_extracted(self):
        """Depends(get_current_user) → auth_boundary"""
        code = '''
@app.get("/users")
async def list_users(user=Depends(get_current_user)):
    return users
'''
        ps = extract_python_security_patterns("app.py", code)
        auth = [p for p in ps if p.kind == "auth_boundary"]
        assert len(auth) >= 1
        assert any("get_current_user" in p.pattern for p in auth)

    def test_login_required_extracted(self):
        """@login_required → auth_boundary"""
        code = '''
@login_required
def dashboard(request):
    return render(request, 'dashboard.html')
'''
        ps = extract_python_security_patterns("views.py", code)
        auth = [p for p in ps if p.kind == "auth_boundary"]
        assert len(auth) >= 1
        assert any("login_required" in p.pattern for p in auth)

    def test_require_admin_extracted(self):
        """Depends(require_admin) → authorization_check"""
        code = '''
@app.delete("/users/{user_id}")
async def delete_user(admin=Depends(require_admin)):
    pass
'''
        ps = extract_python_security_patterns("app.py", code)
        authz = [p for p in ps if p.kind == "authorization_check"]
        assert len(authz) >= 1
        assert any("require_admin" in p.pattern for p in authz)

    def test_tenant_filter_extracted(self):
        """.filter(tenant_id=) → tenant_scope"""
        code = '''
users = User.objects.filter(tenant_id=request.user.tenant_id)
'''
        ps = extract_python_security_patterns("views.py", code)
        tenant = [p for p in ps if p.kind == "tenant_scope"]
        assert len(tenant) >= 1

    def test_user_privilege_from_body(self):
        """data['role'] → user_controlled_privilege"""
        code = '''
data = request.json
role = data['role']
is_admin = data['is_admin']
'''
        ps = extract_python_security_patterns("views.py", code)
        priv = [p for p in ps if p.kind == "user_controlled_privilege"]
        assert len(priv) >= 1

    def test_cors_config_extracted(self):
        """CORS_ORIGINS → security_config"""
        code = '''
CORS_ORIGINS = ["https://app.example.com"]
SESSION_COOKIE_SECURE = True
'''
        ps = extract_python_security_patterns("settings.py", code)
        config = [p for p in ps if p.kind == "security_config"]
        assert len(config) >= 2

    def test_permission_required_extracted(self):
        """@permission_required → authorization_check"""
        code = '''
@permission_required('admin')
def admin_view(request):
    pass
'''
        ps = extract_python_security_patterns("views.py", code)
        authz = [p for p in ps if p.kind == "authorization_check"]
        assert len(authz) >= 1


# ===========================================================================
# TypeScript/Express Backend Extractor Tests
# ===========================================================================


class TestExpressSecurityExtractor:
    """Test TypeScript backend pattern extraction."""

    def test_auth_middleware_extracted(self):
        """app.use(authMiddleware) → auth_boundary"""
        code = '''
import express from 'express';
const app = express();
app.use(authMiddleware);
'''
        ps = extract_typescript_patterns("server/app.ts", code)
        auth = [p for p in ps if p.kind == "auth_boundary"]
        assert len(auth) >= 1
        assert any("authMiddleware" in p.pattern for p in auth)

    def test_req_user_extracted(self):
        """req.user → authorization_check"""
        code = '''
import express from 'express';
app.get('/profile', (req, res) => {
    const userId = req.user.id;
    res.json({ userId });
});
'''
        ps = extract_typescript_patterns("server/routes.ts", code)
        authz = [p for p in ps if p.kind == "authorization_check"]
        assert len(authz) >= 1

    def test_cors_config_extracted(self):
        """cors({ origin: ... }) → security_config"""
        code = '''
import express from 'express';
import cors from 'cors';
app.use(cors({
  origin: 'https://app.example.com',
  credentials: true,
}));
'''
        ps = extract_typescript_patterns("server/app.ts", code)
        config = [p for p in ps if p.kind == "security_config"]
        assert len(config) >= 1

    def test_cookie_config_extracted(self):
        """cookie({ secure: true }) → security_config"""
        code = '''
import express from 'express';
app.use(session({
  secret: 'secret',
  cookie: { secure: true, httpOnly: true, sameSite: 'strict' }
}));
'''
        ps = extract_typescript_patterns("server/app.ts", code)
        config = [p for p in ps if p.kind == "security_config"]
        assert len(config) >= 1

    def test_frontend_patterns_unaffected(self):
        """router.beforeEach still works in frontend files"""
        code = '''
import { createRouter } from 'vue-router'
const router = createRouter({ routes })
router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth && !getToken()) {
    next('/login')
  }
})
'''
        ps = extract_typescript_patterns("src/router/index.ts", code)
        guards = [p for p in ps if p.kind == "router_guard"]
        assert len(guards) >= 1
        # Should NOT have backend patterns
        auth = [p for p in ps if p.kind == "auth_boundary"]
        assert len(auth) == 0  # No express imports → not backend

    def test_backend_detection_heuristic_path(self):
        """_is_likely_backend_ts detects by path"""
        assert _is_likely_backend_ts("server/app.ts", "const x = 1;")
        assert _is_likely_backend_ts("api/routes.ts", "const x = 1;")
        assert not _is_likely_backend_ts("src/components/App.ts", "const x = 1;")

    def test_backend_detection_heuristic_import(self):
        """_is_likely_backend_ts detects by import"""
        assert _is_likely_backend_ts("app.ts", "import express from 'express';")
        assert _is_likely_backend_ts("app.ts", "import { Hono } from 'hono';")
        assert not _is_likely_backend_ts("app.ts", "import { ref } from 'vue';")

    def test_jwt_verify_extracted(self):
        """jwt.verify → auth_boundary"""
        code = '''
import express from 'express';
import jwt from 'jsonwebtoken';
const decoded = jwt.verify(token, secret);
'''
        ps = extract_typescript_patterns("server/auth.ts", code)
        auth = [p for p in ps if p.kind == "auth_boundary"]
        assert any("jwt.verify" in p.pattern for p in auth)

    def test_user_privilege_extracted(self):
        """req.body.role → user_controlled_privilege"""
        code = '''
import express from 'express';
const role = req.body.role;
const isAdmin = req.body.isAdmin;
'''
        ps = extract_typescript_patterns("server/users.ts", code)
        priv = [p for p in ps if p.kind == "user_controlled_privilege"]
        assert len(priv) >= 1

    def test_tenant_scope_extracted(self):
        """req.user.tenantId → tenant_scope"""
        code = '''
import express from 'express';
const tenantId = req.user.tenantId;
'''
        ps = extract_typescript_patterns("server/users.ts", code)
        tenant = [p for p in ps if p.kind == "tenant_scope"]
        assert len(tenant) >= 1
