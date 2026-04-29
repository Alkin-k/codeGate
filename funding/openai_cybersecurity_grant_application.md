# OpenAI Cybersecurity Grant — CodeGate Application

## Project Title
**CodeGate: Deterministic Security Gate for AI-Generated Code**

## Category
Defensive AI Security — Automated governance and policy enforcement for AI coding agents

## Abstract

AI coding agents are increasingly used in production software development, but they introduce a new class of security risk: **silent behavioral drifts** that pass all existing tests. CodeGate addresses this by providing a deterministic security gate that sits between coding agents and code approval.

Unlike LLM-based code review (which is probabilistic), CodeGate's security rules are deterministic and auditable. The SEC-1~5 rule set detects authentication bypass, token deletion, unscoped guest access, and protected route exposure through structural code analysis — not pattern matching on raw text.

## Problem Statement

### The Threat Model

When AI coding agents modify authentication and authorization code, they may:

1. **Remove auth guards** — Delete `router.beforeEach` guards that enforce token validation
2. **Add global guest bypass** — Create `isGuestMode()` functions that skip authentication for all routes
3. **Weaken token checks** — Change `!token` to `!token && !guest`, adding bypass conditions
4. **Expose protected routes** — Set `meta: { public: true }` on routes that should require authentication
5. **Delete token logic** — Remove `getToken()` calls without replacement

These changes are often syntactically correct, pass type checking, and may not be caught by existing unit tests — especially in frontend code where auth logic is typically imperative (not declarative).

### Why This Matters

- AI agents generate code at speeds that exceed human review capacity
- Security vulnerabilities in auth/routing code are high-impact and low-visibility
- Existing static analysis tools don't understand the behavioral semantics of auth flows
- LLM-based code review can catch these issues but is non-deterministic — it might miss them

## Technical Approach

### Structural Extraction + Deterministic Rules

CodeGate uses a two-layer approach:

**Layer 1: Structural Extractors**
- Parse TypeScript/Vue/Rust source files to extract behavioral patterns:
  - `router_guard` — `router.beforeEach` definitions
  - `auth_condition` — Token/isPublic/guest conditions
  - `guard_condition` — Guard logic (early returns, redirects)
  - `route_meta` — Route metadata (public, guest, requireAuth)
  - `storage_access` — localStorage/sessionStorage operations

**Layer 2: Security Policy Rules (SEC-1~5)**
- **SEC-1**: Auth guard bypass detection (guard removed or weakened)
- **SEC-2**: Global guest flag (new guest storage keys)
- **SEC-3**: Unscoped guest access (guest condition without route meta check)
- **SEC-4**: Token logic deletion/weakening
- **SEC-5**: Protected route exposure (auth-gated pages made public)

Each rule produces:
- A violation or advisory classification
- Evidence (the specific pattern that triggered)
- An override decision (revise_code or escalate_to_human)

### Defense in Depth

CodeGate runs security rules AFTER an LLM-based reviewer. This means:
- If the LLM reviewer catches the issue → deterministic rule adds audit evidence
- If the LLM reviewer misses the issue → deterministic rule still catches it
- Either way, a machine-readable `policy_result.json` is produced for compliance

## Demonstrated Results

### T5/T6 Case Study

Same project, same "add guest mode" request, different constraints:

| | T5 (Constrained) | T6 (Unconstrained) |
|---|---|---|
| AI Implementation | `meta: { guest: true }` + scoped guard | `meta: { public: true }` on protected routes |
| SEC-3 | Advisory (scoped — safe) | Not triggered (different path) |
| SEC-5 | Not triggered | **2 violations** (protected route exposure) |
| Decision | ✅ Approve | ⚠️ Escalate to human |
| False positive? | No | No |

### Full Benchmark

- 6 scenarios, 0 false positives, 0 false negatives
- Security gate precision: 100%
- 122 unit/integration tests passing
- Reproducible via automated harness

## Requested Resources

| Resource | Purpose | Amount |
|----------|---------|--------|
| API credits | Continuous security testing across LLM providers | $200-500/month |
| Security research | Expand SEC rules to backend API, RBAC, JWT | $2,000-5,000 total |
| Benchmark infrastructure | Automated regression for security rules | Minimal |

## Impact

If funded, CodeGate will:
1. Expand security rules from frontend-only to full-stack (backend API guards, JWT validation, RBAC enforcement)
2. Publish a public benchmark for AI coding agent security governance
3. Provide an open-source tool that any team can integrate into their AI-assisted development workflow
4. Establish a framework for deterministic security policy enforcement that complements LLM-based review

## Open Source

- Repository: https://github.com/Alkin-k/codeGate
- License: Apache 2.0
- Benchmark reports, the reproducible harness, and security rules are publicly
  available; raw real-project run artifacts that contain code snapshots are kept
  out of git.
