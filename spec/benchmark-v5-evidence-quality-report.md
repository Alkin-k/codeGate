# Benchmark Report v5: Evidence Quality & Safe Refactoring

**Date:** May 2, 2026  
**Version:** CodeGate v0.5.0  
**Focus:** Evidence Explainability and False Positive Reduction

## Summary

CodeGate v0.5.0 significantly improves the explainability of security decisions by providing structured evidence (file, line, snippet) for all rule triggers. It also introduces a "Safe Refactoring Suite" to ensure that security-equivalent code changes (e.g., renaming a dependency) do not trigger false violations.

## Milestone 1: Evidence Explainability

Representative security triggers for rules SEC-1 through SEC-10 now produce structured evidence.

### Accuracy Validation
- **Baseline Coverage:** Representative removed patterns are captured with file/line precision in tests.
- **Candidate Coverage:** Representative added patterns are captured with snippet context in tests.
- **Traceability:** Developers can now trace "escalate_to_human" and "revise_code" decisions to specific code locations in the baseline or candidate.

## Milestone 2: Safe Refactoring Suite

We validated CodeGate against 4 common refactoring scenarios that often trigger false positives in simple diff-based tools. T13-T16 verify that common extractor-visible refactors remain non-blocking and produce advisory evidence rather than violations.

| Scenario | Refactor Type | Result | Evidence |
|---|---|---|---|
| T13 | Auth boundary rename | **Approve (Advisory)** | baseline `get_current_user` → candidate `get_authenticated_user` |
| T14 | Tenant scope rename | **Approve (Advisory)** | baseline `get_tenant` → candidate `get_org_context` |
| T15 | Admin check rename | **Approve (Advisory)** | baseline `require_admin` → candidate `require_admin_role` |
| T16 | Config to Env | **Approve (Advisory)** | baseline `CORS_ORIGINS = [...]` → candidate `ALLOWED_ORIGINS = os.getenv(...)` |

### Conclusion
CodeGate identifies these changes as "modifications" (refactored/changed) rather than "deletions" because:
1. The language-aware extractors recognize the new patterns.
2. The policy engine sees both a removal and a re-addition of the same "kind" of security pattern.

## Milestone 3: Public CI Demo

Implemented locally; GitHub hosted result requires push. Verified `.github/workflows/ci.yml` runs all synthetic tests and demo scripts.
