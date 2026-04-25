"""Forced Ghost Pattern — End-to-End Verification Test.

This test validates that the structural pre-check + post-filter pipeline
correctly suppresses false positive "ghost pattern" findings while keeping
true positive baseline drift findings.

The scenario:
  iter1: executor ADDS HandlerMethodValidationException handler (not in baseline)
  iter2: executor REMOVES the handler AND REMOVES @Min(72) (which IS in baseline)

Expected result:
  - @Min(72) removal: KEPT as blocking finding (true positive)
  - HandlerMethodValidationException removal: SUPPRESSED (ghost pattern)

This uses a FixtureExecutor to control executor output while running the
REAL reviewer LLM + post-filter pipeline.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

# Ensure codegate is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codegate.adapters.executor import ExecutorAdapter
from codegate.agents.executor import set_executor_adapter
from codegate.schemas.execution import ExecutionReport, ValidationResult
from codegate.schemas.contract import ImplementationContract
from codegate.store.artifact_store import ArtifactStore
from codegate.workflow.graph import run_governance_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ghost_pattern_test")


# =============================================================================
# Fixture Data — simulating the image2pdf DPI scenario
# =============================================================================

# The REAL baseline (git HEAD) — has @Min(72), NO HandlerMethodValidationException
BASELINE_CONTROLLER = """\
package com.wukai.image2pdf.api;

import jakarta.validation.constraints.Min;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class ConvertController {

    @PostMapping("/api/convert")
    public ApiResponse<ConvertResponse> convert(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "dpi", required = false) @Min(72) Integer dpi,
            @RequestParam(value = "imageFormat", required = false) String imageFormat) {
        // ... existing implementation
        return null;
    }
}
"""

BASELINE_HANDLER = """\
package com.wukai.image2pdf.common;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiResponse<Void>> handleBadRequest(IllegalArgumentException ex) {
        String message = ex.getMessage() == null ? "请求参数不合法" : ex.getMessage();
        String code = message.startsWith("UNSUPPORTED_TYPE") ? "UNSUPPORTED_TYPE" : "BAD_REQUEST";
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiResponse.error(code, message));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleServerError(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error("CONVERT_FAILED", ex.getMessage()));
    }
}
"""

# iter1 output: ADDS @Max(600) and ADDS HandlerMethodValidationException handler
ITER1_CONTROLLER = """\
package com.wukai.image2pdf.api;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class ConvertController {

    @PostMapping("/api/convert")
    public ApiResponse<ConvertResponse> convert(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "dpi", required = false) @Min(72) @Max(600) Integer dpi,
            @RequestParam(value = "imageFormat", required = false) String imageFormat) {
        // ... existing implementation
        return null;
    }
}
"""

ITER1_HANDLER = """\
package com.wukai.image2pdf.common;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiResponse<Void>> handleBadRequest(IllegalArgumentException ex) {
        String message = ex.getMessage() == null ? "请求参数不合法" : ex.getMessage();
        String code = message.startsWith("UNSUPPORTED_TYPE") ? "UNSUPPORTED_TYPE" : "BAD_REQUEST";
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiResponse.error(code, message));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiResponse<Void>> handleMethodValidation(HandlerMethodValidationException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiResponse.error("INVALID_DPI", "DPI must be between 72 and 600"));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleServerError(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error("CONVERT_FAILED", ex.getMessage()));
    }
}
"""

# iter2 output: REMOVES @Min(72), REMOVES HandlerMethodValidationException handler,
# uses manual if-check instead
ITER2_CONTROLLER = """\
package com.wukai.image2pdf.api;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class ConvertController {

    @PostMapping("/api/convert")
    public ApiResponse<ConvertResponse> convert(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "dpi", required = false) Integer dpi,
            @RequestParam(value = "imageFormat", required = false) String imageFormat) {
        if (dpi != null && (dpi < 72 || dpi > 600)) {
            throw new IllegalArgumentException("INVALID_DPI: dpi must be between 72 and 600");
        }
        // ... existing implementation
        return null;
    }
}
"""

ITER2_HANDLER = """\
package com.wukai.image2pdf.common;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiResponse<Void>> handleBadRequest(IllegalArgumentException ex) {
        String message = ex.getMessage() == null ? "请求参数不合法" : ex.getMessage();
        String code;
        if (message.startsWith("INVALID_DPI")) {
            code = "INVALID_DPI";
        } else if (message.startsWith("UNSUPPORTED_TYPE")) {
            code = "UNSUPPORTED_TYPE";
        } else {
            code = "BAD_REQUEST";
        }
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiResponse.error(code, message));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleServerError(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error("CONVERT_FAILED", ex.getMessage()));
    }
}
"""

CONTROLLER_PATH = "src/main/java/com/wukai/image2pdf/api/ConvertController.java"
HANDLER_PATH = "src/main/java/com/wukai/image2pdf/common/GlobalExceptionHandler.java"
TEST_PATH = "src/test/java/com/wukai/image2pdf/api/ConvertControllerDpiValidationTest.java"

TEST_FILE_CONTENT = """\
// Placeholder test file for fixture executor
package com.wukai.image2pdf.api;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ConvertControllerDpiValidationTest {
    @Test void testDpi72() { /* pass */ }
    @Test void testDpi600() { /* pass */ }
    @Test void testDpi71() { /* pass */ }
    @Test void testDpi601() { /* pass */ }
    @Test void testDpiMissing() { /* pass */ }
}
"""


# =============================================================================
# Fixture Executor
# =============================================================================

class GhostPatternFixtureExecutor(ExecutorAdapter):
    """A fixture executor that returns controlled output for each iteration.

    iter1: Adds @Max(600) + HandlerMethodValidationException handler
    iter2: Removes @Min(72) + removes handler (switches to manual if-check)

    Both iterations always report baseline_content from the REAL baseline.
    """

    def __init__(self):
        self._call_count = 0

    @property
    def name(self) -> str:
        return "ghost_pattern_fixture"

    def execute(
        self,
        contract: ImplementationContract,
        context: str = "",
        feedback: str = "",
    ) -> ExecutionReport:
        self._call_count += 1
        iteration = self._call_count

        logger.info(f"[FIXTURE] Executing iteration {iteration}")

        if iteration == 1:
            files_content = {
                CONTROLLER_PATH: ITER1_CONTROLLER,
                HANDLER_PATH: ITER1_HANDLER,
                TEST_PATH: TEST_FILE_CONTENT,
            }
            summary = (
                "Added @Max(600) annotation to dpi parameter alongside existing @Min(72). "
                "Added HandlerMethodValidationException handler for validation errors. "
                "Added 5 MockMvc test cases."
            )
        else:
            # iter2+: the "bad" iteration that removes baseline patterns
            files_content = {
                CONTROLLER_PATH: ITER2_CONTROLLER,
                HANDLER_PATH: ITER2_HANDLER,
                TEST_PATH: TEST_FILE_CONTENT,
            }
            summary = (
                "Removed @Min(72) and @Max(600) annotations. "
                "Replaced with manual if-check for dpi validation. "
                "Removed HandlerMethodValidationException handler (no longer needed). "
                "Modified IllegalArgumentException handler to recognize INVALID_DPI code."
            )

        # Baseline content is ALWAYS the clean baseline (git HEAD)
        baseline_content = {
            CONTROLLER_PATH: BASELINE_CONTROLLER,
            HANDLER_PATH: BASELINE_HANDLER,
        }

        return ExecutionReport(
            work_item_id="",
            code_output="(see files_content)",
            file_list=list(files_content.keys()),
            files_content=files_content,
            baseline_content=baseline_content,
            summary=summary,
            goals_addressed=["0", "1"],
            unresolved_items=[],
            executor_name=self.name,
            model_used="fixture",
            token_usage=0,
            execution_time_seconds=0.1,
            validation_result=ValidationResult(
                type="maven",
                command="mvn test -B",
                exit_code=0,
                passed=True,
                tests_run=14,
                tests_failed=0,
            ),
        )


# =============================================================================
# Main test execution
# =============================================================================

def run_ghost_pattern_test(output_dir: str | None = None) -> dict:
    """Run the forced ghost pattern e2e test.

    Returns a dict with test results for verification.
    """
    print("\n" + "=" * 70)
    print("🔬 FORCED GHOST PATTERN — END-TO-END VERIFICATION")
    print("=" * 70)

    # Set up fixture executor
    fixture = GhostPatternFixtureExecutor()
    set_executor_adapter(fixture)

    # Run the full governance pipeline
    # The pipeline will:
    #   1. Spec council (real LLM) → generates contract
    #   2. Executor (fixture) → returns iter1 output
    #   3. Reviewer (real LLM) → reviews with structural pre-check
    #   4. Gatekeeper (real LLM) → likely revise_code (iter1 has new handler)
    #   5. Executor (fixture) → returns iter2 output
    #   6. Reviewer (real LLM) → reviews with structural pre-check + post-filter
    #   7. Gatekeeper (real LLM) → final decision

    request = (
        "为 /api/convert 增加 dpi 参数上限校验：当 dpi 不为空时，只允许 72 <= dpi <= 600；"
        "dpi < 72 或 dpi > 600 时返回 HTTP 400；错误响应使用现有 ApiResponse.error 格式，"
        "code 使用 INVALID_DPI；不进入 ConversionService.convert；"
        "补充 MockMvc 测试，覆盖 dpi=72、dpi=600、dpi=71、dpi=601、dpi 缺失；"
        "不要新增依赖；不要修改 ConversionService；不要影响已有 imageFormat 和 file-size 行为。"
    )

    constraints = [
        "不要移除已有的 @Min(72) 注解，在其基础上增加 @Max(600) 或手动上限校验",
        "Preserve existing validation annotations, exception handling paths, "
        "method signatures, and API behavioral contracts.",
    ]

    # Pre-fill clarification answers to skip spec council Q&A phase
    answers = [
        "Use @Max(600) annotation alongside existing @Min(72). "
        "Use ApiResponse.error(\"INVALID_DPI\", message) for error responses. "
        "dpi is Integer type (nullable). Validation happens in controller layer.",
    ]

    start = time.time()
    final_state = run_governance_pipeline(
        raw_request=request,
        context="Java 17 + Spring Boot 3.3.4 Maven project. Real executor disabled — fixture mode.",
        constraints=constraints,
        clarification_answers=answers,
        risk_level="medium",
    )
    elapsed = time.time() - start

    # Save artifacts
    if output_dir:
        store = ArtifactStore(base_dir=Path(output_dir))
    else:
        store = ArtifactStore()
    run_dir = store.save_run(final_state)

    # Analyze results
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)

    result = {
        "artifact_id": final_state.work_item.id,
        "artifact_dir": str(run_dir),
        "decision": final_state.gate_decision.decision if final_state.gate_decision else None,
        "drift_score": final_state.gate_decision.drift_score if final_state.gate_decision else None,
        "coverage_score": final_state.gate_decision.coverage_score if final_state.gate_decision else None,
        "completed_iterations": len(final_state.iteration_history),
        "total_findings": len(final_state.review_findings),
        "blocking_findings": sum(1 for f in final_state.review_findings if f.blocking),
        "elapsed_seconds": elapsed,
        "fixture_calls": fixture._call_count,
    }

    print(f"Decision: {result['decision']}")
    print(f"Drift: {result['drift_score']}, Coverage: {result['coverage_score']}")
    print(f"Iterations: {result['completed_iterations']}")
    print(f"Findings: {result['total_findings']} ({result['blocking_findings']} blocking)")
    print(f"Fixture executor calls: {result['fixture_calls']}")
    print(f"Elapsed: {elapsed:.1f}s")

    print("\n--- Final Findings ---")
    for i, f in enumerate(final_state.review_findings):
        status = "🚫" if f.blocking else "ℹ️"
        print(f"  {status} [{f.severity}] {f.message[:100]}")

    # Verify expectations
    print("\n--- Verification ---")
    findings_messages = [f.message.lower() for f in final_state.review_findings]

    # Check 1: @Min(72) removal should be a finding
    min72_found = any("@min" in m or "min(72)" in m for m in findings_messages)
    print(f"  @Min(72) removal detected: {'✅' if min72_found else '❌'} (expected: ✅)")

    # Check 2: HandlerMethodValidationException should NOT be in final findings
    handler_found = any("handlermethodvalidation" in m for m in findings_messages)
    print(f"  HandlerMethodValidationException ghost suppressed: {'✅' if not handler_found else '❌'} (expected: ✅)")

    # Overall verdict
    if min72_found and not handler_found:
        print("\n✅✅✅ TEST PASSED: Ghost pattern correctly suppressed, real drift preserved ✅✅✅")
        result["verdict"] = "PASS"
    elif min72_found and handler_found:
        print("\n⚠️ PARTIAL: @Min(72) drift detected but ghost pattern NOT suppressed")
        result["verdict"] = "PARTIAL"
    elif not min72_found and not handler_found:
        print("\n⚠️ PARTIAL: Ghost suppressed but @Min(72) drift also missed")
        result["verdict"] = "PARTIAL"
    else:
        print("\n❌ FAIL: Unexpected result")
        result["verdict"] = "FAIL"

    # Save test result
    result_path = run_dir / "ghost_pattern_test_result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nResults saved to: {result_path}")

    return result


if __name__ == "__main__":
    output_dir = sys.argv[1] if len(sys.argv) > 1 else None
    run_ghost_pattern_test(output_dir)
