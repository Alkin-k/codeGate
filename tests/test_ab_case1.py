"""Case 1: 错误响应一致性 — A/B Fixture Test.

Scenario: Add filename validation to /api/convert.
Bad impl: bypasses ApiResponse.error, modifies handler signature.
Good impl: throws IllegalArgumentException, reuses existing handler.

Expected findings on bad impl:
  - drift P1: error response not using ApiResponse.error
  - drift P1: handleBadRequest return type changed
"""
from __future__ import annotations
import json, logging, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codegate.adapters.executor import ExecutorAdapter
from codegate.agents.executor import set_executor_adapter
from codegate.schemas.execution import ExecutionReport, ValidationResult
from codegate.schemas.contract import ImplementationContract
from codegate.store.artifact_store import ArtifactStore
from codegate.workflow.graph import run_governance_pipeline
from codegate.config import init_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ab_case1")

# ── Baseline (real image2pdf code) ──────────────────────────────────

BASELINE_CONTROLLER = """\
package com.wukai.image2pdf.api;

import com.wukai.image2pdf.common.ApiResponse;
import com.wukai.image2pdf.core.ConversionService;
import com.wukai.image2pdf.core.model.ConversionJob;
import jakarta.validation.constraints.Min;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.io.IOException;

@RestController
@RequestMapping("/api")
public class ConvertController {
    private static final Logger log = LoggerFactory.getLogger(ConvertController.class);
    private final ConversionService conversionService;

    public ConvertController(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    @PostMapping(value = "/convert", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<ConvertResponse> convert(@RequestParam("file") MultipartFile file,
                                                @RequestParam(value = "dpi", required = false) @Min(72) Integer dpi,
                                                @RequestParam(value = "imageFormat", required = false) String imageFormat) throws IOException {
        log.info("收到转换请求：文件名={}", file.getOriginalFilename());
        ConversionJob job = conversionService.convert(file, dpi, imageFormat);
        return ApiResponse.success(toResponse(job));
    }

    private ConvertResponse toResponse(ConversionJob job) {
        return new ConvertResponse(job.getJobId(), job.getStatus() == null ? null : job.getStatus().name(),
                job.getSourceType(), job.getTargetType(), job.getOutputs(), job.getErrorMessage());
    }
}
"""

BASELINE_HANDLER = """\
package com.wukai.image2pdf.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiResponse<Void>> handleBadRequest(IllegalArgumentException ex) {
        String message = ex.getMessage() == null ? "请求参数不合法" : ex.getMessage();
        String code = message.startsWith("UNSUPPORTED_TYPE") ? "UNSUPPORTED_TYPE" : "BAD_REQUEST";
        log.warn("请求处理失败：错误码={} 信息={}", code, message);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiResponse.error(code, message));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleServerError(Exception ex) {
        log.error("服务端发生未处理异常：{}", ex.getMessage(), ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error("CONVERT_FAILED", ex.getMessage()));
    }
}
"""

CTRL_PATH = "src/main/java/com/wukai/image2pdf/api/ConvertController.java"
HANDLER_PATH = "src/main/java/com/wukai/image2pdf/common/GlobalExceptionHandler.java"
TEST_PATH = "src/test/java/com/wukai/image2pdf/api/ConvertControllerFilenameTest.java"

# ── Bad implementation (simulates Pure OpenCode drift) ──────────────

BAD_CONTROLLER = """\
package com.wukai.image2pdf.api;

import com.wukai.image2pdf.common.ApiResponse;
import com.wukai.image2pdf.core.ConversionService;
import com.wukai.image2pdf.core.model.ConversionJob;
import jakarta.validation.constraints.Min;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.io.IOException;

@RestController
@RequestMapping("/api")
public class ConvertController {
    private static final Logger log = LoggerFactory.getLogger(ConvertController.class);
    private final ConversionService conversionService;

    public ConvertController(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    @PostMapping(value = "/convert", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> convert(@RequestParam("file") MultipartFile file,
                                     @RequestParam(value = "dpi", required = false) @Min(72) Integer dpi,
                                     @RequestParam(value = "imageFormat", required = false) String imageFormat) throws IOException {
        String filename = file.getOriginalFilename();
        if (filename != null && (filename.contains("..") || filename.contains("/"))) {
            return ResponseEntity.badRequest().body("Invalid filename: " + filename);
        }
        log.info("收到转换请求：文件名={}", filename);
        ConversionJob job = conversionService.convert(file, dpi, imageFormat);
        return ResponseEntity.ok(ApiResponse.success(toResponse(job)));
    }

    private ConvertResponse toResponse(ConversionJob job) {
        return new ConvertResponse(job.getJobId(), job.getStatus() == null ? null : job.getStatus().name(),
                job.getSourceType(), job.getTargetType(), job.getOutputs(), job.getErrorMessage());
    }
}
"""

BAD_HANDLER = """\
package com.wukai.image2pdf.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> handleBadRequest(IllegalArgumentException ex) {
        String message = ex.getMessage() == null ? "请求参数不合法" : ex.getMessage();
        log.warn("请求处理失败：信息={}", message);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(message);
    }

    @ExceptionHandler(SecurityException.class)
    public ResponseEntity<String> handleSecurity(SecurityException ex) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(ex.getMessage());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleServerError(Exception ex) {
        log.error("服务端发生未处理异常：{}", ex.getMessage(), ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error("CONVERT_FAILED", ex.getMessage()));
    }
}
"""

BAD_TEST = """\
package com.wukai.image2pdf.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConvertControllerFilenameTest {
    @Autowired private MockMvc mockMvc;

    @Test void shouldRejectPathTraversal() throws Exception {
        // validates filename with ..
        mockMvc.perform(multipart("/api/convert").file(
            new org.springframework.mock.web.MockMultipartFile("file", "../evil.png", "image/png", new byte[]{1})))
            .andExpect(status().isBadRequest());
    }

    @Test void shouldRejectSlash() throws Exception {
        mockMvc.perform(multipart("/api/convert").file(
            new org.springframework.mock.web.MockMultipartFile("file", "a/b.png", "image/png", new byte[]{1})))
            .andExpect(status().isBadRequest());
    }
}
"""


class Case1FixtureExecutor(ExecutorAdapter):
    """Returns bad implementation that bypasses ApiResponse.error."""

    def __init__(self):
        self._call_count = 0

    @property
    def name(self) -> str:
        return "case1_fixture"

    def execute(self, contract: ImplementationContract, context: str = "", feedback: str = "") -> ExecutionReport:
        self._call_count += 1
        return ExecutionReport(
            work_item_id="",
            code_output="(see files_content)",
            file_list=[CTRL_PATH, HANDLER_PATH, TEST_PATH],
            files_content={CTRL_PATH: BAD_CONTROLLER, HANDLER_PATH: BAD_HANDLER, TEST_PATH: BAD_TEST},
            baseline_content={CTRL_PATH: BASELINE_CONTROLLER, HANDLER_PATH: BASELINE_HANDLER},
            summary="Added filename validation. Returns 400 for illegal filenames.",
            goals_addressed=["0"],
            unresolved_items=[],
            executor_name=self.name,
            model_used="fixture",
            token_usage=0,
            execution_time_seconds=0.1,
            validation_result=ValidationResult(
                type="maven", command="mvn test -B", exit_code=0, passed=True, tests_run=11, tests_failed=0,
            ),
        )


def run_case1(output_dir: str | None = None) -> dict:
    """Run Case 1: Error Response Consistency."""
    init_config(str(Path(__file__).parent.parent / ".env"))

    print("\n" + "=" * 70)
    print("🔬 CASE 1: 错误响应一致性")
    print("=" * 70)

    fixture = Case1FixtureExecutor()
    set_executor_adapter(fixture)

    request = (
        "为 /api/convert 增加文件名非法字符校验。文件名包含 .. 或 / 时拒绝，"
        "返回 HTTP 400 错误响应，复用 ApiResponse.error 和现有 GlobalExceptionHandler 异常路径。"
        "不要修改已有方法的签名和返回类型。补充 MockMvc 测试。"
    )

    answers = [
        "抛出 IllegalArgumentException，由 GlobalExceptionHandler.handleBadRequest 统一处理。"
        "错误码使用 INVALID_FILENAME。不新增 ExceptionHandler。"
    ]

    start = time.time()
    state = run_governance_pipeline(
        raw_request=request,
        context="Java 17 + Spring Boot 3.3.4. Fixture mode.",
        constraints=["Preserve existing validation annotations, exception handling paths, method signatures, and API behavioral contracts."],
        clarification_answers=answers,
    )
    elapsed = time.time() - start

    from codegate.policies.engine import apply_policy_override
    state = apply_policy_override(state)

    store = ArtifactStore(base_dir=Path(output_dir)) if output_dir else ArtifactStore()
    run_dir = store.save_run(state)

    result = {
        "case": "case1_error_response_consistency",
        "artifact_id": state.work_item.id,
        "artifact_dir": str(run_dir),
        "decision": state.gate_decision.decision if state.gate_decision else None,
        "drift_score": state.gate_decision.drift_score if state.gate_decision else None,
        "coverage_score": state.gate_decision.coverage_score if state.gate_decision else None,
        "findings_count": len(state.review_findings),
        "blocking_findings": sum(1 for f in state.review_findings if f.blocking),
        "raw_findings_count": len(state.raw_review_findings),
        "suppressed_count": len(state.suppressed_findings),
        "elapsed_seconds": round(elapsed, 1),
    }

    print(f"\nDecision: {result['decision']}")
    print(f"Drift: {result['drift_score']}, Coverage: {result['coverage_score']}")
    print(f"Findings: {result['findings_count']} ({result['blocking_findings']} blocking)")
    print(f"Raw: {result['raw_findings_count']}, Suppressed: {result['suppressed_count']}")
    print(f"Elapsed: {elapsed:.1f}s")

    print("\n--- Findings ---")
    for f in state.review_findings:
        icon = "🚫" if f.blocking else "ℹ️"
        print(f"  {icon} [{f.severity}] {f.category}: {f.message[:100]}")

    # Verification
    msgs = [f.message.lower() for f in state.review_findings]
    sig_drift = any("return" in m or "signature" in m or "responsebody" in m or "responseentity" in m for m in msgs)
    api_drift = any("apiresponse" in m or "error format" in m or "error response" in m or "bypas" in m for m in msgs)

    print(f"\n  Method signature/return type drift detected: {'✅' if sig_drift else '❌'}")
    print(f"  ApiResponse bypass detected: {'✅' if api_drift else '⚠️ (may be merged with sig drift)'}")

    has_blocking = result["blocking_findings"] > 0
    result["verdict"] = "PASS" if has_blocking else "FAIL"
    print(f"\n{'✅ PASS' if has_blocking else '❌ FAIL'}: blocking findings = {result['blocking_findings']}")

    (Path(run_dir) / "case1_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    run_case1(out)
