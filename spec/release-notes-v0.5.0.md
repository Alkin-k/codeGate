# Release Notes v0.5.0

**Theme:** Evidence Quality & Safe Refactoring

CodeGate v0.5.0 focuses on making security decisions transparent and robust. We've added structured evidence to all security findings and introduced a suite to validate that common refactorings don't trigger false positives.

## New Features

### 1. Structured Security Evidence
Representative security rule triggers (covering SEC-1 ~ SEC-10 patterns) now include a detailed `evidence` block:
- **File & Line**: Exact location in the baseline and candidate code.
- **Pattern Match**: The specific code fragment that triggered the rule.
- **Snippet Context**: Surrounding code for quick manual verification.
- **Summary**: A human-readable one-liner explaining the drift.

### 2. Safe Refactoring Suite
CodeGate now distinguishes between **malicious deletions** and **common extractor-visible refactorings**.
- T13-T16 scenarios verify that renaming auth dependencies or moving security configs to environment variables remain non-blocking (`advisory`) rather than violations.
- Updated extractors for Python to support a wider range of security-equivalent naming patterns.

### 3. Public CI Integration
- Added `.github/workflows/ci.yml` for automated regression testing.
- Public backend security demo now covers 10 scenarios (T7-T16) including safe refactors.

## Improvements
- **Policy Engine**: Added `severity` and `reason` fields to all rule triggers for better downstream integration.
- **Extractors**: Enhanced FastAPI dependency detection regexes.
- **Documentation**: New `docs/security-evidence-schema.md` and updated benchmark reports.

## Breaking Changes
- None. `evidence` is a new field; `removed` and `added` fields are preserved for backward compatibility.
