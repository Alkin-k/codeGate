# CodeGate — Agent 协作规则

> 本文件供 AI Agent（Codex / Claude Code / Antigravity / OMO / OMC）读取，
> 作为参与 CodeGate 项目开发时的行为指南。

---

## 1. 项目定位

CodeGate 是一个 **AI Coding 治理层**（Governance Layer），不是编排器，不是 IDE，不是执行器。

它只做三件事：

1. 把模糊需求变成 **可执行合同**（ImplementationContract）
2. 对照合同 **审计偏航**（drift detection）
3. 按硬规则 **决定放行**（gate decision）

## 2. 架构红线

### 2.1 Executor 是外部的

- `executor` 节点只是 adapter 的代理，**不包含业务逻辑**
- 内建的 `BuiltinLLMExecutor` 仅用于测试，**不代表产品行为**
- 治理层（spec_council / reviewer / gatekeeper / policy_engine）必须是 **executor-agnostic**

### 2.2 状态机不可绕过

- 所有工作项必须经过 `spec_council → executor → reviewer → gatekeeper` 四个节点
- 跳过任何节点的 shortcut 只允许出现在 **低风险快速路径** 中，且必须在 state 中标记

### 2.3 Policy Engine 是最终权威

- LLM 门禁（gatekeeper）的决策是**建议性**的
- Policy Engine 的规则是**强制性**的，可以 override 任何 LLM 决策
- Prompt 中的阈值必须与 Policy Engine 的硬编码阈值 **完全一致**
- 当前规则清单（8 条）：
  - Rule 1: blocking findings → 拒绝 approve
  - Rule 2: drift > 30 (high-risk: >15) → 拒绝 approve
  - Rule 3: coverage < 70 (high-risk: <85) → 拒绝 approve
  - Rule 4: 达到 max_iterations 未通过 → escalate
  - Rule 5: security P0 → escalate
  - Rule 6: unresolved_items > 0 → 拒绝 approve
  - Rule 7: assumed_defaults 被 P0/P1 finding 引用 → 拒绝 approve
  - Rule 8: high-risk + ≥2 P0/P1 → escalate

## 3. 踩坑记录

### 3.1 LangGraph 条件路由函数不能修改 state

**问题**：在 `_route_after_gate()` 中做 `state.iteration += 1` 不会生效。
**原因**：LangGraph 的 conditional edge 函数是只读路由器，修改不会持久化。
**修复**：所有 state 修改必须在 node 函数（如 `run_gatekeeper()`）中完成。

### 3.2 LangGraph invoke 返回 dict，嵌套 Pydantic 模型丢失

**问题**：`workflow.invoke()` 返回 dict 时，`contract`、`gate_decision` 等嵌套对象变成原始 dict。
**原因**：LangGraph 内部序列化机制。
**修复**：`_reconstruct_state()` 显式重建所有嵌套 Pydantic 模型。

### 3.3 Python 3.9 不支持 `X | None` union 语法

**问题**：LangGraph 内部用 `get_type_hints()` 解析 state 类型，3.9 下 `X | None` 报错。
**修复**：state 定义用 `Optional[X]`，并在文件头加 `from __future__ import annotations`。

### 3.4 Deepseek API 间歇性 SSL/EOF 断连

**问题**：长跑 benchmark 时 Deepseek API 会随机断连。
**修复**：`llm.py` 加了指数退避重试（3 次，基础 2 秒）。

### 3.5 LLM 返回的 JSON 类型不稳定

**问题**：executor 返回 `file_list` 时有时是 string，有时是 int，有时是 null。
**修复**：`_to_str_list()` 做鲁棒类型强转。

### 3.6 Policy Rule 写 warnings 不等于 violations

**问题**：`engine.py` Rule 4 把 max_iterations 超限写进 `warnings`，但 `apply_policy_override` 只检查 `violations`。
**结果**：Rule 4 变成死规则，永远不触发。
**修复**：改为 `violations`。

### 3.7 Prompt 阈值与 Policy 阈值不一致导致灰区

**问题**：gatekeeper.md 写 drift≤20，engine.py 写 drift≤30 → 21-30 是矛盾区。
**修复**：统一为 Policy Engine 的值（drift≤30, coverage≥70），Prompt 中增加 Hard Policy Rules 说明。

### 3.8 Reviewer system prompt 与 user prompt 输出格式不一致

**问题**：system prompt 说"返回 JSON array"，user prompt 说"返回 JSON object"。
**结果**：不同模型/温度下解析不稳定。
**修复**：统一为 JSON object + 完整 example。

## 4. 开发约定

### 4.1 Schema 先行

- 任何新功能先定义 Pydantic schema，再写 agent prompt
- Schema 是骨架，prompt 是肉

### 4.2 测试产物管理

- 每次 benchmark run 必须在 `benchmark_results/run_YYYYMMDD_HHMMSS/` 下
- 必须包含 `manifest.json` + 每个 case 的 `evidence/` 目录
- 严禁覆盖写历史 run 数据

### 4.3 Prompt 变更必须同步 Policy

- 修改任何 prompt 中的阈值/规则时，同步检查 `policies/engine.py`
- 反之亦然

### 4.4 Findings 只包含缺陷

- Reviewer 的 findings 只能包含实际问题，不能包含"通过判定"
- "No security issues found" 不是 finding
- Policy Engine 基于 findings 做硬判断，findings 纯度是生死攸关的
- 违反 assumed_defaults 的 P1+ finding 必须标记 `blocking: true`
- 参见 ADR-006, ADR-007

### 4.5 Node 计时使用 _timed_node 包装器

- 不要用 token 比例估算耗时
- `graph.py` 中每个 node 都用 `_timed_node()` 包装
- 真实耗时存在 `state.phase_timings` 中

### 4.6 修订循环必须传完整 feedback

- Executor 重试时必须传递：blocking findings + P0/P1 non-blocking findings + gatekeeper.next_action + drift/coverage 分数
- 只传 blocking findings 会让修订"盲转"

## 5. V2 Benchmark 踩坑记录（2026-04-23）

### 5.1 Reviewer 给分不遵循自己的公式

**问题**：Reviewer prompt 明确写了 `drift_score = (unmet_criteria / total_criteria) × 100`，
但 LLM 实际给出的分数是"感觉上差不多"的估计值，不是精确计算。
**案例**：Case 5 reviewer 发现"缺少 roles 表"，同时给了 `drift=10, coverage=100`。
**修复**：Prompt 中增加更明确的计算指导，将 assumed_defaults 违规纳入计算基数。

### 5.2 100% approve 不是好事

**问题**：V2.0 的 5/5 approve 掩盖了 gate 偏松的问题。
**教训**：治理产品的核心价值是"拦截价值"。Case 5 的 approve 其实是一个误放行。
**修复**：收紧 Policy Engine（Rule 6/7/8），确保不合格实现被拦截。

### 5.3 assumed_defaults 是治理盲区

**问题**：`assumed_defaults`、`required_tests`、`rollback_conditions` 在合同中定义了，
但 Policy Engine 没有任何规则检查它们。它们是"死字段"。
**修复**：Rule 7 检查 assumed_defaults 违规。参见 ADR-007。

### 5.4 risk_level 不能只是展示字段

**问题**：`risk_level` 在 state 中流转但不影响任何行为。low 和 high 走完全相同的路径。
**修复**：Rule 2/3 使用 risk_level 动态选择阈值，Rule 8 仅对 high-risk 生效。参见 ADR-008。

### 5.5 venv 在 iCloud Drive 中文路径下 symlink 损坏

**问题**：在不同路径下创建的 `.venv`，Python 解释器 symlink 中的中文被 escape 导致无法找到。
**修复**：在正确的路径下重新创建 venv：`rm -rf .venv && python3 -m venv .venv`。
**预防**：`.venv` 不入版本控制，每次 clone 后重建。
