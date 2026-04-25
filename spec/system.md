# CodeGate 系统规格说明

## 1. 系统定位

> 一个面向 AI Coding 的方案批准、偏航审计与质量门禁层。

CodeGate 站在执行器（Codex / Claude Code / OMO / OMC）之上，负责：

1. 把模糊需求变成可执行合同（ImplementationContract）
2. 对照合同审计实现是否偏航（drift detection）
3. 按程序化规则决定是否放行（gate decision）
4. 全过程留存审计证据

## 2. 核心数据结构

```
WorkItem ──→ ImplementationContract ──→ ExecutionReport ──→ ReviewFinding[] ──→ GateDecision
 (需求)         (批准合同)                (执行报告)          (审查发现)         (门禁决策)
```

### 2.1 WorkItem

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | UUID |
| title | str | 工作项标题 |
| request | str | 原始需求 |
| context | str | 项目上下文 |
| status | WorkflowStatus | 当前状态 |

### 2.2 ImplementationContract

| 字段 | 类型 | 说明 |
|------|------|------|
| goals | list[str] | 目标列表 |
| non_goals | list[str] | 非目标 |
| constraints | list[str] | 约束条件 |
| acceptance_criteria | list[Criterion] | 验收标准（含 priority + verification） |
| required_tests | list[str] | 必要测试 |
| assumed_defaults | list[str] | 假设默认值 |
| risks | list[str] | 风险点 |

### 2.3 ExecutionReport

| 字段 | 类型 | 说明 |
|------|------|------|
| code_output | str | 生成的代码/patch |
| file_list | list[str] | 修改的文件列表 |
| summary | str | 执行摘要 |
| goals_addressed | list[str] | 已完成的目标 |
| unresolved_items | list[str] | 未完成项 |
| executor_name | str | 执行器名称 |

### 2.4 ReviewFinding

| 字段 | 类型 | 说明 |
|------|------|------|
| category | str | drift / completeness / correctness / security / maintainability |
| severity | str | P0 / P1 / P2 |
| message | str | 具体描述 |
| contract_clause_ref | str | 引用合同条款 |
| blocking | bool | 是否阻断放行 |
| suggestion | str | 修复建议 |

### 2.5 GateDecision

| 字段 | 类型 | 说明 |
|------|------|------|
| decision | str | approve / revise_code / revise_spec / escalate_to_human |
| drift_score | int | 0-100 |
| coverage_score | int | 0-100 |
| blocking_findings | list[str] | 阻断性发现 |
| summary | str | 决策理由 |
| requires_human | bool | 是否需要人工介入 |

## 3. 流水线节点

```
spec_council → executor → reviewer → gatekeeper
     ↑              ↑                    │
     │              └── revise_code ─────┤
     └────── revise_spec ────────────────┤
                                         │
                          escalate / approve → END
```

### 3.1 Spec Council

- 接收原始需求 + 上下文
- 主动追问模糊点
- 生成 ImplementationContract
- **输出**: 批准版合同

### 3.2 Executor (外部 adapter)

- 接收批准合同
- 委托给外部执行器生成代码
- 收回 ExecutionReport
- **输出**: 执行报告

### 3.3 Reviewer

- 对照 contract + code_output 审查
- 检查 drift、coverage、correctness、security
- **输出**: ReviewFinding[] + drift_score + coverage_score

### 3.4 Gatekeeper

- 综合 review findings 做决策
- **输出**: GateDecision

## 4. Policy Engine（硬规则）

| Rule | 条件 | 动作 | 说明 |
|------|------|------|------|
| 1 | security P0 findings > 0 | 拒绝 approve | |
| 2 | drift_score > 30 (high-risk: >15) | 拒绝 approve | risk-aware 阈值 |
| 3 | coverage_score < 70 (high-risk: <85) | 拒绝 approve | risk-aware 阈值 |
| 4 | iteration >= max_iterations && !approved | 强制 escalate_to_human | |
| 5 | blocking P0 findings > 0 | 拒绝 approve | |
| 6 | unresolved_items > 0 | 拒绝 approve | V2.1 新增 |
| 7 | findings 引用 assumed_defaults 且 P0/P1 | 拒绝 approve (high-risk: escalate) | V2.1 新增 |
| 8 | high-risk + ≥2 P0/P1 findings | 强制 escalate_to_human | V2.1 新增 |

## 5. Executor Adapter 接口

```python
class ExecutorAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def execute(
        self,
        contract: ImplementationContract,
        context: str = "",
        feedback: str = "",
    ) -> ExecutionReport: ...
```

### 已实现 Adapter

| Adapter | 状态 | 说明 |
|---------|------|------|
| BuiltinLLMExecutor | ✅ 测试用 | LLM 模拟执行，不产出真实 patch |
| OpenCodeAdapter | 🔲 待实现 | 通过 OpenCode CLI 执行 |
| OMOAdapter | 🔲 待实现 | 通过 OMO API 执行 |
| ClaudeCodeAdapter | 🔲 待实现 | 通过 Claude Code SDK 执行 |

## 6. Benchmark 度量体系

### V2 度量指标

| 指标 | 说明 | 谁的成本 |
|------|------|---------|
| governance_overhead | spec + review + gate 耗时 | 治理层 |
| executor_time | 执行器耗时 | 外部执行器 |
| governance_tokens | spec + review + gate token 消耗 | 治理层 |
| executor_tokens | 执行器 token 消耗 | 外部执行器 |
| drift_score | 实现偏航程度 | 质量指标 |
| coverage_score | 合同覆盖率 | 质量指标 |
| gate_decision | 最终门禁决策 | 质量指标 |
| iterations | 修订轮次 | 效率指标 |
