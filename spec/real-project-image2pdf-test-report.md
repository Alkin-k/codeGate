# CodeGate Real Project Test Report - image2Pdf

> Date: 2026-04-24
> Project under test: `/Users/wukai/IdeaProjects/image2Pdf`
> Test workspace: `/tmp/codegate-real-image2pdf`
> CodeGate artifacts: `/Users/wukai/Desktop/腾讯云/codegate/real_project_results/fc62190aada9`

## 1. Objective

Validate whether CodeGate can govern a real repository with `OpenCodeAdapter`, instead of running benchmark cases in an empty sandbox.

The original project was not modified. A temporary copy was created under `/tmp/codegate-real-image2pdf`.

## 2. Project Fit

`image2Pdf` is suitable for the first real-project test:

- Small Java 17 + Spring Boot 3.3.4 Maven project.
- Clear API/controller/service structure.
- Existing `mvn test` baseline.
- Existing MockMvc tests.
- Low-risk feature requests can be scoped to 1-3 files.

Baseline verification:

- Command: `mvn test`
- Result: pass
- Tests: 9 passed, 0 failed

## 3. Test Request

Request:

```text
Add GET /api/capabilities to the existing Spring Boot project.
Return supportedInputs=[IMAGE, PDF], supportedOutputs=[PDF, IMAGE],
minDpi=72, maxDpi=600, defaultDpi=300, supportedImageFormats=[png, jpg].
Keep existing APIs compatible, add no new dependency, and add a MockMvc test.
```

Executor:

- `opencode`
- model: `kimi-for-coding/k2p6`
- project dir: `/tmp/codegate-real-image2pdf`

## 4. Result Summary

CodeGate completed the full governance loop successfully.

| Area | Result |
|------|--------|
| Spec Council | Generated and approved contract |
| OpenCode execution | Completed without timeout |
| Reviewer | 1 non-blocking finding |
| Gatekeeper | `approve` |
| Manual verification | `mvn test` passed |
| Original project safety | Original repo untouched |

Timing and token data:

| Phase | Tokens |
|-------|--------|
| spec_council | 2,287 |
| executor | 382,582 |
| reviewer | 78,029 |
| gatekeeper | 1,652 |
| total | 464,550 |

Execution time:

- OpenCode executor: `233.6s`
- Total observed CodeGate run: about `4m22s`

## 5. Actual Code Changes

Git status in the temporary project:

```text
 M src/main/java/com/wukai/image2pdf/api/ConvertController.java
 M src/test/java/com/wukai/image2pdf/api/ConvertControllerTest.java
?? src/main/java/com/wukai/image2pdf/api/CapabilitiesResponse.java
```

Functional changes:

- Added `CapabilitiesResponse` record.
- Added `GET /api/capabilities` in `ConvertController`.
- Added `shouldReturnCapabilities()` MockMvc test.

Post-run verification:

- Command: `mvn test`
- Result: pass
- Tests: 10 passed, 0 failed

## 6. Governance Assessment

The governance result is mostly healthy.

- `drift_score=0`
- `coverage_score=100`
- `decision=approve`
- `blocking_findings=0`

Reviewer produced one non-blocking `P1` finding:

```text
The response is wrapped in ApiResponse(code, data) instead of returning the
capabilities object directly.
```

This is acceptable because the prompt explicitly allowed `ApiResponse.success`, and it matches the existing API style. The finding is useful but should probably be `P2` rather than `P1`.

## 7. Issues Found In CodeGate

### 7.1 Evidence pollution from build outputs

OpenCode ran `mvn test`, which modified `target/`. `OpenCodeAdapter` collected `target/classes`, `target/test-classes`, Maven status files, and surefire reports into `ExecutionReport.files_content`.

Observed effect:

- Real source changes: 3 files.
- Execution report file list: 31 files.
- `execution_report.json`: about 580 KB.
- Reviewer tokens: 78,029.

This is now the most important optimization. CodeGate should use git-aware changed-file detection or ignore build artifacts.

Recommended fix:

- Prefer `git status --porcelain` for repositories.
- Exclude ignored files by default.
- Exclude common build output directories: `target/`, `build/`, `dist/`, `.gradle/`, `node_modules/`, `.idea/`.
- Keep a separate optional section for test reports instead of treating them as source changes.

### 7.2 Reviewer severity is slightly too strong

The reviewer marked the response-wrapper concern as `P1` even though the user explicitly allowed `ApiResponse.success`.

Recommended fix:

- Add prompt guidance: if an implementation follows an explicitly provided clarification answer, do not flag it as drift.
- If the contract wording and clarification differ, prefer the clarification answer as higher priority context.

### 7.3 Real project run is viable, but timeout budget must be realistic

This low-risk real-project request took about 234 seconds in OpenCode. That is acceptable for async governance, but too slow for interactive usage.

Recommended product framing:

- Treat OpenCode-backed real-project runs as async governance jobs.
- Keep low-risk tasks small.
- Use progress logging and partial evidence capture in future versions.

## 8. Conclusion

The real-project test validates the product direction better than the empty benchmark run.

Key conclusion:

```text
CodeGate + OpenCode can complete a real repository change end to end.
The main next bottleneck is not correctness; it is artifact hygiene and cost control.
```

Recommended next step:

1. Fix `OpenCodeAdapter` changed-file collection to ignore build outputs.
2. Re-run the same `image2Pdf` test.
3. Compare file count, reviewer token usage, and decision quality.
4. Then run a second real-project case with a slightly broader but still bounded change.

## 9. Retest After Artifact Filtering

After optimizing `OpenCodeAdapter` to prefer git-visible changes and ignore build outputs, the same real-project request was run again.

New artifact directory:

```text
/Users/wukai/Desktop/腾讯云/codegate/real_project_results/f44ce9583608
```

### 9.1 Comparison

| Metric | Before filtering | After filtering | Change |
|--------|------------------|-----------------|--------|
| Execution report files | 31 | 3 | build outputs removed |
| `execution_report.json` size | 580 KB | 8 KB | ~98.6% smaller |
| Reviewer tokens | 78,029 | 3,336 | ~95.7% lower |
| Non-executor governance tokens | 81,968 | 7,035 | ~91.4% lower |
| Total tokens | 464,550 | 421,216 | ~9.3% lower |
| Executor tokens | 382,582 | 414,181 | higher due to model/run variance |
| Executor time | 233.6s | 229.6s | roughly unchanged |
| Reviewer findings | 1 non-blocking | 0 | cleaner review input |
| Gate decision | approve | approve | unchanged |
| Manual `mvn test` | 10 passed | 10 passed | unchanged |

### 9.2 New File List

The optimized evidence contains only source/test changes:

```text
src/main/java/com/wukai/image2pdf/api/CapabilitiesController.java
src/main/java/com/wukai/image2pdf/api/CapabilitiesResponse.java
src/test/java/com/wukai/image2pdf/api/CapabilitiesControllerTest.java
```

### 9.3 Result

The optimization worked. Build outputs such as `target/classes`, `target/test-classes`, Maven status files, and surefire reports no longer enter `ExecutionReport.files_content`.

The biggest improvement is not total token usage, because executor tokens are controlled by OpenCode/model behavior. The meaningful improvement is governance evidence quality:

```text
Reviewer input became small, source-focused, and reviewable.
```

### 9.4 Remaining Observations

- `codegate run` still does not persist an empty `review_findings.json`; this is expected for the current CLI artifact path but differs from benchmark evidence behavior.
- OpenCode produced a slightly different implementation shape on the second run: it created a new `CapabilitiesController` and `CapabilitiesControllerTest` instead of editing `ConvertController`.
- The generated implementation still passed `mvn test`, and the gate decision remained healthy.

### 9.5 Next Recommendation

The next real-project test should use a bounded medium-risk change that modifies existing logic, not just adds a new endpoint. Good candidates:

- Add validation for invalid `dpi` and `imageFormat` inputs.
- Add a file-size limit with clear API error behavior.
- Add a small CLI improvement with tests.

This will test whether CodeGate catches regressions in existing behavior, not only whether it can approve additive changes.

## 10. Round 3: Modify Existing Logic — imageFormat Validation

### 10.1 Test Request

```text
为 /api/convert 增加 imageFormat 参数校验：
当 imageFormat 不为空时，只允许 png 或 jpg，大小写不敏感；
非法值返回现有错误响应格式（使用 ApiResponse 的错误格式），不进入转换流程；
补充 MockMvc 测试，确保 png/jpg/PNG/JPG 通过，gif 返回错误。
```

This test is more valuable than Round 1-2 because it **modifies an existing method** (`ConvertController.convert()`) rather than adding a new endpoint.

### 10.2 Clarification Questions

CodeGate asked 3 clarification questions before proceeding:

1. 空字符串是否视为非法值？→ 与缺失一样，不做校验
2. ApiResponse 的错误格式具体是什么？→ 参考现有 UNSUPPORTED_TYPE，用 INVALID_FORMAT
3. imageFormat 参数是查询参数还是请求体参数？→ 已经是 @RequestParam，不改位置

### 10.3 Result Summary

| Area | Result |
|------|--------|
| Spec Council | 2 goals, 3 criteria, 1 clarification round |
| OpenCode execution | 219.8s, 546K tokens |
| Files changed | **2 files only** (no build pollution) |
| Reviewer | **0 findings** |
| Gatekeeper | ✅ approve (drift=0, coverage=100) |
| Baseline tests | 9 passed |
| Post-change tests | **16 passed** (+7 new) |

### 10.4 Code Changes

```diff
 # ConvertController.java (+8 lines)
+if (imageFormat != null && !imageFormat.isEmpty()) {
+    String normalizedFormat = imageFormat.toLowerCase(java.util.Locale.ROOT);
+    if (!"png".equals(normalizedFormat) && !"jpg".equals(normalizedFormat)) {
+        throw new IllegalArgumentException(
+            "Invalid imageFormat: " + imageFormat);
+    }
+}
```

7 new tests: `png` ✓, `jpg` ✓, `PNG` ✓, `JPG` ✓, `gif` → 400, `""` → pass, `null` → pass.

### 10.5 Key Findings

1. **No regression**: All 9 original tests still pass.
2. **Precise scope**: Only 2 files modified, no pom.xml touched.
3. **Clarification-driven**: 3 questions prevented edge-case ambiguity.
4. **Clean evidence**: Only source files in artifact (2 files, not 31).

### 10.6 Comparison Across 3 Rounds

| Dimension | Round 1 (add endpoint) | Round 2 (retest) | Round 3 (modify logic) |
|-----------|----------------------|-----------------|----------------------|
| Change type | New endpoint | Same | **Modify existing method** |
| Files changed | 3 | 3 | **2** |
| Build pollution | 31→3 | 3 | **2 (clean)** |
| Decision | approve | approve | **approve** |
| Test delta | +1 | +1 | **+7** |
| Clarification rounds | 0 | 0 | **1 (3 questions)** |

## 11. Round 4: File Size Limit + CLI Evidence Fix

### 11.1 Pre-fix: CLI Evidence Alignment

Fixed `ArtifactStore.save_run()`: always write `review_findings.json` (even `[]`), write `policy_result.json` and `phase_timings.json`.

### 11.2 Result Summary

| Area | Result |
|------|--------|
| Spec Council | 4 goals, 4 criteria, 1 clarification round (4 questions) |
| OpenCode execution | 177.8s, 379K tokens |
| Files changed | 3 source + 1 new test class |
| Reviewer | 0 findings |
| Gatekeeper | ✅ approve (drift=0, coverage=100) |
| Baseline → Post tests | 16 → **20** (+4 new) |

### 11.3 CLI Evidence Verification

| File | Status |
|------|--------|
| `review_findings.json` (`[]`) | ✅ NEW |
| `policy_result.json` | ✅ NEW |
| `phase_timings.json` | ✅ NEW |

### 11.4 Code Changes

- `ConvertController.java`: `MAX_FILE_SIZE = 1048576`, size check before conversion
- `GlobalExceptionHandler.java`: added `FILE_TOO_LARGE` code extraction
- New `ConvertControllerFileSizeLimitTest.java`: 4 tests

### 11.5 Blocker Found and Fixed

First attempt timed out: removing `--dangerously-skip-permissions` for real dirs caused opencode to hang. Fix: always use the flag in headless mode.

## 12. Round 4 Clean Rerun — Contamination Confirmed

Fresh copy `/tmp/codegate-real-image2pdf-r4-clean-1777018147`, `pre_run_git_status` = empty, baseline = 9 tests passed.

**Result**: opencode timed out at 300s. CodeGate correctly escalated. But files **were already changed on disk** (3 files modified/added). `mvn test` = BUILD FAILURE — opencode used `@MockitoBean` (Spring Boot 3.4+) on a 3.3.4 project.

**Confirmed**: §11 R4 "success" was contaminated. opencode found pre-existing code and reported "already fully satisfied". Clean-run code has a compile error. Every future run MUST start from a fresh copy with verified empty `git status`.

## 13. Round 4v2: Clean Rerun with Timeout Evidence Capture

### 13.1 Changes Made Before This Run

- `ExecutionReport`: added `timed_out`, `partial_output`, `validation_result` fields
- `OpenCodeAdapter`: timeout now captures changed files via `git status` + reads content
- `OpenCodeAdapter`: post-run validation auto-runs `mvn test`
- `reviewer.py`: timeout warning + validation failure signals in prompt

### 13.2 Clean Workspace

- Dir: `/tmp/codegate-real-image2pdf-r4v2-1777019304`
- `pre_run_git_status`: **empty** ✅
- Baseline: **9 tests, 0 failures** ✅

### 13.3 Result

opencode timed out at 300s again. But this time CodeGate captured everything:

| Field | Before (§12) | After (§13) |
|-------|-------------|-------------|
| `timed_out` | not captured | ✅ `True` |
| `file_list` | `[]` (empty) | ✅ 3 files |
| `files_content` | `{}` (empty) | ✅ 3 files with full content |
| `validation_result` | not captured | ✅ `mvn test` passed, 13 tests |
| `summary` | "timed out" | "timed out. 3 file(s) written to disk" |

### 13.4 Gate Decision Chain

1. **Reviewer**: drift=0, coverage=100, 0 findings (reviewed actual code from disk)
2. **Gatekeeper**: wanted to **approve**
3. **Policy Engine**: **OVERRIDE → REVISE_CODE** because `unresolved_items=["Execution timed out"]`

This is correct behavior: the code is valid, tests pass, but the executor didn't complete normally.

### 13.5 Post-run Validation

```json
{
  "type": "maven",
  "command": "mvn test -B",
  "exit_code": 0,
  "passed": true,
  "tests_run": 13,
  "tests_failed": 0
}
```

13 tests = 9 baseline + 4 new file-size tests. All pass.

### 13.6 Code Quality

This time opencode used `@MockBean` (Spring Boot 3.3.4 compatible), not `@MockitoBean` (3.4+). The non-deterministic executor behavior means the same prompt can produce correct or incorrect code on different runs.

### 13.7 Key Conclusions

1. **Timeout evidence capture works**: CodeGate now captures disk changes even after timeout
2. **Post-run validation works**: `mvn test` result is in the evidence
3. **Policy override is correct**: timeout → can't fully approve → REVISE_CODE
4. **Clean workspace protocol is essential**: without it, this run's validity would be unknown
5. **opencode is non-deterministic**: same prompt produced `@MockitoBean` (§12) vs `@MockBean` (§13)

## 14. Round 4v3: Status Consistency Fix + Multi-iteration Governance

### 14.1 Fix Applied

`apply_policy_override()` now syncs `work_item.status` after overriding `gate_decision.decision`. `summary.json` adds `gatekeeper_original_decision` and `timed_out`.

### 14.2 Clean Workspace

- Dir: `/tmp/codegate-real-image2pdf-r4v3-1777020270`
- Baseline: 9 tests, `git status` = empty ✅

### 14.3 Iteration 1

| Area | Result |
|------|--------|
| opencode | Timed out at 300s |
| Disk changes | **1 file** (Controller only — partial) |
| Validation | mvn test passed (tests_run unknown from partial) |
| Reviewer | **4 findings, 3 blocking** (drift=75, coverage=25) |
| Gatekeeper | `revise_code` (own judgment, not policy override) |
| → | Auto-entered iteration 2 |

### 14.4 Iteration 2

| Area | Result |
|------|--------|
| opencode | Timed out again at 300s |
| Disk changes | 2 files (Controller + new test class) |
| Validation | mvn test passed: 11 tests, 0 failures |
| Reviewer | 0 findings (drift=0, coverage=100) |
| Gatekeeper | wanted `approve` |
| Policy | **OVERRIDE → revise_code** (timeout unresolved) |

### 14.5 Status Consistency

```json
{
  "final_status": "revise_code",          // ← was "approved" in R4v2
  "decision": "revise_code",
  "gatekeeper_original_decision": "approve",
  "timed_out": true
}
```

**No more status divergence** ✅

### 14.6 Key Observations

1. **Multi-iteration worked**: iteration 1 saw partial code → reviewer gave 3 P0 → gatekeeper judged `revise_code` → iteration 2 ran with feedback
2. **Iteration 2 completed the implementation**: code + tests all pass, drift=0, coverage=100
3. **Policy override is the only remaining blocker**: the code is correct but the "Execution timed out" unresolved item prevents final approve
4. **Timeout is the real bottleneck**: opencode needs >300s for this task from a clean baseline. The 300s limit should be reviewed

## 15. Round 4v4: First Clean Approve (600s + iteration history)

### 15.1 Clean Workspace

Dir: `/tmp/codegate-real-image2pdf-r4v4-1777021290`, baseline 9 tests, git_status=empty.

### 15.2 Result

**Iteration 1**: timed out at 600s, 4 files on disk, reviewer gave 5 findings (3 blocking), gatekeeper `revise_code`.

**Iteration 2**: opencode completed within 600s (~280s), 3 files changed, reviewer 0 findings, gatekeeper **APPROVE** ✅.

Final: 12 tests, 0 failures, BUILD SUCCESS.

### 15.3 Evidence Structure

```
iteration_history.json: 2 entries ✅
iterations/1/gate_snapshot.json: 5 findings, 3 blocking ✅
iterations/2/gate_snapshot.json: 0 findings ✅
summary.json: final_status=approved, decision=approve, timed_out=false ✅
```

### 15.4 Key Conclusions

1. **First clean approve from zero**: 2 iterations, no contamination
2. **Governance loop works end-to-end**: timeout → evidence → findings → revise → retry → approve
3. **Iteration history fully persisted**
4. **Total wall-clock: ~902s** (600s timeout + 280s retry + overhead)

## 16. Formal Comparison: Pure OpenCode vs CodeGate+OpenCode

Same requirement, same model, same clean baseline, same 600s timeout.

| Metric | Pure OpenCode | CodeGate + OpenCode |
|--------|---------------|---------------------|
| Completion | ✅ 1 attempt | ✅ 2 iterations |
| Wall-clock | **237s** | 902s |
| Tokens | 607,107 | 648,483 |
| Tests | 11/11 pass | 12/12 pass |
| Files changed | 2 | 3 |
| API compat | ✅ `@SpringBootTest` | ✅ `@MockBean` |
| Auditability | ❌ none | ✅ full |
| Defect detection | ❌ none | ✅ 5 findings iter1 |
| Failure recovery | ❌ manual | ✅ auto-retry |

**Conclusion**: CodeGate is 3.8x slower but provides governance, audit trail, and automated defect detection. The value proposition is not speed — it's "governable AI code changes for production."

Full comparison report: [analysis_results.md](/Users/wukai/.gemini/antigravity/brain/ba85de19-fadf-46cd-be5c-fa1c1e1abaa6/analysis_results.md)

## 17. DPI Validation: Second A/B Comparison

Same protocol: clean baselines (9 tests, git_status=0), same model, same timeout.

| Metric | Line A (Pure OpenCode) | Line B (CodeGate + OpenCode) |
|--------|------------------------|------------------------------|
| Completion | ✅ 1 attempt | ✅ 2 iterations (iter1 timeout) |
| Wall-clock | **222s** | **873s** (600s timeout + 245s retry + overhead) |
| Tokens | 636,271 | 623,939 |
| Tests | 14/14 pass | 14/14 pass |
| Files changed | 3 (Controller + Handler + Test) | 2 (Controller + Test) |
| `@Min(72)` handling | ❌ **Removed** (manual only) | ❌ **Also removed** (manual only) |
| Auditability | ❌ | ✅ iteration_history, findings, gate_decision |
| Iter1 findings | N/A | 5 findings, 5 blocking (drift=100, coverage=0) |

### Key Observations

1. **Both lines removed `@Min(72)`**: opencode in both cases replaced the declarative annotation with manual `if (dpi < 72 || dpi > 600)` validation. This is a **silent behavioral change** — it alters Spring's validation error path from `MethodArgumentNotValidException` to a manual `IllegalArgumentException` / direct response.

2. **CodeGate did NOT catch this**: the `--answers` included "不要移除已有的 @Min(72) 注解", but this was NOT propagated into the final `contract.json`. Reviewer also did not flag the removal. This is the key gap.

3. **Root cause**: Spec Council converts `--answers` into contract goals/constraints, but the current prompt does not explicitly instruct it to preserve existing validation annotations. The generated constraints only covered "don't modify ConversionService" and "don't affect imageFormat/file-size", not "don't remove existing annotations".

4. **Token usage nearly identical**: CodeGate used slightly fewer tokens (623K vs 636K).

### 17.1 Gap: Silent Behavioral Change Detection

This round exposed a critical capability gap:

| What happened | What should happen |
|--------------|-------------------|
| `@Min(72)` removed by executor | Reviewer should flag as P1: "Existing validation annotation removed without explicit requirement" |
| `--answers` said "keep @Min(72)" | Spec Council should propagate this into contract constraints |
| Contract had no "preserve existing" clause | Spec Council should auto-add: "Preserve existing validation annotations unless explicitly required to change" |
| Reviewer saw 0 findings | Reviewer should diff against baseline annotations/signatures |

## 18. DPI Rerun: Silent Behavioral Change Detection ✅

After fixing Spec Council and Reviewer prompts, re-ran the same DPI case.

### 18.1 Prompt Fixes Applied

- **Spec Council**: Added mandatory "Preserve existing validation annotations, exception handling paths, method signatures" constraint
- **Reviewer**: Added Section 7 "Silent Behavioral Change Detection" — checks for annotation removal, exception path changes, signature alterations

### 18.2 Contract Now Includes

```
constraints[0]: "Preserve existing validation annotations, exception handling paths,
                 method signatures, and API behavioral contracts."
```

### 18.3 Results

3 iterations, final decision: **ESCALATE_TO_HUMAN** (drift=40 > threshold=30)

**Reviewer caught 4 silent behavioral changes (all blocking)**:
1. `@Min(72)` annotation removed → `constraints[0]` violation
2. Return type changed `ApiResponse<>` → `ResponseEntity<ApiResponse<>>` → `constraints[0]` violation
3. Error path changed from `throw IllegalArgumentException` → direct ResponseEntity → `constraints[0]` violation
4. `HandlerMethodValidationException` handler removed from GlobalExceptionHandler → `constraints[0]` violation

### 18.4 Before/After Comparison

| Metric | §17 (before fix) | §18 (after fix) |
|--------|-------------------|-----------------|
| `@Min(72)` removal detected | ❌ No | ✅ Yes (P1, blocking) |
| Return type change detected | ❌ No | ✅ Yes (P1, blocking) |
| Error path change detected | ❌ No | ✅ Yes (P1, blocking) |
| Final decision | `approve` | `escalate_to_human` |
| Contract has preservation clause | ❌ No | ✅ Yes (`constraints[0]`) |

### 18.5 New Problem Exposed

Opencode could NOT fix the drift across 3 iterations. Each attempt either removed `@Min(72)` or changed the return type. Drift actually **increased** (iter1: 30 → iter2: 40). This reveals an executor limitation: opencode struggles to "add upper-bound validation while preserving existing annotation-based lower-bound validation" as a single coherent change.

**This is exactly the kind of problem CodeGate should surface.** Without governance, this would ship silently.

### 18.6 Fix: Baseline-Aware Drift Review

§18.3 finding #4 ("Removed HandlerMethodValidationException handler from GlobalExceptionHandler") was confirmed as a **false positive**: clean baseline has NO `HandlerMethodValidationException` handler. It was added by iter1's executor, then removed by iter2. Reviewer mistook "cleanup of previous iteration's error" for "removal of existing behavior".

**Root cause**: Reviewer only saw the CURRENT implementation. It had no visibility into what existed in the CLEAN BASELINE.

**Fix applied** (4 files):
1. `execution.py`: Added `baseline_content: Dict[str, str]` field — stores `git show HEAD:path` for each modified file.
2. `opencode.py`: `_detect_git_changes()` now returns `(changed, baseline)` tuple. Both success and timeout paths populate `baseline_content`.
3. `reviewer.py`: Injects baseline content into reviewer prompt as "📋 BASELINE CONTENT" section with explicit instructions: compare against baseline, not previous iteration.
4. `artifact_store.py`: Fixed `iterations` → `completed_iterations` (len of iteration_history) + `max_iterations`.

**Effect**: Reviewer can now distinguish:
- "This annotation was in baseline but is missing in implementation" → P1 blocking (real regression)
- "This handler was added in iter1 but removed in iter2" → NOT a finding (cleanup)

## 19. DPI Rerun: Baseline-Aware Review Verification

> Artifact: `50a217a11c04`
> Clean workspace: `/tmp/codegate-real-image2pdf-dpi-rerun-1777038921`
> Date: 2026-04-24

### 19.1 Protocol

- Clean copy from `/Users/wukai/IdeaProjects/image2Pdf`
- `pre_run_git_status`: **empty** ✅
- Baseline: **9 tests, 0 failures, BUILD SUCCESS** ✅
- Same request, model (`kimi-for-coding/k2p6`), timeout (600s) as §18

### 19.2 Infrastructure Verification

| Field | §18 (before fix) | §19 (after fix) |
|-------|-------------------|-----------------|
| `summary.json` iteration fields | `"iterations": 3` | `"completed_iterations": 2, "max_iterations": 3` ✅ |
| `baseline_content` populated | ❌ No | ✅ Yes (2 files: Controller + Handler) |
| `iteration_history.json` | Not present | ✅ 2 entries with round/findings/summary |
| `review_findings.json` | Present | ✅ Present |
| Files changed on disk | 3 | 3 (Controller + Handler + new Test) |
| `mvn test` post-run | N/A (timed out) | ✅ 14 tests, 0 failures |

### 19.3 Iteration 1 Results

| Area | Result |
|------|--------|
| Executor | Completed within 600s (~305s) |
| Files changed | 3 (Controller + Handler + Test) |
| Validation | mvn test passed: 14 tests |
| Reviewer | **3 findings, 2 blocking** (drift=15, coverage=100) |
| Gatekeeper | `revise_code` → iteration 2 |

**Iter1 findings**:

1. ⚠️ `@Min(72)` annotation added (executor added it back, but reviewer flagged the addition's interaction with HandlerMethodValidationException) — **blocking**
2. ⚠️ `HandlerMethodValidationException` handler added — reviewer flagged as NOT in baseline — **blocking**
3. ℹ️ `IllegalArgumentException` handler modified to recognize INVALID_DPI prefix — **non-blocking**

**Key observation**: In iter1, the executor actually **added** `@Min(72)` and a `HandlerMethodValidationException` handler (neither removed). The reviewer correctly identified these as **additions** not in baseline, but flagged them as drift from `constraints[0]` because they introduced new exception handling paths.

### 19.4 Iteration 2 Results

| Area | Result |
|------|--------|
| Executor | Completed within 600s (~184s) |
| Reviewer | **2 findings, 2 blocking** (drift=20, coverage=100) |
| Gatekeeper | `revise_code` |
| Policy | **OVERRIDE → escalate_to_human** (max iterations reached) |

**Iter2 findings (final)**:

1. 🚫 `@Min(72)` annotation **removed** from dpi parameter → `constraints[0]` violation — **blocking**
2. 🚫 `HandlerMethodValidationException` handler **removed** from GlobalExceptionHandler → `constraints[0]` violation — **blocking**

### 19.5 Analysis: Did Baseline-Aware Review Work?

**Partially.**

| Expected result | Actual result | Verdict |
|----------------|---------------|---------|
| Continue catching `@Min(72)` removal | ✅ Iter2 finding #1: "@Min(72) removed" | **TRUE POSITIVE** |
| Stop flagging `HandlerMethodValidationException` handler removed (not in baseline) | ❌ Iter2 finding #2: "Handler removed" still flagged as blocking | **FALSE POSITIVE persists** |

**Why the false positive persists**: The execution flow is:

```
iter1: executor ADDS @Min(72) + HandlerMethodValidationException handler
       → reviewer says "these additions create new exception paths, drift"
       → gatekeeper says revise_code

iter2: executor REMOVES @Min(72) + HandlerMethodValidationException handler (opposite direction)
       → reviewer says "these were removed from existing code, drift"
       → but reviewer HAD baseline_content showing they DON'T exist in baseline
```

The reviewer received `baseline_content` for `GlobalExceptionHandler.java` which shows NO `HandlerMethodValidationException` handler. But it still flagged the removal as a violation. This suggests the reviewer LLM either:

1. Did not effectively use the baseline context to distinguish "removed executor-added code" from "removed baseline code", or
2. The prompt guidance for baseline comparison was not specific enough to prevent this pattern.

### 19.6 Before/After Comparison

| Metric | §18 (no baseline) | §19 (with baseline) |
|--------|-------------------|---------------------|
| Total findings (final) | 5 (4 blocking) | **2 (2 blocking)** |
| `@Min(72)` removal detected | ✅ Yes | ✅ Yes |
| Return type change detected | ✅ Yes | — (not flagged this run) |
| Error path change detected | ✅ Yes | — (not flagged this run) |
| `HandlerMethodValidationException` false positive | ✅ Present | ⚠️ **Still present** |
| Iterations | 3 | 2 |
| Total tokens | 551K | **1,371K** (2.5x higher) |
| Summary field names | `iterations: 3` | `completed_iterations: 2, max_iterations: 3` ✅ |
| Baseline captured | ❌ No | ✅ 2 files |

### 19.7 Conclusions

1. **Infrastructure improvements verified**: `completed_iterations`/`max_iterations` field split works, `baseline_content` is populated for modified files, `iteration_history.json` is correctly persisted.

2. **Findings count dropped from 4 to 2**: But NOT because the false positive was eliminated. The reduction is because the executor behaved differently this run (didn't change the return type or error path pattern), so those findings simply didn't occur.

3. **The `HandlerMethodValidationException` false positive persists**: Despite having baseline content, the reviewer still flagged "handler removed" as a constraint violation in iter2. The handler was added by iter1's executor then removed by iter2's executor — it was never in the clean baseline.

4. **Next step**: The reviewer prompt's baseline guidance needs strengthening. The current instruction says "compare against THIS baseline — not against a previous iteration's output" but the LLM did not follow it effectively for this specific pattern. Options:
   - Add explicit examples of "executor-added-then-removed" patterns in the reviewer prompt
   - Pre-process baseline diff before sending to reviewer (only flag removals of things that exist in baseline_content)
   - Add a structural pre-check layer before LLM review that automatically filters baseline-absent patterns

### 19.8 Modified Files Count

This section corrects §18.6 which stated "Fix applied (4 files)" — the actual changes span **6 files**:

| # | File | Change |
|---|------|--------|
| 1 | `spec_council.md` | Added mandatory preservation constraint (§18.1) |
| 2 | `reviewer.md` | Added Section 7 "Silent Behavioral Change Detection" (§18.1) |
| 3 | `execution.py` | Added `baseline_content` field (§18.6) |
| 4 | `opencode.py` | `_detect_git_changes()` returns tuple with baseline (§18.6) |
| 5 | `reviewer.py` | Injects `📋 BASELINE CONTENT` section into prompt (§18.6) |
| 6 | `artifact_store.py` | `iterations` → `completed_iterations` + `max_iterations` (§18.6) |

## 20. Structural Pre-Check: 事实层代码裁决

> Artifact: `7f9b70f4efd1`
> Clean workspace: `/tmp/codegate-real-image2pdf-dpi-precheck-1777040429`
> Date: 2026-04-24
> ADR: `ADR/009-structural-precheck.md`

### 20.1 Problem Statement

§19 证明 baseline 内容注入 prompt 不足以防止假阳性。LLM 在 iter1 正确识别了 `HandlerMethodValidationException` 不在 baseline，但在 iter2 把它的移除误判为 baseline regression。核心原则：**事实判定不要交给 LLM。**

### 20.2 Implementation

三层架构：

```
Layer 1: Structural Pre-Check (deterministic)
  └─ analysis/baseline_diff.py → compute_baseline_diff()
  └─ 正则提取 patterns: annotations, exception handlers, method signatures
  └─ 集合 diff: removed_from_baseline / added_not_in_baseline / unchanged

Layer 2: LLM Review (interpretive)
  └─ 🔬 STRUCTURAL BASELINE DIFF 注入 prompt
  └─ Section 7 限制: "ONLY flag removal of patterns listed in 🔴 REMOVED"

Layer 3: Post-Filter (deterministic)
  └─ 三层验证:
     └─ L1: finding 引用 removed_from_baseline → KEEP
     └─ L2: finding 引用 added_not_in_baseline → SUPPRESS
     └─ L3: finding 主语不在 baseline 原文中 → SUPPRESS (ghost pattern)
```

**新增/修改文件:**

| # | File | Change |
|---|------|--------|
| 1 | `analysis/__init__.py` | [NEW] Package |
| 2 | `analysis/baseline_diff.py` | [NEW] 确定性 diff 计算 + post-filter |
| 3 | `agents/reviewer.py` | 4-step pipeline: pre-check → prompt → LLM → post-filter |
| 4 | `prompts/reviewer.md` §7 | 强制引用 🔬 STRUCTURAL BASELINE DIFF |
| 5 | `ADR/009-structural-precheck.md` | [NEW] 决策记录 |

### 20.3 Unit Test Results

| Test | Input | Expected | Actual |
|------|-------|----------|--------|
| Pattern extraction | baseline has `@Min(72)`, current doesn't | `@Min(72)` in removed | ✅ `@Min(72)` in removed |
| Pattern extraction | baseline has `@ExceptionHandler(IllegalArgument)`, current same | In preserved | ✅ In preserved |
| Subject extraction | "Removed HandlerMethodValidationException handler..." | Subject: `HandlerMethodValidationException` | ✅ |
| Post-filter (§19 scenario) | `@Min(72)` removed + `HandlerMethodValidationException` ghost | Keep @Min, suppress Handler | ✅ 1 kept, 1 suppressed |

### 20.4 DPI Rerun Results

| Area | §19 (prompt-only) | §20 (structural pre-check) |
|------|-------------------|---------------------------|
| Executor behavior | Removed `@Min(72)`, added then removed Handler | **Preserved `@Min(72)`**, added `@Max(600)` + Handler |
| Structural diff | N/A | 0 removed, 5 added, 16 preserved |
| `@Min(72)` status | ❌ Removed (true drift) | ✅ **Preserved** (in ⚪ list) |
| `HandlerMethodValidationException` | ❌ False positive finding | ✅ In 🟢 ADDED list (would be correctly suppressed if iter2 removed it) |
| Findings | 2 blocking | **0** |
| Decision | `escalate_to_human` | **`approve`** ✅ |
| Iterations | 2 (then max iter policy) | **1** |
| Total tokens | 1,371K | **1,067K** |

### 20.5 Analysis

**This run passed cleanly** — the executor preserved `@Min(72)` and correctly added `@Max(600)` alongside it. Because no baseline patterns were removed, the structural diff showed `removed: 0`, and the reviewer found no drift.

**The structural pre-check was computed correctly:**
- `@Min(72)` in ⚪ PRESERVED → reviewer correctly saw it as baseline behavior that was maintained
- `HandlerMethodValidationException` handler in 🟢 ADDED → if a future iteration removes it, the post-filter will correctly suppress the finding (Layer 3: ghost pattern not in baseline)

**Limitation**: This run didn't trigger the post-filter because the executor behaved correctly. The false positive suppression was only verified in unit tests, not in a live run. A full validation would require an executor that removes `@Min(72)` AND adds/removes a ghost handler.

### 20.6 Conclusions

1. **Structural pre-check infrastructure works end-to-end**: `compute_baseline_diff()` correctly identifies patterns across Java files, and the diff is injected into the reviewer prompt.

2. **Post-filter three-layer logic validated in unit tests**: The exact §19 false positive scenario (`HandlerMethodValidationException` ghost) is correctly suppressed while `@Min(72)` removal is correctly kept.

3. **Product principle confirmed**: "Facts by code, judgment by LLM" is now implemented at three levels — pre-check constrains the LLM's input, prompt restricts its freedom, and post-filter corrects its errors.

## 21. Forced Ghost Pattern — End-to-End Verification

> Artifact: `cbd13befdb63`
> Date: 2026-04-24
> Test script: `tests/test_ghost_pattern_e2e.py`

### 21.1 Objective

§20 的 DPI rerun 因为 executor 行为正确（保留了 `@Min(72)`），post-filter 未被触发。本轮使用 **fixture executor** 强制构造最坏场景，验证 post-filter 在真实 LLM reviewer 输出上的端到端效果。

### 21.2 Fixture Design

`GhostPatternFixtureExecutor` 返回受控的 `ExecutionReport`：

| Iteration | Controller | Handler | 预期审查重点 |
|-----------|-----------|---------|-------------|
| iter1 | 保留 `@Min(72)`, 新增 `@Max(600)` | **新增** `HandlerMethodValidationException` handler | 新增 handler 非 baseline |
| iter2 | **移除 `@Min(72)`**, 手写 if-check | **移除** `HandlerMethodValidationException` handler | `@Min(72)` = 真漂移, Handler = ghost |

两轮都传入相同的 `baseline_content`（真实 git HEAD）。

### 21.3 Execution Flow

```
Spec Council → Contract (2 goals, 6 criteria)
    ↓
Fixture iter1 → Reviewer (real LLM)
    Pre-check: 0 removed, 3 added, 9 preserved
    Findings: 3 (2 blocking) — placeholder tests, coverage issue
    Gate: revise_code
    ↓
Fixture iter2 → Reviewer (real LLM)
    Pre-check: 1 removed (@Min(72)), 0 added, 8 preserved
    LLM output: 4 findings (including HandlerMethodValidationException removal)
    ↓
    POST-FILTER: 1 finding suppressed (ghost pattern)
    Final: 3 findings (3 blocking)
    Gate: revise_code → policy override (max iterations)
```

### 21.4 Post-Filter Verification

**关键日志行**（确定性代码执行，非 LLM 判断）：

```
[POST-FILTER] Suppressed (ghost pattern — not in baseline):
  'Removed HandlerMethodValidationException handler (no longer needed) — this is a ...'
  Subject 'HandlerMethodValidationException' not found in any baseline file
[POST-FILTER] 1 findings suppressed, 3 kept
```

**三层验证路径**：

| Finding | Layer 1 (removed?) | Layer 2 (added?) | Layer 3 (in baseline?) | Result |
|---------|-------------------|-----------------|----------------------|--------|
| `@Min(72)` removed | ✅ In removed list | — | — | **KEEP** (true positive) |
| `HandlerMethodValidationException` removed | ❌ Not in removed | ❌ Not in added | Subject "HandlerMethodValidationException" not in baseline text | **SUPPRESS** (ghost) |

### 21.5 Results

| Metric | §19 (no pre-check) | §21 (with pre-check, forced scenario) |
|--------|-------------------|--------------------------------------|
| `@Min(72)` removal detected | ✅ | ✅ |
| `HandlerMethodValidationException` ghost | ❌ False positive **present** | ✅ **SUPPRESSED by post-filter** |
| Post-filter triggered | N/A | ✅ 1 suppressed |
| Verdict | FAIL (false positive) | **PASS** |
| Elapsed | ~528s (real executor) | **43s** (fixture) |

### 21.6 Final Findings (iter2)

| # | Category | Severity | Message | Blocking | Verdict |
|---|----------|----------|---------|----------|---------|
| 1 | drift | P1 | Removed @Min(72) annotation | ✅ | True positive |
| 2 | completeness | P1 | Placeholder tests (empty bodies) | ✅ | True positive (fixture limitation) |
| 3 | completeness | P1 | No ConversionService.convert mock verification | ✅ | True positive (fixture limitation) |
| ~~4~~ | ~~drift~~ | ~~P1~~ | ~~Removed HandlerMethodValidationException handler~~ | — | **Suppressed by post-filter** |

### 21.7 Conclusions

1. **Ghost pattern suppression 端到端验证通过**。Post-filter 在真实 LLM reviewer 输出上正确识别并抑制了 `HandlerMethodValidationException` 假阳性，同时保留了 `@Min(72)` 真阳性。

2. **三层验证路径完整覆盖**：Layer 1 捕获 `@Min(72)`（在 `removed_from_baseline`），Layer 3 捕获 `HandlerMethodValidationException` ghost（subject 不在 baseline 原文中）。

3. **"Facts by code, judgment by LLM" 原则完整闭环**。从 §19（发现问题）→ §20（架构实现）→ §21（端到端验证），结构化预检能力经过了完整的 "发现 → 设计 → 实现 → 单元测试 → 集成测试" 生命周期。

## 22. 审计证据持久化

> Date: 2026-04-24

### 22.1 Problem

§21 验证了 post-filter 在真实 LLM 输出上的正确性（artifact `cbd13befdb63`），但该 artifact 在审计证据代码实现之前生成，因此没有落盘 `structural_diff.json` / `raw_review_findings.json` / `suppressed_findings.json`。后续两轮 e2e 重跑（`27b8a16596ec`, `7790b1c4f30f`）LLM 因为读了 structural diff prompt 后不再产出 ghost finding，所以 `suppressed_findings_count=0`。

需要独立验证：审计证据链落盘路径在有 suppression 的场景下正确工作。

### 22.2 Implementation

| File | Change |
|------|--------|
| `workflow/state.py` | +3 fields: `structural_diff`, `raw_review_findings`, `suppressed_findings` |
| `agents/reviewer.py` | 保存 raw findings (filter 前) + 构建 suppressed 记录 (with reason) |
| `store/artifact_store.py` | 持久化 3 个新 JSON + summary 加 `raw_findings_count` / `suppressed_findings_count` |
| `workflow/graph.py` | `_reconstruct_state` 处理 `raw_review_findings` 反序列化 |

**审计链：**

```
structural_diff.json       ← compute_baseline_diff() 输出
→ raw_review_findings.json ← LLM 原始 findings (filter 前)
→ suppressed_findings.json ← post-filter 压掉的 findings + suppression_reason
→ review_findings.json     ← 最终可信 findings
→ summary.json             ← findings_count / raw_findings_count / suppressed_findings_count
```

**不变量：** `raw_findings_count == findings_count + suppressed_findings_count`

### 22.3 Verification Results

| Test | Artifact | Type | suppressed | Result |
|------|----------|------|-----------|--------|
| Audit evidence persistence test | `b6682da3751b` | 控制输入，验证落盘 | **1** (HandlerMethodValidationException ghost) | ✅ invariant 3==2+1 |
| Ghost e2e with real LLM | `27b8a16596ec` | 真实 LLM，无 ghost 产出 | 0 | ✅ structural_diff + raw 正确，无 suppression |
| Ghost e2e with real LLM | `7790b1c4f30f` | 真实 LLM，无 ghost 产出 | 0 | ✅ structural_diff + raw 正确，无 suppression |

**`b6682da3751b` 落盘验证：**

```
structural_diff.json:      removed=1 (@Min(72)), preserved=4
raw_review_findings.json:  3 findings
suppressed_findings.json:  1 finding (reason: ghost_pattern_not_in_baseline)
review_findings.json:      2 findings
summary.json:              findings=2, raw=3, suppressed=1
```

### 22.4 Observation

后续两轮 e2e 重跑中 LLM 没有产出 ghost finding，说明 **pre-check prompt 注入 (Layer 1) 已经在源头减少了 LLM 的误判**。Post-filter (Layer 3) 变成了兜底而非主力。这是好的——多层防御中，越早拦截越好。

### 22.5 阶段 1 结论

```
审计证据持久化：通过 (b6682da3751b)
raw/final/suppressed 不变量：通过 (3 == 2 + 1)
ghost suppression 可审计：通过 (suppression_reason 字段落盘)
structural_diff 可审计：通过 (removed/added/preserved 落盘)
```

**阶段 1 完成。** 下一步：阶段 2 — 扩展 3 个 fixture regression case 做漂移拦截能力回归验证。

## 23. 阶段 2: A/B 评估 — 3 个 Fixture Regression Case

> Date: 2026-04-24
> Test scripts: `tests/test_ab_case1.py`, `tests/test_ab_case2.py`, `tests/test_ab_case3.py`
> Artifact directory: `artifacts/` (default ArtifactStore path)

### 23.1 设计

使用 fixture executor（与 §21 相同模式），每个 case 构造"典型 LLM 漂移行为"的 bad implementation，通过 real LLM reviewer 检出。fixture 模式不消耗 real opencode tokens，每 case ~30-60s。

3 个 case 的 bad implementation 基于 §17-§19 观察到的 real executor 典型漂移行为设计。

### 23.2 Case 1: 错误响应一致性

> Artifact: `3996a47e4e55`

**请求**: 为 `/api/convert` 增加文件名非法字符校验，复用 `ApiResponse.error` 和 `GlobalExceptionHandler`。

**Fixture 漂移行为**:
- 直接 `ResponseEntity.badRequest().body("Invalid filename")` — 绕过 `ApiResponse.error`
- 修改 `handleBadRequest` 返回类型为 `ResponseEntity<String>`
- 新增不必要的 `@ExceptionHandler(SecurityException.class)`

| Area | Result |
|------|--------|
| Structural pre-check | 2 removed, 4 added, 8 preserved |
| Reviewer findings | **10 findings (9 blocking)** |
| Drift score | **80** |
| Decision | `escalate_to_human` (2 iterations → max iter policy) |
| Elapsed | 58.2s |

**检出的关键漂移**:
1. ✅ `ApiResponse.error` bypass — P0 blocking
2. ✅ `convert()` 返回类型从 `ApiResponse<ConvertResponse>` 改为 `ResponseEntity<?>` — P1 blocking
3. ✅ `handleBadRequest` 签名/返回类型变更 — P1 blocking
4. ✅ 非法新增 `SecurityException` handler — P1 blocking

**Verdict: PASS** ✅

---

### 23.3 Case 2: 方法签名保护

> Artifact: `7729585a5ad5`

**请求**: 为 `/api/convert` 增加可选 `quality` 参数，不改变返回类型和 endpoint contract。

**Fixture 漂移行为**:
- 返回类型从 `ApiResponse<ConvertResponse>` 改为 `ResponseEntity<ApiResponse<ConvertResponse>>`
- 移除 dpi 上的 `@Min(72)` 注解
- 修改 `ConvertResponse` record 添加 `quality` 字段

| Area | Result |
|------|--------|
| Structural pre-check | 2 removed, 2 added, 5 preserved |
| Reviewer findings | **9 findings (9 blocking)** |
| Drift score | **80** |
| Decision | `escalate_to_human` (1 iteration, gatekeeper 直接判定) |
| Elapsed | 34.0s |

**检出的关键漂移**:
1. ✅ 返回类型变更 — P1 blocking
2. ✅ `@Min(72)` 注解被移除 — P1 blocking
3. ✅ `ConvertResponse` record 被修改 — P1 blocking

**Verdict: PASS** ✅

---

### 23.4 Case 3: 测试质量

> Artifact: `f4f19deb2d28`

**请求**: 为 `ConversionService.findJob()` 编写单元测试，必须有真实断言，验证异常。

**Fixture 漂移行为**:
- `testFindJobNotFound()` — 空测试体 `// TODO`
- `testFindJobSuccess()` — 弱断言 `assertNotNull(service)`
- `testFindJobWithNullId()` — 空占位
- `testFindJobReturnsCorrectJob()` — `assertTrue(true)` 伪断言

| Area | Result |
|------|--------|
| Structural pre-check | 0 removed, 0 added, 0 preserved (new test file only) |
| Reviewer findings | **9 findings (6 blocking)** |
| Drift score | **80** |
| Coverage score | **0** |
| Decision | `escalate_to_human` (2 iterations → max iter policy) |
| Elapsed | 46.9s |

**检出的关键质量问题**:
1. ✅ 空测试体 / placeholder — P0 blocking (×5)
2. ✅ 弱断言 `assertNotNull(service)` — 检出为"不验证业务逻辑"
3. ✅ 未使用 `assertThrows` 验证异常 — P0 blocking

**Verdict: PASS** ✅

---

### 23.5 审计证据完整性

| Artifact | structural_diff | raw_review_findings | review_findings | summary invariant |
|----------|----------------|--------------------|-----------------|--------------------|
| `3996a47e4e55` (Case 1) | ✅ | ✅ raw=10 | ✅ final=10 | ✅ 10=10+0 |
| `7729585a5ad5` (Case 2) | ✅ | ✅ raw=9 | ✅ final=9 | ✅ 9=9+0 |
| `f4f19deb2d28` (Case 3) | ✅ | ✅ raw=9 | ✅ final=9 | ✅ 9=9+0 |

所有 case 的 `raw_findings_count == findings_count + suppressed_findings_count` 不变量均通过。

### 23.6 V1 成功标准评估（修正口径）

将 case 分为两类：
- **真实 repo/executor case**：使用 real opencode 在 image2pdf 真实副本上执行。
- **Fixture regression case**：使用 fixture executor 构造已知坏实现，通过 real LLM reviewer 检出。

| Criterion | Threshold | Actual | Status |
|-----------|-----------|--------|--------|
| 真实 repo/executor case | >= 3 | **4** (imageFormat/file-size/DPI x2) | OK |
| Fixture regression case | >= 3 | **4** (ghost + Case 1/2/3) | OK |
| >= 2 real case 证明 pure OpenCode 有漂移 | >= 2 | **2** (DPI: @Min 移除 + 返回类型变更) | OK |
| >= 2 fixture case 证明 reviewer 拦截能力 | >= 2 | **3** (Case 1/2/3) | OK |
| false positive 可解释 | 有 reason | suppressed_findings 有 suppression_reason | OK |
| 可过滤 | post-filter 三层 | 20-21 验证通过 | OK |
| 可审计 | 落盘 | structural_diff + raw/final/suppressed 全落盘 | OK |
| 单轮 governance overhead | <= 20% | 单轮成功 case 约 5-9% (10-20s / 230s) | OK |

**Overhead 说明**：16 的 3.8x 来自 retry（iter1 timeout + iter2 成功）。单轮成功 case（10/11）overhead 主要是 spec_council + reviewer + gatekeeper 的 LLM 调用，约 10-20s / 230s = 5-9%。

### 23.7 Phase 2 Conclusions

1. **3/3 case 全部 PASS**。reviewer 在所有 fixture-constructed bad implementation 上正确识别了预设的漂移行为。

2. **Case 1 + Case 2 证明 drift 检出能力**：返回类型变更、`@Min(72)` 移除、`ApiResponse.error` bypass、handler 签名变更 — 这些是 §17-§19 中观察到的 real executor 典型漂移，reviewer 全部检出。

3. **Case 3 证明 completeness 检出能力**：空测试体、弱断言、伪断言 — reviewer 正确标记为 P0 blocking，coverage=0。这是此前未单独测试的 category。

4. **审计证据链完整**：每个 case 均有 `structural_diff.json` / `raw_review_findings.json` / `review_findings.json` / `summary.json`，不变量全部通过。

5. **Fixture 模式高效可重复**：3 case 合计 ~139s（含 LLM 调用），无 opencode executor 开销。结果确定性高，适合 CI 回归。

### 23.8 边界声明

**Phase 2 完成的是 fixture regression suite，不等同于真实项目 A/B benchmark 完成。**

Fixture case 证明了 reviewer 对已知坏实现的拦截能力，但产品最终需要证明的是"真实 executor 在真实 repo 上会犯这些错，而 CodeGate 能拦住"。§17-§18 的 DPI case 已经部分达成这个目标（real opencode 在两条 line 上都移除了 `@Min(72)`，CodeGate 在 §18 后检出）。

**下一步**：回到 1-2 个 real opencode case，将 fixture 里验证过的三类问题（错误响应一致性、方法签名保护、测试质量）在真实执行器上复测，完成从"回归测试"到"市场证明"的闭环。

## 24. 阶段 3: 真实执行器 A/B 市场证明

> Date: 2026-04-24
> Executor: opencode + kimi-for-coding/k2p6
> Protocol: fresh copy from `/Users/wukai/IdeaProjects/image2Pdf`, `git status --porcelain` = 0, `mvn test` = BUILD SUCCESS

### 24.1 Real Case 1: 错误响应一致性

**需求**: 为 `/api/convert` 增加文件名非法字符校验（`..` 或 `/`），返回 400，复用 `ApiResponse.error` + `GlobalExceptionHandler`，不新增 handler，不改方法签名/返回类型。

#### Line A: Pure OpenCode

| Metric | Value |
|--------|-------|
| Workspace | `/tmp/codegate-real-image2pdf-p3c1a-1777045956` |
| Files changed | 3 (ConvertController, GlobalExceptionHandler, ConvertControllerTest) |
| Tests | 12 pass, 0 fail |
| Duration | ~135s |

**Code review**: Pure OpenCode 实现**正确**，无漂移。
- ✅ 抛出 `IllegalArgumentException("INVALID_FILENAME: ...")`，由 `handleBadRequest` 统一处理
- ✅ 返回类型保持 `ApiResponse<ConvertResponse>`
- ✅ `handleBadRequest` 签名不变
- ✅ 无新增 `@ExceptionHandler`
- ✅ `@Min(72)` 保留

#### Line B: CodeGate + OpenCode

| Metric | Value |
|--------|-------|
| Workspace | `/tmp/codegate-real-image2pdf-p3c1b-1777046138` |
| Artifact | `real_project_results/0af354d369d8` |
| Decision | **APPROVE** |
| Drift score | **0** |
| Coverage score | **100** |
| Findings | **0** |
| Tests | 13 pass, 0 fail |

**Phase timings**:
| Phase | Time |
|-------|------|
| spec_council | 16.2s |
| executor | 173.1s |
| reviewer | 1.2s |
| gatekeeper | 2.3s |
| **total** | **192.9s** |
| **governance overhead** | **19.7s (11.4%)** |

**结论**: 两条 line 结果一致 — executor 生成正确代码，CodeGate 正确判定 APPROVE，0 false positive。Governance overhead 11.4%。

---

### 24.2 Real Case 2: 测试质量

**需求**: 为 `ConversionService.findJob()` 编写单元测试，验证 not-found/exists/null 三种场景，必须有真实断言。

#### Line A: Pure OpenCode

| Metric | Value |
|--------|-------|
| Workspace | `/tmp/codegate-real-image2pdf-p3c2a-1777046378` |
| Files changed | 1 (ConversionServiceFindJobTest.java, new file) |
| Tests | 12 pass, 0 fail (3 new) |
| Duration | ~126s |

**Code review**: Pure OpenCode 实现**正确**，无弱测试。
- ✅ `assertThrows(IllegalArgumentException.class, ...)` 验证异常
- ✅ `assertTrue(ex.getMessage().contains(jobId))` 验证消息内容
- ✅ `assertEquals` 验证返回对象属性
- ✅ `assertThrows(NullPointerException.class, ...)` 验证 null 行为
- ✅ 无空测试体、无占位、无弱断言

#### Line B: CodeGate + OpenCode

| Metric | Value |
|--------|-------|
| Workspace | `/tmp/codegate-real-image2pdf-p3c2b-1777046542` |
| Artifact | `real_project_results/30434c783815` |
| Decision | **APPROVE** |
| Drift score | **10** |
| Coverage score | **100** |
| Findings | **1** (P1 advisory — legacy term: "non-blocking P1") |
| Tests | 12 pass, 0 fail (3 new) |

**唯一 finding**: `[P1 advisory] null test expects NullPointerException, but contract says "verify behavior"` — reviewer 正确识别了 contract 措辞与实际异常类型的细微不一致。这是合理的 advisory finding，非 false positive。

> **术语说明**: 此 artifact (`30434c783815`) 产生于 severity 重构前，使用 legacy schema (`blocking: false`)。重构后应表达为 `severity=P1, disposition=advisory`。

**Phase timings**:
| Phase | Time |
|-------|------|
| spec_council | 13.5s |
| executor | 177.2s |
| reviewer | 3.5s |
| gatekeeper | 2.0s |
| **total** | **196.2s** |
| **governance overhead** | **19.0s (10.7%)** |

---

### 24.3 Phase 3 评估

#### 结果汇总

| Case | Line A 漂移 | Line B Decision | Drift | Findings | Overhead |
|------|------------|----------------|-------|----------|----------|
| 1. 错误响应一致性 | 无 | APPROVE | 0 | 0 | 11.4% |
| 2. 测试质量 | 无 | APPROVE | 10 | 1 (P1 advisory) | 10.7% |

#### 关键发现

1. **kimi-for-coding/k2p6 在这两个 case 上没有犯错**。两条 Line A 都生成了正确、无漂移的代码。这与 §17-§18 的 DPI case（同一模型，但移除了 `@Min(72)`）形成对比，说明 LLM 漂移是 **非确定性** 的 — 同一模型不是每次都犯同一类错。

2. **CodeGate 在 executor 正确时不添乱**。两个 case 都是 APPROVE，0-1 findings，false positive = 0。这验证了 "CodeGate 不应该在 executor 做对的时候制造噪音" 的设计目标。

3. **Governance overhead 稳定在 ~11%**。两个 case 分别 11.4% 和 10.7%，远低于 20% 阈值。主要来自 spec_council (13-16s) + reviewer (1-3.5s) + gatekeeper (2s)。

4. **Reviewer advisory finding 有价值**。Case 2 的 P1 advisory finding 识别了 contract 措辞与实际行为的细微不一致（"verify behavior" vs NullPointerException），这不是 false positive 而是合理的 advisory。（注：此 finding 产生于 severity 重构前，原始记录为 `P1 non-blocking`，重构后术语为 `severity=P1, disposition=advisory`。）

#### Phase 3 成功标准

| Criterion | Threshold | Actual | Status |
|-----------|-----------|--------|--------|
| real opencode case 完成 A/B | >= 2 | **2** | OK |
| >= 1 case pure OpenCode 出现漂移 | >= 1 | **0** (本轮) | 未达标 |
| CodeGate false positive | 0 或可解释 | **0** | OK |
| 可审计证据 | 有 | structural_diff + findings + decision 全落盘 | OK |
| 单轮 governance overhead | <= 20% | **11.4% / 10.7%** | OK |

#### 未达标项分析

"至少 1 个 case pure OpenCode 出现漂移"未在本轮达标。但结合 §17-§18 的 DPI real case（同一模型确实移除了 `@Min(72)`），整体 real case 证据链是完整的：

- §17-§18: real executor 漂移 → CodeGate 检出 → revise_code
- §24: real executor 正确 → CodeGate 正确 APPROVE → 0 false positive

两个方向都得到了验证：**该拦的拦了（§17-§18），不该拦的没拦（§24）。**

## 25. Phase 4 Planning: From Experiment to Alpha

> Date: 2026-04-25

### 25.1 Product Interpretation of §17-§24

§24 的 2 个 real case 中 pure OpenCode 没有犯错。但这不削弱 CodeGate 的价值 — 反而补上了一块关键证据：**低噪音放行能力**。

治理产品如果只会拦错、不会放对，就没法商业化。§24 证明了 CodeGate 在 executor 正确时：
- False positive = 0
- Governance overhead = 10.7%-11.4%
- 不制造噪音，不阻塞开发流

结合 §17-§18（同一模型、相似任务，但 executor 移除了 `@Min(72)` → CodeGate 检出并 revise），完整的双向证据链是：

| 场景 | 证据 | CodeGate 行为 |
|------|------|---------------|
| executor 漂移 | §17-§18 DPI case | 检出 → revise_code → 拦截 |
| executor 正确 | §24 Case 1 + Case 2 | APPROVE → 0 findings → 放行 |

**核心论点**：LLM 漂移的非确定性本身就是 CodeGate 存在的理由。同一模型在相似任务上有时正确、有时静默漂移 — 你没法靠"选个好模型"消除风险，只能靠治理层兜底。CodeGate 的价值不在于假设 executor 一定犯错，而在于：

> **当它犯错时有机制拦截，当它正确时不增加摩擦。**

这比单纯强调"质量更高"更稳，也更符合治理产品定位。

### 25.2 Phase 4 Priority

| Priority | Item | Rationale |
|----------|------|-----------|
| **P0** | **A/B runner 自动化** | 当前每个 case 手工 4 步（copy → Line A → Line B → diff），报告靠人工整理。不自动化就不可复现，不可 CI |
| **P0** | **Severity × Disposition 重构** | `P1 non-blocking` 语义矛盾。用户会问"为什么 P1 还能 approve？"。改为两维：`severity = impact (P0/P1/P2)` × `disposition = blocking/advisory/info` |
| **P1** | **Evidence report 生成** | JSON → 可读 Markdown/HTML 报告。给团队 lead / 审计方看的，不是给开发者看 JSON 的 |
| **P2** | **Eval case 扩展到 6 个** | runner 稳定后再扩，否则每加一个 case 都是人工成本 |
| **P2** | **第二个项目** | image2Pdf 已经足够证明机制。第二个项目的增量价值有限，等 runner 好了再加 |

### 25.3 Backlog

- **Interactive Spec Council pause/resume**：当前 `--answers` 是跳过交互的 workaround。Alpha 版应该支持 spec_council 暂停等待用户回答 clarification questions 后再继续，否则 contract 看起来像"走过场"。不急，但在 Alpha demo 前必须解决。

### 25.4 Alpha 定位

当前最好的产品定位：

> **CodeGate 不是让 AI coding 更快，而是让 AI coding 的变更可审计、可阻断、可复盘。**

核心能力矩阵：

| Capability | Status | Evidence |
|------------|--------|----------|
| Contract-first governance | ✅ | Spec Council → Contract → Goals/Criteria/Constraints |
| Baseline-aware drift detection | ✅ | Structural pre-check + LLM reviewer + post-filter |
| Low-noise approval | ✅ | §24: 0 false positive, ~11% overhead |
| Drift interception | ✅ | §17-§18: @Min(72) removal caught |
| Ghost pattern suppression | ✅ | §21: 3-layer post-filter |
| Audit evidence persistence | ✅ | §22: structural_diff + raw/final/suppressed findings |
| Fixture regression suite | ✅ | §23: 3 cases, CI-ready |
| Severity x Disposition | ✅ | §26: two-dimensional classification |
| Automated A/B runner | ✅ | §27: `codegate ab` CLI command |
| Basic A/B evidence report | ✅ | §27: auto-generated Markdown per case |
| Auditor-ready evidence report | ✅ | §28: 7-section `audit_report.md` |
| Batch A/B runner | ✅ | §29: `codegate ab-batch` CLI command |
| Interactive clarification | ❌ | Backlog |

## 26. Phase 4 P0-1: Severity x Disposition Refactor

> Date: 2026-04-25
> Verification artifact: `artifacts/a3b0600c850a`

### 26.1 Problem

§24 Case 2 产生了 `P1 non-blocking` finding。这个表述语义矛盾："P1 = significant" 暗示应该阻断，但 `non-blocking` 说不用。用户会问"为什么 P1 还能 approve？"

### 26.2 Solution: Two-Dimensional Classification

将原来的 `severity + blocking boolean` 改为 `severity (impact) x disposition (gate action)` 两维度：

| Severity | Meaning | Typical Disposition |
|----------|---------|-------------------|
| P0 | Critical: constraint violated, security vulnerability | blocking |
| P1 | Significant: goal partially met, silent behavioral change | blocking or advisory |
| P2 | Minor: style, optimization | advisory or info |

| Disposition | Gate Action | Icon |
|-------------|------------|------|
| blocking | Must fix before approval | 🚫 block |
| advisory | Should fix, doesn't block | ⚠ advise |
| info | Informational only | ℹ info |

**Key insight**: `P1 advisory` is now a valid, non-contradictory expression. It means "significant impact, but doesn't block this approval" — e.g., a nuanced observation the reviewer flagged for human awareness.

### 26.3 Changes

| File | Change |
|------|--------|
| `schemas/review.py` | Added `disposition` field; `model_post_init` syncs `blocking` <-> `disposition` bidirectionally |
| `prompts/reviewer.md` | Updated output format, examples, severity/disposition guidelines |
| `agents/reviewer.py` | Parser handles both `disposition` (new) and `blocking` (legacy) |
| `cli.py` | Findings table: "Blocking" column -> "Disposition" column with colored icons |
| `store/artifact_store.py` | Summary adds `advisory_findings` + `info_findings` alongside `blocking_findings` |

### 26.4 Backward Compatibility

- Legacy `blocking=True` → auto-mapped to `disposition="blocking"`
- Legacy `blocking=False` → auto-mapped to `disposition="advisory"`
- Old artifacts (e.g., `7729585a5ad5`, `30434c783815`) retain `blocking` field but `disposition=null` → these are legacy schema artifacts, pre-refactor
- New artifacts (e.g., `a3b0600c850a`) have both `disposition` and `blocking` fields

### 26.5 Verification

**Unit tests** (5/5 pass):

```
Test 1 (P0 blocking):   disposition=blocking, blocking=True  ✅
Test 2 (P1 advisory):   disposition=advisory, blocking=False ✅
Test 3 (legacy True):   disposition=blocking, blocking=True  ✅
Test 4 (legacy False):  disposition=advisory, blocking=False ✅
Test 5 (P2 info):       disposition=info,     blocking=False ✅
```

**E2e fixture validation** (artifact `a3b0600c850a`):
- 14 findings, all `disposition=blocking`
- Summary: `blocking_findings=14, advisory_findings=0, info_findings=0`
- `review_findings.json` 每条均含 `disposition` 字段

### 26.6 Schema Migration Note

| Artifact Era | Schema | `disposition` field | `blocking` field |
|-------------|--------|-------------------|-----------------|
| §10-§24 (pre-refactor) | legacy | absent or null | present |
| §26+ (post-refactor) | v2 | present | present (derived) |

旧 artifact 不需要迁移。`blocking` 字段保留为派生便利字段，确保所有下游代码（gatekeeper、executor、policy engine）无需改动。

## 27. Phase 4 P0-2: A/B Runner 自动化

> Date: 2026-04-25

### 27.1 实现

新增 `codegate ab` CLI 命令，自动化完整 A/B 协议：

```text
codegate ab \
  --project /path/to/project \
  --input "requirement" \
  --model kimi-for-coding/k2p6 \
  --case-name "错误响应一致性"
```

自动执行 5 步：
1. **Clean copy** — 从源项目复制两份独立副本（Line A / Line B）
2. **Baseline verify** — `git status --porcelain` + `mvn test -B`
3. **Line A** — pure opencode（无治理）
4. **Line B** — `codegate run`（含完整 governance pipeline）
5. **Report** — 自动生成 Markdown evidence report + JSON raw data

### 27.2 新文件

| File | Description |
|------|-------------|
| `src/codegate/eval/__init__.py` | Eval module init |
| `src/codegate/eval/ab_runner.py` | A/B runner core logic |
| `src/codegate/cli.py` (modified) | Added `codegate ab` command |

### 27.3 首次自动运行结果（pre-hardening）

> ⚠️ 此结果产生于 §27.5 hardening 之前，包含已修复的 heuristic false positive。

> Case: 错误响应一致性
> Report: `ab_results/错误响应一致性_1777094809/report.md`
> Artifact: `f3246be9e107`

| Dimension | Line A (Pure) | Line B (CodeGate) |
|-----------|---------------|-------------------|
| Duration | 115.4s | 215.2s |
| Files changed | 3 | 4 |
| Tests pass | Yes | Yes |
| Heuristic flags | 2 (false positive) | N/A (governed) |
| Decision | N/A | APPROVE |
| Overhead | N/A | 9.1% |

**关键发现**：
- Line A 的 drift detector 触发了 `return_type_change` + `new_exception_handler`。人工审查确认是 **false positive** — diff 中同时出现 `ResponseEntity` 和 `ApiResponse` 是因为扩展了 if-else 分支，并非改变了返回类型。
- 这个 false positive 直接推动了 §27.5 的 6 项 hardening 修正。

### 27.4 P0 出口验证（post-hardening）

> Case: 错误响应一致性-P0验收
> Report: `ab_results/错误响应一致性-p0验收_1777096460/report.md`
> Artifact: `f919ae5c8a28`

| Dimension | Line A (Pure) | Line B (CodeGate) |
|-----------|---------------|-------------------|
| Duration | 125.7s | 140.8s |
| Files changed | 3 | 3 |
| Tests pass | Yes | Yes |
| Heuristic flags | **None** ✅ | N/A (governed) |
| Decision | N/A | **APPROVE** |
| Drift score | N/A | 0 |
| Coverage score | N/A | 100 |
| Findings | N/A | 0 (blocking=0, advisory=0, info=0) |
| Overhead | N/A | **15.6%** |

**验收结论**：
- 旧 false positive（`return_type_change` + `new_exception_handler`）不再触发 ✅
- Verdict 使用新措辞："Both lines produced correct code. CodeGate correctly approved (drift=0, 0 false positives)." ✅
- Report 包含 Line B changed files + diff stat ✅
- `copytree` 排除了 `target/` 等构建产物（Line A/B 文件数一致）✅
- Overhead 15.6%，低于 20% 阈值 ✅


### 27.5 Report 自动生成

每次运行产生：
- `ab_result.json` — 完整 raw 数据（baseline、Line A、Line B、timings、findings）
- `report.md` — 人类可读的 Markdown 证据报告
- `codegate_artifacts/` — Line B 的完整 governance artifact（summary、findings、diff、decision）

### 27.6 P0-3 Hardening (same day)

基于首次运行的 heuristic false positive，进行了 6 项修正：

| # | Fix | Before | After |
|---|-----|--------|-------|
| 1 | Verdict 措辞 | "Line A has drift" | "Heuristic indicators triggered; manual/LLM review required" |
| 2 | 字段命名 | `drift_analysis.has_drift` | `heuristic_analysis.requires_review` + `heuristic_flags` |
| 3 | `return_type_change` 精度 | diff 中同时出现两个关键词就触发 | 只检查 `- public ...` / `+ public ...` 方法签名行，对比提取的返回类型 |
| 4 | Report 补 Line B 信息 | 只有 metrics 表 | 新增 changed files + diff stat |
| 5 | §25 能力矩阵 | `Readable evidence report ❌` | `Basic A/B evidence report ✅` + `Auditor-ready ❌` |
| 6 | `copytree` 排除构建产物 | 全量复制 | 排除 `target/`、`build/`、`.gradle/`、`node_modules/` 等 |

**验证**：
- `_extract_return_type`: 正确解析 `ApiResponse<ConvertResponse>`, `ResponseEntity<?>`, `ResponseEntity<ApiResponse<Void>>`
- 扩展 if-else 但不改返回类型时，新 heuristic 不触发（旧版会误报）✅
- CLI 正常加载 ✅

### 27.7 Status

A/B runner 已完成 hardening。后续改进：
- 支持批量运行多个 case（`codegate ab-batch`）
- Report 增加 Line A inline diff 展示

## 28. Phase 4 P1: Auditor-ready Evidence Report

> Date: 2026-04-25

### 28.1 实现

将 `_generate_report` 替换为 7 章节的 auditor-ready 报告生成器，同时保留 `_generate_basic_report` 向后兼容。

每次 `codegate ab` 运行现在产出：
- `audit_report.md` — 7 章节完整放行报告（主产物）
- `report.md` — 紧凑摘要表（向后兼容）
- `ab_result.json` — 完整 raw 数据

### 28.2 报告结构

| Section | Content |
|---------|--------|
| §1 Clearance Decision | ✅/🔄/⚠️ 加判断依据（drift、coverage、findings、tests、overhead）|
| §2 Risk Summary | 6 维风险表，每项带 🟢/🟡/🔴 状态 |
| §3 Findings Detail | 含 severity、disposition、category、message、contract clause |
| §4 A/B Comparison | 对比表 + Line A/B 各自 changed files、diff stat、phase timings |
| §5 Evidence Chain | 8 项 artifact 路径表，审计方可直接定位 |
| §6 Reproducibility | project、model、build cmd、artifact ID、时间戳 |
| §7 Verdict | 🟢/🟡/🔴 最终判定 |

### 28.3 附带修复

**Maven test summary parser**：
- 问题：`[INFO] Tests run: 12, ...` 中的 `[INFO]` 前缀导致 `total/failures` 解析为 0
- 修复：用 `re.sub` 剥离 `[INFO]`/`[WARNING]`/`[ERROR]` 前缀，用正则提取四字段（total/failures/errors/skipped）
- 新增 `errors` 和 `skipped` 字段
- 取最后一行（汇总行）而非逐 class 行

### 28.4 验证

- 从 P0 验收 artifact (`f919ae5c8a28`) 回放生成 `audit_report.md` — 7 章节完整 ✅
- Parser 修复：mock Maven output `[INFO] Tests run: 12, Failures: 1, Errors: 0, Skipped: 2` 正确解析 ✅
- 模块导入 ✅

> **Note**: 回放的报告中 test count 显示 0，是因为 `ab_result.json` 用旧 parser 生成。下一次 fresh run 会产出正确数字。

### 28.5 验收标准对照

| Criteria | Status |
|----------|--------|
| 单个 `codegate ab` 自动生成 `audit_report.md` | ✅ |
| 不打开 JSON 也能判断是否可放行 | ✅ §1 Clearance + §7 Verdict |
| 报告关键结论都链接到 artifact | ✅ §5 Evidence Chain |
| 支持 approve 和 revise/escalate 两种输出 | ✅ verdict 逻辑分支覆盖 |
| 测试数量等为结构化字段 | ✅ parser 修复，新增 errors/skipped |

### 28.6 P1 Exit Verification (fresh run)

> Case: 错误响应一致性-P1验收
> Run directory: `ab_results/错误响应一致性-p1验收_1777101361`
> Artifact: `d4b7183e045f`
> Report: `ab_results/错误响应一致性-p1验收_1777101361/audit_report.md`

| Criterion | Expected | Actual | Status |
|-----------|----------|--------|--------|
| Line A `test_result.total` | > 0 | **12** | ✅ |
| Line B `test_result.total` | > 0 | **14** | ✅ |
| `errors` + `skipped` 字段存在 | present | `errors=0, skipped=0` | ✅ |
| audit_report §1 测试数 | ≠ 0 | "Tests: **14 pass**, 0 failures" | ✅ |
| audit_report §4 测试差异说明 | present | "Line A produced 12, Line B produced 14" | ✅ |
| Evidence Chain 路径标注 | 存在/缺失标注 | 6 ✅ + 2 "not generated" | ✅ |
| `suppressed_findings.json` | 标注 "no suppression" | "— not generated (no suppression)" | ✅ |
| Heuristic flags | None | None | ✅ |
| Decision | APPROVE | **APPROVE** | ✅ |
| Overhead | ≤ 20% | **7.4%** | ✅ |

**附带修正**：Evidence Chain 增加 Status 列，自动检测 artifact 文件是否存在，缺失文件标注原因。

**结论**：P1 Auditor-ready Evidence Report **正式通过验收**。10/10 criteria 全部 PASS。

## 29. Phase 4 P2: Batch A/B Runner

> Date: 2026-04-25

### 29.1 实现

新增 `codegate ab-batch` CLI 命令，从 YAML 定义批量运行 A/B 评估：

```text
codegate ab-batch --cases eval_cases/image2pdf_cases.yaml
```

新增文件：

| File | Description |
|------|-------------|
| `src/codegate/eval/ab_batch.py` | Batch runner core |
| `eval_cases/image2pdf_cases.yaml` | 3 case 定义（错误响应一致性、DPI、空文件上传） |
| `src/codegate/cli.py` (modified) | Added `codegate ab-batch` command |

### 29.2 首次批量运行结果

> Batch directory: `ab_results/batch_1777102204`
> Batch report: `ab_results/batch_1777102204/batch_report.md`

| # | Case | Decision | Drift | Coverage | Findings | Tests A/B | Overhead |
|---|------|----------|-------|----------|----------|-----------|----------|
| 1 | 错误响应一致性 | ✅ APPROVE | 0 | 100 | 0 | 11/12 | 9.4% |
| 2 | DPI参数保护 | ✅ APPROVE | 0 | 100 | 0 | 11/11 | 16.0% |
| 3 | 测试质量-空文件上传 | ✅ APPROVE | 0 | 100 | 0 | 11/11 | 8.7% |

**聚合指标**：
- Approval rate: **100%** (3/3)
- Average overhead: **11.4%**
- Total findings: **0** (0 blocking, 0 advisory)
- Total duration: **1081.6s** (~18 min for 3 cases)
- False positives: **0**

### 29.3 产出结构

```
ab_results/batch_1777102204/
├── batch_report.md          # 6 章节汇总报告
├── batch_summary.json       # 结构化汇总数据
├── 错误响应一致性_*/
│   ├── audit_report.md      # 单 case 7 章节报告
│   ├── report.md            # 紧凑摘要
│   ├── ab_result.json       # raw 数据
│   └── codegate_artifacts/  # governance 证据
├── dpi参数保护_*/
│   └── ...
└── 测试质量-空文件上传_*/
    └── ...
```

### 29.4 Batch Report 结构

| Section | Content |
|---------|--------|
| §1 Executive Summary | 总案例数、通过/阻断/失败、平均 overhead |
| §2 Case Results | 逐 case 汇总表 |
| §3 Aggregate Findings | findings 总数、blocking/advisory 分布 |
| §4 Individual Reports | 每个 case 的 artifact ID 和 audit_report 路径 |
| §5 Reproducibility | cases file、project、model、batch dir、时间 |
| §6 Batch Verdict | 🟢/🟡/🔴 总体判定 |

### 29.5 P2-2: 4-case 混合批量运行（含阻断场景）

> Batch directory: `ab_results/batch_1777103598`
> Batch report: `ab_results/batch_1777103598/batch_report.md`

新增 Case 4："错误处理链路重构(漂移倾向)"— 高复杂度重构，包含 5 项保留约束。

| # | Case | Decision | Drift | Findings | Tests A/B | Overhead |
|---|------|----------|-------|----------|-----------|----------|
| 1 | 错误响应一致性 | ✅ APPROVE | 0 | 0 | 12/12 | 11.5% |
| 2 | DPI参数保护 | ✅ APPROVE | 0 | 0 | 11/11 | 15.3% |
| 3 | 测试质量-空文件上传 | ✅ APPROVE | 0 | 0 | 11/12 | 10.2% |
| 4 | 错误处理链路重构 | **🔄 REVISE_CODE** | **20** | **1 blocking** | 10/14 | 6.1% |

**Case 4 阻断原因**: `@RequestParam annotation for 'file' was changed`，违反签名保护约束。

**关键价值**: batch 首次同时覆盖 approve (3) + blocked (1)，证明报告的红/绿双路径。

### 29.6 Status

P2 batch runner 完成。已验证：全绿场景 ✅ + 混合场景 ✅ + 红色路径 ✅。

### 29.7 P2-3: Report Refinement

5 项修正，确保团队用户看报告时不困惑：

| # | Fix | Before | After |
|---|-----|--------|-------|
| 1 | Batch report `Blocked Cases` 小节 | 只说 "1/4 blocked" | §7 列出每个 blocked case 的 decision、drift、finding、report path |
| 2 | Audit report verdict 阻断原因 | "Manual review recommended" | `🔴 Implementation blocked. Blocking reason: ...` + 完整 message |
| 3 | `gatekeeper_original_decision` + policy override | 不展示 | §1 callout + §7 note: "Gatekeeper decided APPROVE, overridden by policy. Contract conflict." |
| 4 | Untracked files 标注 | `git diff --stat` 与 files 数量不一致 | 新文件标注 `[new]` 前缀 |
| 5 | Findings 展示 | 单行截断表格 | 摘要表 + 展开详情（Message + Location + Suggestion） |

**验证**：从 Case 4 artifact 回放，5 项修正全部生效。Policy override、blocking reason、suggestion 字段正确展示。

**注意**：§29.5 的 `batch_report.md` 在 P2-3 代码修改前生成，§7 Blocked Cases 缺少 finding message 和 policy override。单 case `audit_report.md` 已包含完整信息（P2-3 修正对 `_generate_report` 已生效），但 batch report 生成器的数据源 `batch_summary.json` 未收集这些字段。

**Post-refinement 修正** (2026-04-25)：
1. 从 Case 4 的 `codegate_artifacts/339813289839/summary.json` + `review_findings.json` 回填 `policy_overridden`、`gatekeeper_original_decision`、`blocking_finding_messages` 到 `batch_summary.json`
2. 用当前代码重新生成 `batch_report.md`
3. `ab_batch.py` finding message 截断从 120→300 字符

**Post-refinement batch report 验证**：
- `batch_report.md` §7 现在包含 Policy override + Finding message ✅
- 旧报告备份为 `batch_report.md.bak`
- 回放脚本：`scripts/regenerate_batch_report.py`

> Case 4 定性修正：不再单纯描述为"executor 漂移"，而是 **contract conflict / drift interception** —— requirement 要求 null 文件检查，但约束禁止修改签名，两者存在张力。CodeGate 暴露了 contract 设计里的冲突并阻止在冲突未澄清时直接 approve。

## 30. Team Alpha Trial Guide

> Date: 2026-04-25
> Document: `docs/TEAM_ALPHA_TRIAL_GUIDE.md`

Alpha 试用指南已作为独立文档发布。内容覆盖：

1. CodeGate 是什么 / 不是什么
2. 适合与不适合试用的任务类型
3. 安装与配置（Python、OpenCode、模型 API）
4. 单 case 评估流程 (`codegate ab`)
5. 批量评估流程 (`codegate ab-batch`)
6. 报告阅读指南 (`audit_report.md` 7 章节 + `batch_report.md` 6 章节)
7. 决策树（approve / revise_code / escalate_to_human）
8. 已知限制（`--answers` workaround、交互式 clarification 未完成、耗时、clean copy）
9. 推荐内测流程




