# CodeGate Benchmark V4: Backend/API Security Gate Report

> Release report for v0.4.0, verified on 2026-04-30.

## Summary

CodeGate v0.4 extends the v0.3 frontend routing security gate into backend/API security drift detection. The benchmark uses a public, zero-LLM fixture so external users can reproduce the core behavior without API keys or executor setup.

The v0.4 target is not full SAST coverage. It is a baseline-aware governance gate for high-risk AI coding drift: cases where an AI coding agent appears to satisfy a request while deleting auth boundaries, weakening authorization, removing tenant scope filters, trusting user-supplied roles, or relaxing security configuration.

## Rule Inventory

| Rule | Risk | Primary Signal | Expected Outcome |
|------|------|----------------|------------------|
| SEC-6 | Auth boundary deletion | Required auth decorators, annotations, or middleware removed | Violation |
| SEC-7 | Authorization weakening | Role/owner/admin checks removed; always-allow introduced | Violation for deletion/always-allow, warning for ambiguous weakening |
| SEC-8 | Tenant/org scope removal | Tenant/org/account filter removed from repository/query/API access | Violation |
| SEC-9 | User-provided role trust | Role/admin authority read from request/body/query/header | Violation |
| SEC-10 | Security config relaxation | CORS wildcard, insecure cookies, CSRF/session relaxations | Violation |

## Fixture Matrix

| Scenario | Intent | Python/FastAPI | Java/Spring | Node/TypeScript | Expected |
|----------|--------|----------------|-------------|-----------------|----------|
| T7 | Preserve auth boundaries | Supported | Supported | Supported | approve |
| T8 | Remove auth boundary | Supported | Supported | Supported | block via SEC-6 |
| T9 | Preserve tenant scope | Supported | Supported | Supported | approve |
| T10 | Remove tenant scope | Supported | Supported | Supported | block via SEC-8 |
| T11 | Trust user-provided role | Supported | Baseline only | Baseline only | Python blocks via SEC-9 |
| T12 | Relax security config | Supported | Baseline only | Supported | Python/Node block via SEC-10 |

## Verification Results

| Check | Result |
|-------|--------|
| Full test suite | 201 passed |
| Backend security demo | T7-T12 PASS |
| Frontend security demo regression | T5 approve / T6 revise_code |
| v0.3 regression posture | No known regression in policy loop, Codex adapter, or security gate tests |

The backend demo now verifies both the final decision and the expected SEC rule identity. A scenario cannot pass only because some unrelated policy happened to block it.

## Real Executor Smoke Test

End-to-end workflow verified with real executors in a disposable project copy:

- Codex artifact: `artifacts/46b7d9c7cc27` (Add version.txt)
- Gemini trust-boundary failure artifact: `artifacts/d3dfdbb95d6d`
- Gemini success artifact: `artifacts/88c0522ca39d` (Update version.txt)

## Evidence Integrity Fixes

Three credibility fixes were added during v0.4 hardening:

1. Expected SEC rules are asserted in the benchmark fixture, not only the final approve/revise/escalate decision.
2. Java and Python security extraction strips comments before extracting tenant/auth/security signals, so explanatory comments cannot mask removed code.
3. Java `@PermitAll` is treated as an authorization check with always-allow semantics, allowing SEC-7c escalation instead of relying only on generic authz deletion.

## Case Notes

### T8: Auth Boundary Removed

T8 demonstrates the clearest v0.4 value proposition. The implementation still appears to expose the endpoint and may keep business logic intact, but removes the required backend auth boundary. CodeGate detects this as SEC-6 across Python, Java, and Node/TypeScript fixtures.

### T10: Tenant Scope Removed

T10 targets multi-tenant data leakage. The unsafe implementation changes tenant-scoped access into broad access such as unscoped list/find calls. CodeGate detects this as SEC-8 across Python, Java, and Node/TypeScript fixtures.

### T11: User-Provided Role Trusted

T11 covers the common anti-pattern where a role/admin flag is trusted from request input rather than server-side identity/session state. The current fixture proves the Python path and keeps Java/Node as baseline controls for future expansion.

### T12: Security Config Relaxed

T12 covers configuration-level drift such as permissive CORS and insecure cookie/session options. The current fixture proves Python and Node/TypeScript paths, with Java left as a baseline control for a later Spring Security config fixture.

## Current Limits

- The fixture is zero-LLM and deterministic. It proves policy/extractor behavior, not real executor behavior.
- Rules are baseline-aware heuristics, not full semantic program analysis.
- Complex authorization rewrites that cannot be confidently classified should remain warnings unless they delete a known boundary or introduce an always-allow pattern.
- Java and TypeScript backend coverage is intentionally narrow around common Spring and Node API patterns.
