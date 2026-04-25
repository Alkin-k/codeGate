"""Benchmark V2 — measures governance OVERHEAD, not governance vs baseline.

Key differences from V1:
  - Separates governance overhead (spec + review + gate) from execution time
  - Tracks executor time independently
  - Risk-level classification determines governance thresholds (not governance depth)
  - Measures: contract quality, drift detection, gate precision
  - Does NOT claim governance "correctness" is comparable to baseline

Usage:
    python -m codegate.benchmark --cases all
    python -m codegate.benchmark --cases case_1,case_2
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from codegate.config import get_config, init_config
from codegate.llm import call_llm_json, call_llm
from codegate.workflow.graph import run_governance_pipeline
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


# ============================================================
# Benchmark Case Definition
# ============================================================

@dataclass
class BenchmarkCase:
    """A single benchmark test case."""
    id: str
    name: str
    requirement: str
    context: str = ""
    eval_criteria: list[str] = field(default_factory=list)
    clarification_answers: list[str] = field(default_factory=list)
    risk_level: str = "medium"  # low / medium / high
    difficulty: str = "medium"
    description: str = ""       # Design intent / target rules


@dataclass
class GovernanceMetrics:
    """Detailed metrics for one governance run."""
    case_id: str

    # --- Timing (seconds) ---
    spec_time: float = 0.0       # Spec Council only
    executor_time: float = 0.0   # Executor only (NOT governance overhead)
    review_time: float = 0.0     # Reviewer only
    gate_time: float = 0.0       # Gatekeeper only
    policy_time: float = 0.0     # Policy Engine
    total_time: float = 0.0      # Wall-clock total

    # Derived: governance overhead = total - executor
    @property
    def governance_overhead(self) -> float:
        return self.total_time - self.executor_time

    # --- Tokens ---
    spec_tokens: int = 0
    executor_tokens: int = 0
    review_tokens: int = 0
    gate_tokens: int = 0
    total_tokens: int = 0

    @property
    def governance_tokens(self) -> int:
        """Tokens consumed by governance layer only (excluding executor)."""
        return self.total_tokens - self.executor_tokens

    # --- Quality metrics ---
    contract_goals: int = 0
    contract_criteria: int = 0
    findings_count: int = 0
    blocking_count: int = 0
    drift_score: int = 0
    coverage_score: int = 0
    gate_decision: str = ""
    iterations: int = 1
    risk_level: str = ""

    # --- Error ---
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "risk_level": self.risk_level,
            "timing": {
                "total_seconds": round(self.total_time, 1),
                "governance_overhead_seconds": round(self.governance_overhead, 1),
                "executor_seconds": round(self.executor_time, 1),
                "breakdown": {
                    "spec_council": round(self.spec_time, 1),
                    "executor": round(self.executor_time, 1),
                    "reviewer": round(self.review_time, 1),
                    "gatekeeper": round(self.gate_time, 1),
                },
            },
            "tokens": {
                "total": self.total_tokens,
                "governance_only": self.governance_tokens,
                "executor_only": self.executor_tokens,
                "breakdown": {
                    "spec_council": self.spec_tokens,
                    "executor": self.executor_tokens,
                    "reviewer": self.review_tokens,
                    "gatekeeper": self.gate_tokens,
                },
            },
            "quality": {
                "contract_goals": self.contract_goals,
                "contract_criteria": self.contract_criteria,
                "drift_score": self.drift_score,
                "coverage_score": self.coverage_score,
                "findings": self.findings_count,
                "blocking": self.blocking_count,
                "gate_decision": self.gate_decision,
                "iterations": self.iterations,
            },
            "error": self.error,
        }


# ============================================================
# Built-in Test Cases
# ============================================================

BUILTIN_CASES = [
    BenchmarkCase(
        id="case_1_fibonacci",
        name="Simple & Clear — Fibonacci",
        requirement="写一个 Python 函数，计算斐波那契数列的第 N 项，要求支持 N=0 的情况，不使用递归",
        eval_criteria=[
            "函数签名正确",
            "支持 N=0 返回 0",
            "支持 N=1 返回 1",
            "使用迭代而非递归",
            "有基本的参数校验",
        ],
        clarification_answers=[
            "不需要缓存优化",
            "返回整数类型",
            "N 不会超过 1000",
        ],
        risk_level="low",
        difficulty="easy",
    ),
    BenchmarkCase(
        id="case_2_auth",
        name="Ambiguous — Add Authentication",
        requirement="给这个 Flask 应用加用户认证功能",
        context="项目是一个 Flask REST API，目前没有任何认证机制。有 users 表但没有 password 字段。",
        eval_criteria=[
            "选择了一种认证方案（JWT/Session/OAuth）",
            "添加了用户注册端点",
            "添加了用户登录端点",
            "实现了密码哈希存储",
            "保护了现有 API 端点",
        ],
        clarification_answers=[
            "用 JWT 认证",
            "需要注册和登录功能",
            "只需要邮箱+密码，不需要 OAuth",
            "所有 API 都需要认证，除了注册和登录",
        ],
        risk_level="medium",
        difficulty="medium",
    ),
    BenchmarkCase(
        id="case_3_cache",
        name="Hidden Constraint — Cache System",
        requirement="给项目实现一个缓存系统，提高 API 响应速度",
        context="项目是分布式部署的微服务，运行在 3 个 Kubernetes 节点上。",
        eval_criteria=[
            "识别到分布式场景不能用单机缓存",
            "选择了分布式缓存方案（Redis 等）",
            "实现了缓存失效策略",
            "处理了缓存穿透/击穿",
            "没有引入单点故障",
        ],
        clarification_answers=[
            "主要缓存数据库查询结果",
            "缓存 5 分钟过期",
            "可以使用 Redis",
        ],
        risk_level="medium",
        difficulty="medium",
    ),
    BenchmarkCase(
        id="case_4_refactor",
        name="Multi-Step — API Refactoring",
        requirement="把现在这个 API 模块重构一下，太乱了，拆成 service 层和 repository 层",
        context="当前所有业务逻辑写在 router handler 里，包括数据库查询、业务校验、响应组装。约 500 行代码。",
        eval_criteria=[
            "创建了 service 层",
            "创建了 repository 层",
            "router 只负责请求/响应",
            "service 负责业务逻辑",
            "repository 负责数据访问",
            "没有破坏现有 API 接口",
        ],
        clarification_answers=[
            "先重构用户模块",
            "保持现有 API 路径不变",
            "不需要改数据库",
        ],
        risk_level="high",
        difficulty="hard",
    ),
    BenchmarkCase(
        id="case_5_migration",
        name="High Risk — Database Migration",
        requirement="数据库加一个用户角色表，支持多角色",
        context="生产环境 PostgreSQL，users 表有 10 万条数据。现有系统没有角色概念。",
        eval_criteria=[
            "创建了 roles 表",
            "创建了 user_roles 关联表",
            "提供了数据迁移脚本",
            "考虑了回滚方案",
            "没有对现有数据造成破坏性变更",
            "考虑了默认角色分配",
        ],
        clarification_answers=[
            "角色有管理员和普通用户两种",
            "现有用户默认设为普通用户",
            "需要回滚脚本",
            "不需要复杂的权限系统",
        ],
        risk_level="high",
        difficulty="hard",
    ),
    # --- Rule 6/7/8 trigger cases ---
    BenchmarkCase(
        id="case_6_partial_impl",
        name="Partial Implementation — Incomplete Feature",
        requirement="实现一个文件上传功能，支持断点续传和进度回调",
        context="FastAPI 项目，已有基础的文件存储服务。需要对接 MinIO 对象存储。",
        eval_criteria=[
            "实现断点续传（分片上传）",
            "提供上传进度回调",
            "支持 MinIO 对接",
            "处理大文件（>100MB）",
            "错误重试机制",
        ],
        clarification_answers=[
            "文件大小上限 2GB",
            "分片大小 5MB",
            "需要进度百分比回调",
            "MinIO 已部署好",
        ],
        risk_level="medium",
        difficulty="hard",
        description="设计意图：复杂需求容易产生 unresolved_items，测试 Rule 6",
    ),
    BenchmarkCase(
        id="case_7_assumed_defaults",
        name="Heavy Assumptions — Payment Integration",
        requirement="接入支付系统",
        context="电商平台项目，用户量约 5 万。目前只有商品浏览功能，没有任何支付相关代码。",
        eval_criteria=[
            "选择了支付网关",
            "实现了下单流程",
            "处理了支付回调",
            "考虑了幂等性",
            "有退款流程",
        ],
        clarification_answers=[
            "先只支持微信支付",
            "不需要发票功能",
        ],
        risk_level="high",
        difficulty="hard",
        description="设计意图：极其模糊的需求 + high-risk，Spec Council 会填充大量 assumed_defaults。"
                    "测试 Rule 7（assumed_defaults 违规）和 Rule 8（high-risk ≥2 P0/P1）",
    ),
    BenchmarkCase(
        id="case_8_security_critical",
        name="Security Critical — API Key Management",
        requirement="实现 API Key 管理功能，允许用户创建、撤销和轮转 API Key",
        context="SaaS 平台，多租户架构。API Key 用于第三方集成。当前没有 key 管理功能。",
        eval_criteria=[
            "API Key 生成使用密码学安全随机数",
            "Key 存储只保存哈希值",
            "支持 Key 撤销（立即失效）",
            "支持 Key 轮转（新旧 Key 共存过渡期）",
            "每个租户的 Key 隔离",
            "审计日志记录 Key 操作",
        ],
        clarification_answers=[
            "每个用户最多 5 个活跃 Key",
            "轮转过渡期为 24 小时",
            "Key 格式为 sk-{random_hex_32}",
            "需要审计日志",
        ],
        risk_level="high",
        difficulty="hard",
        description="设计意图：high-risk + 严格安全要求，容易产出多个 P0/P1 findings。"
                    "测试 Rule 5（security P0）和 Rule 8（high-risk ≥2 P0/P1 → escalate）",
    ),
]


# ============================================================
# Governance Run with Detailed Metrics
# ============================================================

def run_governance_with_metrics(case: BenchmarkCase) -> tuple[GovernanceMetrics, GovernanceState | None]:
    """Run the governance pipeline and collect detailed timing/token metrics."""
    metrics = GovernanceMetrics(case_id=case.id, risk_level=case.risk_level)
    start_time = time.time()

    try:
        state = run_governance_pipeline(
            raw_request=case.requirement,
            context=case.context,
            clarification_answers=case.clarification_answers if case.clarification_answers else None,
            risk_level=case.risk_level,
        )

        # Apply policy override
        from codegate.policies.engine import apply_policy_override
        state = apply_policy_override(state)

        metrics.total_time = time.time() - start_time

        # Extract per-phase tokens
        phase = state.phase_tokens or {}
        metrics.spec_tokens = phase.get("spec_council", 0)
        metrics.executor_tokens = phase.get("executor", 0)
        metrics.review_tokens = phase.get("reviewer", 0)
        metrics.gate_tokens = phase.get("gatekeeper", 0)
        metrics.total_tokens = state.total_tokens

        # Extract real per-phase wall-clock timings (instrumented in graph.py)
        timings = state.phase_timings or {}
        metrics.spec_time = timings.get("spec_council", 0.0)
        metrics.executor_time = timings.get("executor", 0.0)
        metrics.review_time = timings.get("reviewer", 0.0)
        metrics.gate_time = timings.get("gatekeeper", 0.0)

        # Quality metrics
        if state.contract:
            metrics.contract_goals = len(state.contract.goals)
            metrics.contract_criteria = len(state.contract.acceptance_criteria)
        if state.gate_decision:
            metrics.drift_score = state.gate_decision.drift_score
            metrics.coverage_score = state.gate_decision.coverage_score
            metrics.gate_decision = state.gate_decision.decision
        metrics.findings_count = len(state.review_findings)
        metrics.blocking_count = sum(1 for f in state.review_findings if f.blocking)
        metrics.iterations = state.iteration

        return metrics, state

    except Exception as e:
        logger.error(f"Governance run failed for {case.id}: {e}")
        metrics.total_time = time.time() - start_time
        metrics.error = str(e)
        return metrics, None


# ============================================================
# Evidence Persistence
# ============================================================

def _persist_evidence(case_id: str, state: GovernanceState, run_dir: Path):
    """Save the full governance evidence chain for auditability."""
    evidence_dir = run_dir / case_id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    try:
        if state.contract:
            (evidence_dir / "contract.json").write_text(
                state.contract.model_dump_json(indent=2), encoding="utf-8"
            )
        if state.execution_report:
            (evidence_dir / "execution_report.json").write_text(
                state.execution_report.model_dump_json(indent=2), encoding="utf-8"
            )
        # Always persist findings — empty [] is a meaningful audit fact
        findings_data = [f.model_dump() for f in state.review_findings]
        (evidence_dir / "review_findings.json").write_text(
            json.dumps(findings_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if state.gate_decision:
            (evidence_dir / "gate_decision.json").write_text(
                state.gate_decision.model_dump_json(indent=2), encoding="utf-8"
            )
        if state.phase_tokens:
            (evidence_dir / "phase_tokens.json").write_text(
                json.dumps(state.phase_tokens, indent=2), encoding="utf-8"
            )
        if state.phase_timings:
            (evidence_dir / "phase_timings.json").write_text(
                json.dumps(state.phase_timings, indent=2), encoding="utf-8"
            )
        if state.iteration_history:
            (evidence_dir / "iteration_history.json").write_text(
                json.dumps(state.iteration_history, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        # Always persist policy result (even empty = no violations)
        policy_data = {
            "violations": state.policy_violations,
            "override_applied": len(state.policy_violations) > 0,
        }
        (evidence_dir / "policy_result.json").write_text(
            json.dumps(policy_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"[{case_id}] Evidence saved to {evidence_dir}")
    except Exception as e:
        logger.warning(f"[{case_id}] Failed to persist some evidence: {e}")


# ============================================================
# Benchmark Runner
# ============================================================

def run_benchmark(
    case_ids: list[str] | None = None,
    output_dir: Path = Path("./benchmark_results"),
) -> list[dict]:
    """Run the governance benchmark.

    Each run gets its own timestamped directory:
        benchmark_results/run_YYYYMMDD_HHMMSS/
            manifest.json
            case_*.json
            case_*/evidence/...
            benchmark_report.json
            benchmark_report.md
        benchmark_results/latest → (symlink)
    """
    # Create run-level directory
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    cases = BUILTIN_CASES
    if case_ids:
        cases = [c for c in cases if c.id in case_ids]

    config = get_config()

    # Read executor name from the active adapter (not hardcoded)
    from codegate.agents.executor import _adapter as active_adapter
    executor_name = active_adapter.name if active_adapter else "builtin_llm"

    manifest = {
        "run_id": run_id,
        "version": "v2",
        "started_at": datetime.now().isoformat(),
        "cases": [c.id for c in cases],
        "executor": executor_name,
        "model_config": {
            "spec_model": config.models.spec_model,
            "exec_model": config.models.exec_model,
            "review_model": config.models.review_model,
            "gate_model": config.models.gate_model,
        },
    }

    results = []

    for case in cases:
        logger.info(f"\n{'='*60}")
        logger.info(f"[{case.risk_level.upper()}] Running: {case.name}")
        logger.info(f"{'='*60}")

        metrics, state = run_governance_with_metrics(case)

        if state is not None:
            _persist_evidence(case.id, state, run_dir)

        result = metrics.to_dict()
        results.append(result)

        # Save individual case
        case_file = run_dir / f"{case.id}.json"
        case_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            f"[{case.id}] Done in {metrics.total_time:.1f}s "
            f"(overhead={metrics.governance_overhead:.1f}s, "
            f"exec={metrics.executor_time:.1f}s)"
        )

    # Finalize manifest
    manifest["completed_at"] = datetime.now().isoformat()
    manifest["total_cases"] = len(results)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Save full report
    (run_dir / "benchmark_report.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    _generate_report(results, run_dir)

    # Update 'latest' symlink
    latest_link = output_dir / "latest"
    if latest_link.is_symlink() or latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(run_id)
    logger.info(f"Run saved to: {run_dir}")

    return results


def _generate_report(results: list[dict], run_dir: Path):
    """Generate a human-readable markdown benchmark report."""
    lines = [
        "# CodeGate Benchmark Report (V2)\n",
        "> This benchmark measures **governance overhead**, not governance vs baseline.\n",
        "> Executor: `builtin_llm` (simulated — not a real coding agent)\n",
        "",
        "## Governance Pipeline Results\n",
        "| Case | Risk | Total | Overhead | Exec | Gov Tokens | Decision | Drift | Coverage | Iter |",
        "|------|------|-------|----------|------|-----------|----------|-------|----------|------|",
    ]

    for r in results:
        t = r["timing"]
        tk = r["tokens"]
        q = r["quality"]
        lines.append(
            f"| {r['case_id'][:25]} | {r['risk_level']} | "
            f"{t['total_seconds']}s | **{t['governance_overhead_seconds']}s** | "
            f"{t['executor_seconds']}s | {tk['governance_only']} | "
            f"{q['gate_decision']} | {q['drift_score']} | "
            f"{q['coverage_score']} | {q['iterations']} |"
        )

    # Summary
    valid = [r for r in results if not r.get("error")]
    if valid:
        total_overhead = sum(r["timing"]["governance_overhead_seconds"] for r in valid)
        total_exec = sum(r["timing"]["executor_seconds"] for r in valid)
        total_gov_tokens = sum(r["tokens"]["governance_only"] for r in valid)
        avg_overhead = total_overhead / len(valid)

        lines.extend([
            "",
            "## Key Metrics\n",
            f"- **Average governance overhead per case**: {avg_overhead:.1f}s",
            f"- **Total governance overhead**: {total_overhead:.1f}s",
            f"- **Total executor time**: {total_exec:.1f}s "
            f"(NOT governance cost — would be external in production)",
            f"- **Total governance-only tokens**: {total_gov_tokens}",
            "",
            "> [!NOTE]",
            "> Governance overhead = spec_council + reviewer + gatekeeper time.",
            "> Executor time is shown separately because in production the executor",
            "> is an external tool (Claude Code, Codex, etc.) whose latency is not",
            "> attributable to the governance layer.",
        ])

    report_path = run_dir / "benchmark_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Report saved to: {report_path}")


# ============================================================
# CLI Entry Point
# ============================================================

if __name__ == "__main__":
    import sys

    init_config()
    setup_level = get_config().log_level
    logging.basicConfig(
        level=getattr(logging, setup_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    case_filter = None
    executor_name = "builtin_llm"
    executor_model = ""
    project_dir = ""

    for arg in sys.argv[1:]:
        if arg.startswith("--cases="):
            case_str = arg.split("=", 1)[1]
            if case_str != "all":
                case_filter = [c.strip() for c in case_str.split(",")]
        elif arg.startswith("--executor="):
            executor_name = arg.split("=", 1)[1]
        elif arg.startswith("--executor-model="):
            executor_model = arg.split("=", 1)[1]
        elif arg.startswith("--project-dir="):
            project_dir = arg.split("=", 1)[1]

    # Configure executor adapter
    if executor_name == "opencode":
        from codegate.adapters.opencode import OpenCodeAdapter
        from codegate.agents.executor import set_executor_adapter
        adapter = OpenCodeAdapter(
            model=executor_model,
            project_dir=project_dir if project_dir else None,
        )
        set_executor_adapter(adapter)
        logger.info(f"Using opencode executor (model={executor_model or 'default'})")

    output_dir = Path("./benchmark_results")
    for arg in sys.argv[1:]:
        if arg.startswith("--output="):
            output_dir = Path(arg.split("=", 1)[1])

    results = run_benchmark(case_ids=case_filter, output_dir=output_dir)

    print(f"\n{'='*60}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*60}")
    for r in results:
        t = r["timing"]
        q = r["quality"]
        print(
            f"  {r['case_id']}: total={t['total_seconds']}s "
            f"overhead={t['governance_overhead_seconds']}s "
            f"decision={q['gate_decision']} "
            f"drift={q['drift_score']}"
        )
