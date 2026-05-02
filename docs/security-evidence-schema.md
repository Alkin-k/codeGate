# Security Evidence Schema (v0.5)

CodeGate v0.5 introduces structured evidence for all security policy rule triggers. This evidence provides clear proof of why a decision was made, where the relevant code is located, and how the implementation has drifted from the baseline.

## Evidence Field

Representative rule triggers in `policy_result.json` contain an `evidence` field with the following structure:

```json
{
  "baseline": [
    {
      "file": "app.py",
      "line": 45,
      "kind": "tenant_scope",
      "pattern": "Depends(get_tenant)",
      "snippet": "tenant = Depends(get_tenant)"
    }
  ],
  "candidate": [],
  "summary": "baseline app.py:45 Depends(get_tenant) → candidate none"
}
```

### Fields

- `baseline`: A list of evidence points from the original (git HEAD) code.
- `candidate`: A list of evidence points from the new code provided by the executor.
- `summary`: A human-readable one-line summary of the drift.

### Evidence Point Fields

- `file`: The relative path to the file.
- `line`: The 1-based line number.
- `kind`: The type of pattern (e.g., `auth_boundary`, `tenant_scope`, `security_config`).
- `pattern`: The specific code fragment that matched the rule.
- `snippet`: The surrounding code context for human readability.

## Supported Rules (SEC-1 ~ SEC-10)

All security rules now populate the `evidence` field.

| Rule | Meaning | Evidence Content |
|---|---|---|
| SEC-1 | Auth guard bypass | Guard or condition changes in router/middleware |
| SEC-2 | Global guest flag | New guest-related storage keys |
| SEC-3 | Unscoped guest access | Unscoped guest conditions in global guards |
| SEC-4 | Token logic deletion | Deletion or weakening of token checks |
| SEC-5 | Protected route exposed | Addition of `public: true` to sensitive routes |
| SEC-6 | Auth boundary removal | Removal of auth decorators/middleware |
| SEC-7 | Authorization check weakening | Removal of role/admin checks or addition of `permitAll` |
| SEC-8 | Tenant scope removal | Removal of tenant/org query filters |
| SEC-9 | User-controlled privilege | Usage of client-supplied roles/IDs in auth |
| SEC-10| Security config relaxation | Weakening of CORS/cookie/CSRF settings |

## Backward Compatibility

The following fields are preserved for backward compatibility with v0.4 tools and tests:

- `removed`: A flat list of patterns removed from the baseline.
- `added`: A flat list of patterns added to the candidate.
- `rule`, `case`, `severity`, `decision`, `reason`: Standard trigger metadata.
