# ADR-009: 结构化预检 — 事实层由代码裁决

- **日期**: 2026-04-24
- **状态**: 已采纳
- **决策者**: 项目负责人

## 背景

§19 DPI rerun 证明：即使把 baseline 内容注入 reviewer prompt，LLM 仍然会产生
假阳性。具体表现：

- Iter1: executor 新增了 `HandlerMethodValidationException` handler（baseline 中不存在）
- Iter2: executor 移除了该 handler
- Reviewer 在 iter2 把"移除 iter1 新增的内容"误判为"移除 baseline 既有行为"
- 但 reviewer 在 iter1 自己明确识别了该 handler "was not in baseline"

**同一个 LLM、同一份 baseline 证据、两轮相反的事实结论。**

这不是 prompt 质量问题——这是 LLM 做精确事实裁决的固有不可靠性。

## 决策

**事实判定由代码执行，LLM 只做解释和归因。**

### 三层架构

```
Layer 1: 结构化预检 (deterministic)
  └─ compute_baseline_diff() → removed / added / preserved

Layer 2: LLM 审查 (interpretive)
  └─ 基于结构化 diff 做合同合规判断

Layer 3: 后过滤 (deterministic)
  └─ 抑制"声称移除了 baseline 不存在的 pattern"的 finding
```

### 实现

- `analysis/baseline_diff.py`: 正则/AST 提取 patterns → 集合 diff
- `agents/reviewer.py`: pre-check + prompt injection + post-filter
- `prompts/reviewer.md` §7: 强制引用 🔬 STRUCTURAL BASELINE DIFF

### 覆盖的 Pattern 类型

| Pattern | 语言 | 提取方式 |
|---------|------|---------|
| 校验注解 (@Min, @Max, @NotNull...) | Java | 正则 |
| 异常处理器 (@ExceptionHandler) | Java | 正则 |
| 方法签名 (public ReturnType name) | Java | 正则 |
| 装饰器 (@app.route, @validator) | Python | 正则 |

## 替代方案

1. **仅加强 prompt**: 被否决 — §19 证明不可靠
2. **LLM 提取 + 代码 diff**: 提取本身仍依赖 LLM，不确定性未消除
3. **仅后过滤**: 部分采纳 — 作为兜底层，但不足以作为唯一防线

## 后果

- 结构化预检覆盖的 pattern 类型将随实际假阳性案例持续扩展
- 新增语言支持需要对应的正则提取器
- 当正则无法覆盖的复杂 pattern 出现时，post-filter 作为兜底
