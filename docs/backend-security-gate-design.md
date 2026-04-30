# Backend Security Gate Design

## Purpose

The backend security gate catches high-risk silent behavioral drift in API/server code generated or modified by AI coding agents.

The core question is narrow:

> Did this change remove or weaken a security invariant that existed in the baseline?

This keeps the gate different from a general-purpose scanner. It does not try to find every possible vulnerability in a codebase. It compares the baseline and candidate implementation, extracts security-relevant facts, then applies deterministic policy rules.

## Design Principles

1. Extractors collect facts; policy rules make decisions.
2. Baseline-aware deletion is stronger evidence than single-snapshot suspicion.
3. Known boundary deletion is a violation.
4. Ambiguous authorization rewrites should be warnings unless a boundary is clearly removed or replaced with always-allow behavior.
5. Public benchmarks must assert the intended SEC rule, not only the final decision.

## Rule Model

| Rule | Pattern | Decision Bias |
|------|---------|---------------|
| SEC-6 | Auth decorator/annotation/middleware deleted | Violation |
| SEC-7 | Role, owner, or admin check deleted or replaced with always-allow | Violation; ambiguous weakening as warning |
| SEC-8 | Tenant/org/account scope filter deleted | Violation |
| SEC-9 | Request-supplied role/admin trusted as authority | Violation |
| SEC-10 | Security config relaxed | Violation |

## Language Coverage

### Python/FastAPI

The Python extractor focuses on:

- dependency-based auth boundaries such as `Depends(get_current_user)`
- decorators and helper calls that indicate auth/authz checks
- tenant/org/account filters
- request-body/query/header role trust
- CORS and cookie/session security options

### Java/Spring

The Java path extends the baseline diff extractor for:

- `@PreAuthorize`, `@Secured`, `@RolesAllowed`, `@PermitAll`, and related annotations
- tenant-scoped repository/query names
- principal/user/tenant helper usage

Comments are stripped before security extraction so removed code cannot be accidentally preserved as evidence through explanatory comments.

### TypeScript Backend

The TypeScript extractor uses backend-mode heuristics because `.ts` files can be frontend or backend:

- backend paths such as `server/`, `api/`, `routes/`, and `controllers/`
- imports or symbols associated with Express, Nest, Fastify, or Hono
- route handlers, middleware, request authority reads, tenant filters, and security config

## Benchmark Fixture

The public backend fixture lives at:

```text
benchmarks/fixtures/backend_security_demo/
```

It covers:

- T7 auth preserved
- T8 auth removed
- T9 tenant scope preserved
- T10 tenant scope removed
- T11 user-provided role trusted
- T12 security config relaxed

The demo is zero-LLM by design. It should run on a fresh clone without API keys and validate both:

- expected final decision
- expected SEC rule trigger

## Why Not a Separate Backend Extractor

v0.4 keeps backend extraction close to the existing language extractors:

- Java patterns already live in `baseline_diff.py`.
- Python gets a dedicated structural extractor because one did not exist before.
- TypeScript adds backend routing inside the existing extractor because frontend/backend cannot be separated by extension alone.

This keeps the current architecture small while still allowing a future `backend.py` facade if rule volume grows.

## Known Limits

- Regex and structural heuristics cannot reliably prove every semantic authorization rewrite.
- Framework coverage is intentionally incomplete.
- Fixture success does not prove real executor robustness.
- Always-allow and deletion patterns are high-confidence; complex conditional changes should stay advisory unless corroborated.

## Release Gate

Before releasing v0.4.0, verify:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python benchmarks/fixtures/security_gate_demo/run_demo.py
.venv/bin/python benchmarks/fixtures/backend_security_demo/run_demo.py
```

For release confidence, also run one Codex or Gemini executor smoke in a disposable project copy.
