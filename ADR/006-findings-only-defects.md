# ADR-006: Findings must be defects only, not pass verdicts

- **日期**: 2026-04-23
- **状态**: 已采纳
- **决策者**: 项目负责人

## 背景

Reviewer prompt (reviewer.md) 要求对每个审查维度"MUST provide a verdict"，但输出 schema (ReviewFinding) 只有 findings 字段。

## 问题

这迫使模型把"没问题"也编码为 finding。例如 Case 1 Fibonacci 中出现：

```json
{
  "category": "security",
  "severity": "P0",
  "message": "No security issues detected; no hardcoded credentials..."
}
```

Policy Engine Rule 5 看到 `category=security + severity=P0` → block approve → escalate_to_human。

**一个正确实现因为"没有安全问题"而被判定有安全问题。**

## 决策

1. Prompt 中明确：`findings` 只包含 **实际缺陷**，不包含通过判定
2. 每个审查维度改为"Create a finding ONLY if..."
3. 新增强调：`An empty findings array [] is correct when there are no problems`
4. 增加反例 example（空 findings）

## 验证

修复前 Case 1 有 7 个 findings（其中 4 个是通过判定），修复后预期 findings 数量大幅减少。

## 教训

- 输出 schema 的语义必须与 prompt 指令一致
- "必须回答每一项"和"只报告问题"是矛盾的指令
- Policy Engine 基于 findings 做硬判断，所以 findings 的纯度是生死攸关的
