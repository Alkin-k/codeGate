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
- 参见 ADR-006

### 4.5 Node 计时使用 _timed_node 包装器

- 不要用 token 比例估算耗时
- `graph.py` 中每个 node 都用 `_timed_node()` 包装
- 真实耗时存在 `state.phase_timings` 中

### 4.6 修订循环必须传完整 feedback

- Executor 重试时必须传递：blocking findings + P0/P1 non-blocking findings + gatekeeper.next_action + drift/coverage 分数
- 只传 blocking findings 会让修订"盲转"

### 4.7 Findings 噪音短语黑名单

- Finding message 中不得出现："No finding for this"、"No issues found"、"No action needed"、"All goals met"
- 如果 message 描述的是"没有问题"，它不是 finding
- reviewer.md 的 Rules 段落已包含显式黑名单

### 4.8 空 findings 必须落盘

- `review_findings.json = []` 是审计事实，不能省略
- benchmark.py 中不能用 `if state.review_findings:` 条件写入
- 无缺陷和"缺少 review_findings.json 文件"含义不同

### 4.9 iteration_history 在 increment 之前快照

- `round` 字段记录的是自然轮次（1, 2, 3...）
- snapshot 必须在 `state.iteration += 1` 之前写入
- 否则首条记录会从 2 开始，与人类理解不一致

### 4.10 Policy Override 必须同步 next_action

- engine.py 的 apply_policy_override 改 decision 时，必须同时重写 next_action
- 否则会出现 decision=escalate 但 next_action="Merge" 的矛盾
- escalate → next_action 写 "[ESCALATED BY POLICY] ..."
- revise_code → next_action 写 "[BLOCKED BY POLICY] ..."

### 4.11 报告中区分"gatekeeper 同向"和"Policy override"

- 只有 policy_result.json 中 override_applied=true 才能说某 Rule 被 Policy Engine 触发
- gatekeeper 自己判了 revise/escalate → Policy 没 override → 说"gatekeeper 判定与 Rule N 同向"
- 不能把 gatekeeper 的自主判定算成 Policy Engine 的功劳

### 4.12 Executor Adapter 使用

- opencode adapter 通过 `opencode run --format json --dir <sandbox>` 调用
- 真实 executor 产出的 `files_content` 和 `file_list` 反映实际文件变更
- benchmark 中对比 builtin_llm vs opencode 时，需注明 executor 类型
- opencode 的 code_output 是真实可执行代码，builtin_llm 是文本模拟
- 不要在真实项目中使用 `--dangerously-skip-permissions` 而不加沙盒隔离
