"""TypeScript / Vue structural extractor tests.

Validates that the TS/Vue extractor correctly identifies:
  - router.beforeEach guard presence
  - Auth conditions (getToken, !token, isPublic, isGuestMode)
  - Route meta definitions (meta.guest, meta.public)
  - localStorage/sessionStorage operations
  - Import declarations
  - Vue SFC <script> extraction
  - Guard body condition extraction
"""

from __future__ import annotations

from codegate.analysis.structural_extractors.typescript import (
    _extract_script_content,
    extract_typescript_patterns,
)

# ---------------------------------------------------------------------------
# Fixtures: realistic code snippets
# ---------------------------------------------------------------------------

ROUTER_TS_BASELINE = '''
import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/platform/auth-storage'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/workspace', name: 'workspace', component: WorkspaceView },
  { path: '/membership', name: 'membership', component: MembershipView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = getToken()
  const isPublic = to.meta?.public

  if (isPublic) {
    return next()
  }

  if (!token) {
    return next({ name: 'login' })
  }

  next()
})

export default router
'''

ROUTER_TS_T5_SCOPED_GUEST = '''
import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/platform/auth-storage'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/workspace', name: 'workspace', component: WorkspaceView, meta: { guest: true } },
  { path: '/membership', name: 'membership', component: MembershipView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = getToken()
  const isPublic = to.meta?.public

  if (isPublic || to.meta?.guest) {
    return next()
  }

  if (!token) {
    return next({ name: 'login' })
  }

  next()
})

export default router
'''

ROUTER_TS_T6_GLOBAL_BYPASS = '''
import { createRouter, createWebHistory } from 'vue-router'
import { getToken, isGuestMode } from '@/platform/auth-storage'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/workspace', name: 'workspace', component: WorkspaceView },
  { path: '/membership', name: 'membership', component: MembershipView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = getToken()
  const isPublic = to.meta?.public
  const guest = isGuestMode()

  if (isPublic) {
    return next()
  }

  if (!token && !guest) {
    return next({ name: 'login' })
  }

  next()
})

export default router
'''

ROUTER_TS_PUBLIC_WORKSPACE = '''
import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/platform/auth-storage'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  {
    path: '/workspace',
    name: 'workspace',
    component: WorkspaceView,
    meta: { title: '写作工作台', icon: 'Edit', public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = getToken()
  const isPublic = to.meta?.public

  if (!isPublic && !token) {
    return next({ name: 'login' })
  }

  next()
})
'''

AUTH_STORAGE_BASELINE = '''
const TOKEN_KEY = 'access_token'

export function getToken(): string | null {
  return localStorage.getItem('access_token')
}

export function setToken(token: string): void {
  localStorage.setItem('access_token', token)
}

export function removeToken(): void {
  localStorage.removeItem('access_token')
}
'''

AUTH_STORAGE_T6_GUEST = '''
const TOKEN_KEY = 'access_token'
const GUEST_KEY = 'guest_mode'

export function getToken(): string | null {
  return localStorage.getItem('access_token')
}

export function setToken(token: string): void {
  localStorage.setItem('access_token', token)
}

export function removeToken(): void {
  localStorage.removeItem('access_token')
}

export function isGuestMode(): boolean {
  return localStorage.getItem('guest_mode') === 'true'
}

export function setGuestMode(value: boolean): void {
  localStorage.setItem('guest_mode', String(value))
}
'''

VUE_SFC = '''
<template>
  <div class="login-view">
    <button @click="handleLogin">Login</button>
    <button @click="handleGuest">Guest Access</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { setGuestMode } from '@/platform/auth-storage'

const router = useRouter()
const loading = ref(false)

function handleGuest() {
  setGuestMode(true)
  router.push({ name: 'workspace' })
}
</script>

<style scoped>
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
'''


# ---------------------------------------------------------------------------
# Tests: Pattern extraction
# ---------------------------------------------------------------------------


class TestRouterGuardExtraction:
    """Test router.beforeEach guard detection."""

    def test_extracts_router_guard(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_BASELINE)
        guards = [p for p in patterns if p.kind == "router_guard"]
        assert len(guards) >= 1
        assert "router.beforeEach" in guards[0].pattern

    def test_guard_params_captured(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_BASELINE)
        guards = [p for p in patterns if p.kind == "router_guard"]
        assert any("to" in g.pattern for g in guards)


class TestAuthConditionExtraction:
    """Test auth condition detection (token, isPublic, guest)."""

    def test_extracts_token_condition(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_BASELINE)
        auth = [p for p in patterns if p.kind == "auth_condition"]
        auth_texts = [p.pattern.lower() for p in auth]
        assert any("token" in t for t in auth_texts)

    def test_extracts_ispublic_condition(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_BASELINE)
        auth = [p for p in patterns if p.kind == "auth_condition"]
        auth_texts = [p.pattern.lower() for p in auth]
        assert any("ispublic" in t or "public" in t for t in auth_texts)

    def test_extracts_guest_condition_in_t6(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_T6_GLOBAL_BYPASS)
        auth = [p for p in patterns if p.kind == "auth_condition"]
        auth_texts = [p.pattern.lower() for p in auth]
        assert any("guest" in t for t in auth_texts), \
            f"Expected guest condition, got: {auth_texts}"

    def test_extracts_gettoken_call(self) -> None:
        """getToken() appears as assignment `const token = getToken()`.
        The extractor captures `token` as auth_condition (the condition variable)
        and `getToken` via the import declaration."""
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_BASELINE)
        auth = [p for p in patterns if p.kind == "auth_condition"]
        auth_texts = [p.pattern.lower() for p in auth]
        # The variable 'token' used in conditions is captured
        assert any("token" in t for t in auth_texts)
        # getToken is captured via import
        imports = [p for p in patterns if p.kind == "import"]
        import_texts = [p.pattern.lower() for p in imports]
        assert any("gettoken" in t for t in import_texts)


class TestRouteMetaExtraction:
    """Test route meta definition detection."""

    def test_extracts_public_meta(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_BASELINE)
        meta = [p for p in patterns if p.kind == "route_meta"]
        assert len(meta) >= 1
        assert any("public" in m.pattern.lower() for m in meta)

    def test_extracts_guest_meta_in_t5(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_T5_SCOPED_GUEST)
        meta = [p for p in patterns if p.kind == "route_meta"]
        assert any("guest" in m.pattern.lower() for m in meta), \
            f"Expected guest meta, got: {[m.pattern for m in meta]}"

    def test_route_meta_includes_route_context(self) -> None:
        patterns = extract_typescript_patterns(
            "src/router/index.ts",
            ROUTER_TS_PUBLIC_WORKSPACE,
        )
        meta = [p for p in patterns if p.kind == "route_meta"]
        workspace_meta = [
            p for p in meta
            if "workspace" in p.pattern.lower() or "工作台" in p.pattern
        ]
        assert workspace_meta, f"Expected workspace route context, got: {[p.pattern for p in meta]}"
        assert any("public: true" in p.pattern for p in workspace_meta)


class TestStorageAccessExtraction:
    """Test localStorage/sessionStorage operation detection."""

    def test_extracts_storage_getitem(self) -> None:
        patterns = extract_typescript_patterns(
            "src/platform/auth-storage.ts",
            AUTH_STORAGE_BASELINE,
        )
        storage = [p for p in patterns if p.kind == "storage_access"]
        assert len(storage) >= 1
        assert any("access_token" in s.pattern for s in storage)

    def test_extracts_guest_storage_in_t6(self) -> None:
        patterns = extract_typescript_patterns(
            "src/platform/auth-storage.ts",
            AUTH_STORAGE_T6_GUEST,
        )
        storage = [p for p in patterns if p.kind == "storage_access"]
        guest_storage = [s for s in storage if "guest" in s.pattern.lower()]
        assert len(guest_storage) >= 1, \
            f"Expected guest storage access, got: {[s.pattern for s in storage]}"


class TestImportExtraction:
    """Test import declaration detection."""

    def test_extracts_imports(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_BASELINE)
        imports = [p for p in patterns if p.kind == "import"]
        assert len(imports) >= 2
        sources = [p.pattern for p in imports]
        assert any("vue-router" in s for s in sources)
        assert any("auth-storage" in s for s in sources)

    def test_detects_new_import_in_t6(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_T6_GLOBAL_BYPASS)
        imports = [p for p in patterns if p.kind == "import"]
        imported_names = " ".join(p.pattern for p in imports)
        assert "isGuestMode" in imported_names, \
            f"Expected isGuestMode import, got: {imported_names}"


class TestVueSFCExtraction:
    """Test Vue Single File Component handling."""

    def test_extracts_from_script_block(self) -> None:
        patterns = extract_typescript_patterns("src/views/login/LoginView.vue", VUE_SFC)
        imports = [p for p in patterns if p.kind == "import"]
        assert len(imports) >= 1

    def test_does_not_extract_css_as_patterns(self) -> None:
        """@keyframes should NOT be extracted as a decorator/pattern."""
        patterns = extract_typescript_patterns("src/views/login/LoginView.vue", VUE_SFC)
        # Should not have decorators for CSS pseudo-patterns
        css_patterns = [
            p for p in patterns
            if "keyframes" in p.pattern.lower() and p.kind == "decorator"
        ]
        assert len(css_patterns) == 0, \
            f"CSS @keyframes incorrectly extracted: {css_patterns}"

    def test_script_content_extraction(self) -> None:
        script = _extract_script_content(VUE_SFC)
        assert "import { ref }" in script
        assert "@keyframes" not in script


class TestGuardConditionExtraction:
    """Test guard body condition detection for policy analysis."""

    def test_extracts_guard_conditions_baseline(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_BASELINE)
        guard_conds = [p for p in patterns if p.kind == "guard_condition"]
        # Should find: isPublic check, !token check
        cond_texts = [p.pattern.lower() for p in guard_conds]
        assert any("ispublic" in t or "public" in t for t in cond_texts) or \
               any("token" in t for t in cond_texts), \
            f"Expected auth guard conditions, got: {cond_texts}"

    def test_extracts_guard_conditions_t6(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ROUTER_TS_T6_GLOBAL_BYPASS)
        guard_conds = [p for p in patterns if p.kind == "guard_condition"]
        cond_texts = [p.pattern.lower() for p in guard_conds]
        # T6 guard has: if (!token && !guest) — should be captured
        assert any("guest" in t for t in cond_texts), \
            f"Expected guest in guard conditions, got: {cond_texts}"


# ---------------------------------------------------------------------------
# Tests: Diff-level integration (pattern comparison)
# ---------------------------------------------------------------------------


class TestBaselineDiffIntegration:
    """Test that baseline diff correctly identifies changes between T5/T6 variants."""

    def test_diff_detects_guest_meta_added_in_t5(self) -> None:
        from codegate.analysis.baseline_diff import compute_baseline_diff

        baseline = {"src/router/index.ts": ROUTER_TS_BASELINE}
        current = {"src/router/index.ts": ROUTER_TS_T5_SCOPED_GUEST}

        diff = compute_baseline_diff(baseline, current)

        added_kinds = [p.kind for p in diff.added_not_in_baseline]
        added_patterns = [p.pattern.lower() for p in diff.added_not_in_baseline]

        # T5 adds route_meta with guest
        assert "route_meta" in added_kinds, \
            f"Expected route_meta added, got kinds: {added_kinds}"
        assert any("guest" in p for p in added_patterns), \
            f"Expected guest in added patterns: {added_patterns}"

    def test_diff_detects_guest_auth_added_in_t6(self) -> None:
        from codegate.analysis.baseline_diff import compute_baseline_diff

        baseline = {"src/router/index.ts": ROUTER_TS_BASELINE}
        current = {"src/router/index.ts": ROUTER_TS_T6_GLOBAL_BYPASS}

        diff = compute_baseline_diff(baseline, current)

        added_patterns = [p.pattern.lower() for p in diff.added_not_in_baseline]

        # T6 adds guest-related auth conditions and imports
        has_guest_addition = any("guest" in p for p in added_patterns)
        assert has_guest_addition, \
            f"Expected guest-related additions, got: {added_patterns}"

    def test_diff_t6_storage_changes(self) -> None:
        from codegate.analysis.baseline_diff import compute_baseline_diff

        baseline = {"src/platform/auth-storage.ts": AUTH_STORAGE_BASELINE}
        current = {"src/platform/auth-storage.ts": AUTH_STORAGE_T6_GUEST}

        diff = compute_baseline_diff(baseline, current)

        added_patterns = [p.pattern.lower() for p in diff.added_not_in_baseline]

        # T6 adds guest_mode storage access
        assert any("guest" in p for p in added_patterns), \
            f"Expected guest storage added, got: {added_patterns}"


# ---------------------------------------------------------------------------
# Tests: Real-world guard pattern variants (Step 2)
# ---------------------------------------------------------------------------


ASYNC_GUARD = '''
router.beforeEach(async (to) => {
  const token = await getToken()
  if (!token) {
    return { name: 'Login' }
  }
})
'''

TERNARY_GUARD = '''
router.beforeEach((to, from, next) => {
  const isPublic = to.meta?.public
  !isPublic && !getToken() ? next('/login') : next()
})
'''

COMBINED_OR_GUARD = '''
router.beforeEach((to, from, next) => {
  const token = getToken()
  if (!isPublic && (!token || guest)) {
    return next({ name: 'login' })
  }
  next()
})
'''

RETURN_OBJECT_GUARD = '''
router.beforeEach(async (to) => {
  const token = getToken()
  const isPublic = to.meta?.public
  if (!isPublic && !token) {
    return { name: 'Login' }
  }
})
'''


class TestGuardVariants:
    """Test extraction of real-world guard pattern variants.

    Covers:
      - async (to) => { ... }
      - ternary condition ? redirect : next()
      - Combined OR: (!token || guest)
      - Return-object style: return { name: 'Login' }
    """

    def test_async_guard_detected(self) -> None:
        """router.beforeEach(async (to) => { ... }) should be detected."""
        patterns = extract_typescript_patterns("src/router/index.ts", ASYNC_GUARD)
        guards = [p for p in patterns if p.kind == "router_guard"]
        assert len(guards) >= 1, f"Async guard not detected, got: {[p.kind for p in patterns]}"
        assert "to" in guards[0].pattern

    def test_async_guard_conditions_extracted(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ASYNC_GUARD)
        auth = [p for p in patterns if p.kind == "auth_condition"]
        auth_texts = [p.pattern.lower() for p in auth]
        assert any("token" in t for t in auth_texts), \
            f"Expected token condition in async guard, got: {auth_texts}"

    def test_async_guard_body_condition_extracted(self) -> None:
        patterns = extract_typescript_patterns("src/router/index.ts", ASYNC_GUARD)
        guard_conds = [p for p in patterns if p.kind == "guard_condition"]
        cond_texts = [p.pattern.lower() for p in guard_conds]
        assert any("token" in t for t in cond_texts), \
            f"Expected !token in guard conditions, got: {cond_texts}"

    def test_combined_or_guest_detected(self) -> None:
        """if (!isPublic && (!token || guest)) should capture guest."""
        patterns = extract_typescript_patterns("src/router/index.ts", COMBINED_OR_GUARD)
        auth = [p for p in patterns if p.kind == "auth_condition"]
        auth_texts = [p.pattern.lower() for p in auth]
        assert any("guest" in t for t in auth_texts), \
            f"Expected guest in OR condition, got: {auth_texts}"

    def test_return_object_guard_detected(self) -> None:
        """return { name: 'Login' } style should still detect guard and conditions."""
        patterns = extract_typescript_patterns("src/router/index.ts", RETURN_OBJECT_GUARD)
        guards = [p for p in patterns if p.kind == "router_guard"]
        assert len(guards) >= 1
        auth = [p for p in patterns if p.kind == "auth_condition"]
        auth_texts = [p.pattern.lower() for p in auth]
        assert any("token" in t for t in auth_texts)
