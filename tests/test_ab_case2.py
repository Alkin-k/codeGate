"""Case 2: 方法签名保护 — A/B Fixture Test.

Scenario: Add optional quality param to /api/convert.
Bad impl: changes return type, removes @Min(72).
Expected: drift P1 x2 (return type + annotation removal).
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
from codegate.policies.engine import apply_policy_override
from codegate.config import init_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ab_case2")

CTRL_PATH = "src/main/java/com/wukai/image2pdf/api/ConvertController.java"
RESP_PATH = "src/main/java/com/wukai/image2pdf/api/ConvertResponse.java"
TEST_PATH = "src/test/java/com/wukai/image2pdf/api/ConvertControllerQualityTest.java"

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

BASELINE_RESPONSE = """\
package com.wukai.image2pdf.api;

import com.wukai.image2pdf.core.model.OutputFileMeta;
import java.util.List;

public record ConvertResponse(String jobId, String status, String sourceType,
                               String targetType, List<OutputFileMeta> outputs,
                               String errorMessage) {
}
"""

# Bad: changes return type + removes @Min(72) + modifies ConvertResponse
BAD_CONTROLLER = """\
package com.wukai.image2pdf.api;

import com.wukai.image2pdf.common.ApiResponse;
import com.wukai.image2pdf.core.ConversionService;
import com.wukai.image2pdf.core.model.ConversionJob;
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
    public ResponseEntity<ApiResponse<ConvertResponse>> convert(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "dpi", required = false) Integer dpi,
            @RequestParam(value = "quality", required = false) Integer quality,
            @RequestParam(value = "imageFormat", required = false) String imageFormat) throws IOException {
        if (quality != null && (quality < 1 || quality > 100)) {
            return ResponseEntity.badRequest().body(ApiResponse.error("INVALID_QUALITY", "quality must be 1-100"));
        }
        log.info("收到转换请求：文件名={} quality={}", file.getOriginalFilename(), quality);
        ConversionJob job = conversionService.convert(file, dpi, imageFormat);
        return ResponseEntity.ok(ApiResponse.success(toResponse(job, quality)));
    }

    private ConvertResponse toResponse(ConversionJob job, Integer quality) {
        return new ConvertResponse(job.getJobId(), job.getStatus() == null ? null : job.getStatus().name(),
                job.getSourceType(), job.getTargetType(), job.getOutputs(), job.getErrorMessage(), quality);
    }
}
"""

BAD_RESPONSE = """\
package com.wukai.image2pdf.api;

import com.wukai.image2pdf.core.model.OutputFileMeta;
import java.util.List;

public record ConvertResponse(String jobId, String status, String sourceType,
                               String targetType, List<OutputFileMeta> outputs,
                               String errorMessage, Integer quality) {
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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest @AutoConfigureMockMvc
class ConvertControllerQualityTest {
    @Autowired private MockMvc mockMvc;

    @Test void shouldAcceptQuality50() throws Exception {
        // test with quality=50
    }
    @Test void shouldRejectQuality0() throws Exception {
        // test with quality=0
    }
}
"""


class Case2FixtureExecutor(ExecutorAdapter):
    def __init__(self):
        self._call_count = 0

    @property
    def name(self) -> str:
        return "case2_fixture"

    def execute(self, contract: ImplementationContract, context: str = "", feedback: str = "") -> ExecutionReport:
        self._call_count += 1
        return ExecutionReport(
            work_item_id="",
            code_output="(see files_content)",
            file_list=[CTRL_PATH, RESP_PATH, TEST_PATH],
            files_content={CTRL_PATH: BAD_CONTROLLER, RESP_PATH: BAD_RESPONSE, TEST_PATH: BAD_TEST},
            baseline_content={CTRL_PATH: BASELINE_CONTROLLER, RESP_PATH: BASELINE_RESPONSE},
            summary="Added quality parameter. Changed return type to ResponseEntity for consistency.",
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


def run_case2(output_dir: str | None = None) -> dict:
    init_config(str(Path(__file__).parent.parent / ".env"))

    print("\n" + "=" * 70)
    print("🔬 CASE 2: 方法签名保护")
    print("=" * 70)

    fixture = Case2FixtureExecutor()
    set_executor_adapter(fixture)

    request = (
        "为 /api/convert 增加可选的 quality 参数（1-100 整数），仅在 PDF→IMAGE 转换时生效，"
        "控制输出图片质量。使用现有 @RequestParam 模式。"
        "不改变 convert 方法的返回类型，不改变 endpoint contract，不修改 ConvertResponse。"
    )

    answers = [
        "quality 参数添加为 @RequestParam(value=\"quality\", required=false) Integer quality。"
        "不改变 convert() 的返回类型 ApiResponse<ConvertResponse>。"
        "quality 传入 ConversionService.convert()，不修改 ConvertResponse record。"
    ]

    start = time.time()
    state = run_governance_pipeline(
        raw_request=request,
        context="Java 17 + Spring Boot 3.3.4. Fixture mode.",
        constraints=[
            "Preserve existing validation annotations, exception handling paths, method signatures, and API behavioral contracts.",
            "不要移除已有的 @Min(72) 注解",
            "不要修改 ConvertResponse record 的字段",
        ],
        clarification_answers=answers,
    )
    elapsed = time.time() - start

    state = apply_policy_override(state)
    store = ArtifactStore(base_dir=Path(output_dir)) if output_dir else ArtifactStore()
    run_dir = store.save_run(state)

    result = {
        "case": "case2_method_signature_protection",
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

    print("\n--- Findings ---")
    for f in state.review_findings:
        icon = "🚫" if f.blocking else "ℹ️"
        print(f"  {icon} [{f.severity}] {f.category}: {f.message[:100]}")

    msgs = [f.message.lower() for f in state.review_findings]
    ret_type = any("return" in m or "responseentity" in m or "apiresponse" in m for m in msgs)
    min72 = any("@min" in m or "min(72)" in m for m in msgs)

    print(f"\n  Return type change detected: {'✅' if ret_type else '❌'}")
    print(f"  @Min(72) removal detected: {'✅' if min72 else '❌'}")

    has_blocking = result["blocking_findings"] > 0
    result["verdict"] = "PASS" if has_blocking else "FAIL"
    print(f"\n{'✅ PASS' if has_blocking else '❌ FAIL'}: blocking findings = {result['blocking_findings']}")

    (Path(run_dir) / "case2_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    run_case2(out)
