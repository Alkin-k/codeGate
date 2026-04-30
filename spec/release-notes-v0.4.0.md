# CodeGate v0.4.0 Release Notes

CodeGate v0.4.0 moves the project from frontend/client route security into backend/API security governance.

v0.3 proved that CodeGate can distinguish a safe, scoped guest-mode implementation from an unsafe protected-route exposure. v0.4 applies the same baseline-aware approach to backend changes where AI coding agents often create silent security drift: removed auth decorators, weakened admin/owner checks, removed tenant filters, trusted request roles, and relaxed CORS/cookie settings.

## Highlights

- Added backend/API security gate rules SEC-6 through SEC-10.
- Added Python/FastAPI security extraction.
- Expanded Java/Spring extraction for security annotations and tenant-scope patterns.
- Expanded TypeScript extraction with backend-mode heuristics for Express/Nest/Fastify/Hono-style APIs.
- Added a public zero-LLM backend security demo fixture covering T7-T12.
- Hardened benchmark credibility by asserting expected SEC rule triggers, not just final decisions.
- Preserved v0.3 frontend security demo behavior.

## New Security Rules

| Rule | Description |
|------|-------------|
| SEC-6 | Detect backend auth boundary deletion |
| SEC-7 | Detect authorization weakening or always-allow replacement |
| SEC-8 | Detect tenant/org/account scope filter removal |
| SEC-9 | Detect trust in user-provided role/admin authority |
| SEC-10 | Detect CORS, cookie, CSRF, or session security relaxation |

## Reproduce

```bash
.venv/bin/python -m pytest -q
.venv/bin/python benchmarks/fixtures/security_gate_demo/run_demo.py
.venv/bin/python benchmarks/fixtures/backend_security_demo/run_demo.py
```

Expected local verification:

```text
201 passed
Frontend demo: T5 approve, T6 revise_code
Backend demo: T7-T12 PASS
```

## Compatibility

There are no intended CLI breaking changes in v0.4.0.

The v0.3 breaking change still applies: external scripts that call `apply_policy_override()` after `run_governance_pipeline()` should remove that extra call because policy checks now run inside the workflow loop.

## Scope and Limits

v0.4.0 is still alpha. The backend security gate is designed for deterministic governance of common AI-coding drift patterns, not as a replacement for SAST, DAST, dependency scanning, or manual security review.

The recommended operating model is:

- Deletion of known auth/tenant/security boundaries: violation.
- Introduction of always-allow authorization: violation.
- Ambiguous complex authorization rewrites: warning unless the removed boundary can be proven.
- Fixture-level proof first, real-executor smoke before public release.

## Related Docs

- `spec/benchmark-v4-backend-security-gate-report.md`
- `docs/backend-security-gate-design.md`
- `benchmarks/fixtures/backend_security_demo/run_demo.py`
