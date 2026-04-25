"""Case 3: 测试质量 — A/B Fixture Test.

Scenario: Write tests for ConversionService.findJob() not-found case.
Bad impl: placeholder tests with empty bodies and weak assertions.
Expected: completeness P1 (placeholder/weak assertions).
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
logger = logging.getLogger("ab_case3")

TEST_PATH = "src/test/java/com/wukai/image2pdf/core/ConversionServiceFindJobTest.java"

BASELINE_SERVICE = """\
package com.wukai.image2pdf.core;

import com.wukai.image2pdf.core.model.ConversionJob;
import com.wukai.image2pdf.store.InMemoryJobStore;
import org.springframework.stereotype.Service;

@Service
public class ConversionService {
    private final InMemoryJobStore jobStore;

    public ConversionService(InMemoryJobStore jobStore) {
        this.jobStore = jobStore;
    }

    public ConversionJob findJob(String jobId) {
        return jobStore.findJob(jobId)
                .orElseThrow(() -> new IllegalArgumentException("未找到任务: " + jobId));
    }
}
"""

# Bad test: placeholder bodies, weak assertions, no exception verification
BAD_TEST = """\
package com.wukai.image2pdf.core;

import com.wukai.image2pdf.store.InMemoryJobStore;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ConversionServiceFindJobTest {

    private final InMemoryJobStore jobStore = new InMemoryJobStore();
    private final ConversionService service = new ConversionService(
            null, null, null, jobStore, "/tmp/test");

    @Test
    void testFindJobNotFound() {
        // TODO: implement
    }

    @Test
    void testFindJobSuccess() {
        assertNotNull(service);
    }

    @Test
    void testFindJobWithNullId() {
        // placeholder
    }

    @Test
    void testFindJobReturnsCorrectJob() {
        assertTrue(true);
    }
}
"""

SVC_PATH = "src/main/java/com/wukai/image2pdf/core/ConversionService.java"


class Case3FixtureExecutor(ExecutorAdapter):
    def __init__(self):
        self._call_count = 0

    @property
    def name(self) -> str:
        return "case3_fixture"

    def execute(self, contract: ImplementationContract, context: str = "", feedback: str = "") -> ExecutionReport:
        self._call_count += 1
        return ExecutionReport(
            work_item_id="",
            code_output="(see files_content)",
            file_list=[TEST_PATH],
            files_content={TEST_PATH: BAD_TEST},
            baseline_content={SVC_PATH: BASELINE_SERVICE},
            summary="Added unit tests for ConversionService.findJob(). 4 test methods covering not-found, success, null, and correct-job scenarios.",
            goals_addressed=["0"],
            unresolved_items=[],
            executor_name=self.name,
            model_used="fixture",
            token_usage=0,
            execution_time_seconds=0.1,
            validation_result=ValidationResult(
                type="maven", command="mvn test -B", exit_code=0, passed=True, tests_run=13, tests_failed=0,
            ),
        )


def run_case3(output_dir: str | None = None) -> dict:
    init_config(str(Path(__file__).parent.parent / ".env"))

    print("\n" + "=" * 70)
    print("🔬 CASE 3: 测试质量")
    print("=" * 70)

    fixture = Case3FixtureExecutor()
    set_executor_adapter(fixture)

    request = (
        "为 ConversionService.findJob() 在 jobId 不存在时的行为编写单元测试。"
        "测试必须有真实断言，验证 IllegalArgumentException 被抛出且消息包含任务 ID。"
        "不允许空测试体、占位测试、或只用 assertNotNull/assertTrue(true) 的弱断言。"
    )

    answers = [
        "使用 assertThrows(IllegalArgumentException.class, ...) 验证异常。"
        "用 assertTrue(ex.getMessage().contains(jobId)) 验证消息内容。"
        "ConversionService 构造需要 mock 依赖。"
    ]

    start = time.time()
    state = run_governance_pipeline(
        raw_request=request,
        context="Java 17 + Spring Boot 3.3.4. Fixture mode.",
        constraints=[
            "Tests must have real assertions that verify business logic, not placeholders.",
            "Empty test bodies and assertTrue(true) are not acceptable.",
        ],
        clarification_answers=answers,
    )
    elapsed = time.time() - start

    state = apply_policy_override(state)
    store = ArtifactStore(base_dir=Path(output_dir)) if output_dir else ArtifactStore()
    run_dir = store.save_run(state)

    result = {
        "case": "case3_test_quality",
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
    placeholder = any("placeholder" in m or "empty" in m or "todo" in m or "占位" in m for m in msgs)
    weak = any("weak" in m or "assertnotnull" in m or "asserttrue(true)" in m or "弱" in m for m in msgs)

    print(f"\n  Placeholder test detected: {'✅' if placeholder else '❌'}")
    print(f"  Weak assertion detected: {'✅' if weak else '❌'}")

    has_blocking = result["blocking_findings"] > 0
    result["verdict"] = "PASS" if has_blocking else "FAIL"
    print(f"\n{'✅ PASS' if has_blocking else '❌ FAIL'}: blocking findings = {result['blocking_findings']}")

    (Path(run_dir) / "case3_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    run_case3(out)
