# ADR-007: Gate 语义收紧 — assumed_defaults、unresolved_items 进 Policy

> 日期: 2026-04-23
> 状态: Accepted

## 上下文

V2 benchmark 全量 5/5 approve，但 case_5_migration 存在明显的 gate 偏松问题：

- Contract 的 `assumed_defaults[0]` 明确写了"角色表包含 id 和 name 字段，name 唯一"
- Executor 实际没有创建 roles 表，只用了 `user_roles(user_id, role_name)` 直接存字符串
- Reviewer 发现了问题，但标记为 `blocking: false`
- Gatekeeper 给了 `coverage=100, approve`
- Policy Engine 的 5 条规则没有任何一条检查 assumed_defaults / unresolved_items

**根本原因**：Policy Engine 只检查 drift/coverage 数值和 P0 finding 计数，不检查合同语义字段。

## 决策

### 新增 Policy Rules

| Rule | 条件 | 动作 |
|------|------|------|
| 6 | executor 有 unresolved_items | 拒绝 approve → revise_code |
| 7 | findings 引用 `assumed_defaults[N]` 且 severity ∈ {P0, P1} | 拒绝 approve → revise_code (high-risk → escalate) |
| 8 | high-risk + ≥2 P0/P1 findings | 拒绝 approve → escalate_to_human |

### 修改 Reviewer Prompt

- 新增 "§7. Assumed Defaults Compliance" 审计维度
- 违反 assumed_defaults 的 P1+ finding 必须标记 `blocking: true`
- drift_score 计算公式包含 assumed_defaults 违规项
- coverage_score 对"部分合规"更严格：partial = not addressed

### 修改 Gatekeeper Prompt

- 输入中新增 risk_level 字段
- Hard Policy Rules 段落反映 Rule 6/7/8 的存在
- approve 条件新增：无 assumed_defaults 违规、无 unresolved items

## 后果

- Case 3/4 在首轮被正确拦截（之前直接放行），验证了"拦截价值"
- 总体 approve 率从 V2 的 5/5 变为需要修订后才能通过
- 平均治理开销从 20.6s 降到 16.9s（因为修订轮更聚焦）
