# CodeGate Alpha 试用指南

> 版本: Alpha v0.2 | 日期: 2026-04-27 | 适用: 团队内测

---

## 1. CodeGate 是什么

CodeGate 是一个 **AI 代码变更的治理层**。它不替代 AI coding 工具（如 OpenCode、Cursor），而是在 AI 生成代码之后、合入主干之前，自动完成：

1. **契约审查** — 从需求生成实现契约（goals、criteria、constraints），确保 AI 的执行范围被限定
2. **基线感知的漂移检测** — 对比原始代码（baseline）和 AI 生成的代码，识别 silent behavioral changes
3. **自动裁决** — approve / revise_code / escalate_to_human 三级决策
4. **审计证据** — 每次变更留下完整的治理证据链，可追溯、可复盘

### CodeGate 不是什么

- **不是代码质量扫描器** — 不替代 SonarQube、PMD 等静态分析工具
- **不是测试框架** — 不替代 JUnit、pytest 等测试工具
- **不是 AI coding 加速器** — 会增加约 10-15% 的 governance overhead（约 15-30 秒）
- **不是 100% 准确的** — LLM 审查存在不确定性，但三层防御机制（structural pre-check → LLM review → post-filter）显著减少误判

## 2. 适合试用的任务类型

| ✅ 适合 | ❌ 不适合 |
|---------|----------|
| 为现有 API 增加参数校验 | 全新项目从零搭建 |
| 增加新的 REST endpoint | 大规模架构重构 |
| 编写单元测试 | 涉及数据库 migration |
| 修改异常处理逻辑 | 需要交互式 UI 调试 |
| 添加输入格式校验 | 多模块协同变更 |
| 重构错误处理链路 | 涉及外部服务集成 |

**经验法则**：如果变更只涉及 1-3 个文件，有现成测试可跑，就适合用 CodeGate 治理。

## 3. 安装与配置

### 3.1 前置要求

- **Python 3.11+**
- **OpenCode** — AI coding CLI 工具（[安装指南](https://opencode.ai)）
- **模型 API Key** — 当前推荐 `kimi-for-coding/k2p6`
- **目标项目** — 需要有可执行的测试命令（`mvn test -B`、`npm test` 等）

### 3.2 安装 CodeGate

```bash
# 克隆仓库
git clone <codegate-repo-url>
cd codegate

# 安装（editable mode）
pip install -e .

# 验证安装
codegate --help
```

### 3.3 配置 .env

在 codegate 项目根目录创建 `.env`：

```env
# LLM API 配置
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://your-api-endpoint/v1

# 默认模型
CODEGATE_MODEL=your-model-name

# 日志级别
LOG_LEVEL=INFO
```

### 3.4 验证 OpenCode

```bash
# 确认 opencode 可用
opencode --version

# 确认模型可访问
opencode run "say hello" --model kimi-for-coding/k2p6 --format json
```

## 4. 跑单个评估

### 4.1 命令格式

```bash
codegate ab \
  --project /path/to/your/project \
  --input "你的需求描述" \
  --model kimi-for-coding/k2p6 \
  --case-name "需求简称" \
  --answers "预设的 clarification 回答" \
  --build-cmd "mvn test -B" \
  --timeout 600
```

### 4.2 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--project` | ✅ | 源项目路径（**不会被修改**，CodeGate 自动创建临时副本） |
| `--input` | ✅ | 需求描述（中/英文均可） |
| `--model` | ✅ | 执行器使用的模型 |
| `--case-name` | 建议 | 人类可读的 case 名称 |
| `--answers` | 可选 | 预设回答，跳过交互式 clarification（用于 batch 和自动化场景） |
| `--build-cmd` | 可选 | 测试命令，默认 `mvn test -B` |
| `--timeout` | 可选 | 执行器超时（秒），默认 600 |
| `--output` | 可选 | 输出目录，默认 `ab_results/` |

### 4.3 它做了什么

```
codegate ab 自动执行 5 步：

1. Clean Copy    — 从源项目复制两份独立副本（排除 target/、node_modules/ 等）
2. Baseline      — 验证 git status 干净 + 测试通过
3. Line A        — 纯 OpenCode 执行（无治理，作为对照组）
4. Line B        — CodeGate + OpenCode（完整治理管线）
5. Report        — 自动生成 audit_report.md + report.md + ab_result.json
```

### 4.4 示例

```bash
codegate ab \
  --project /Users/wukai/IdeaProjects/image2Pdf \
  --input "为 /api/convert 增加文件名非法字符校验。文件名包含 .. 或 / 时拒绝，返回 HTTP 400 错误响应。" \
  --model kimi-for-coding/k2p6 \
  --case-name "错误响应一致性" \
  --answers "抛出 IllegalArgumentException，由 GlobalExceptionHandler.handleBadRequest 统一处理。错误码 INVALID_FILENAME。" \
  --build-cmd "mvn test -B"
```

### 4.5 耗时预期

| 阶段 | 典型耗时 |
|------|---------|
| Clean Copy + Baseline | 5-15s |
| Line A (Pure OpenCode) | 120-300s |
| Line B (CodeGate + OpenCode) | 140-500s |
| **总计** | **4-12 分钟** |

> ⚠️ 如果 OpenCode 执行器超时（默认 600s），CodeGate 会捕获已写入磁盘的代码并继续审查。超时本身会导致 policy override → `REVISE_CODE`。

## 5. 跑批量评估

### 5.1 编写 cases YAML

创建一个 YAML 文件定义多个 case：

```yaml
# eval_cases/my_project_cases.yaml

project: /path/to/your/project
model: kimi-for-coding/k2p6
build_cmd: mvn test -B
timeout: 600

cases:
  - name: Case 名称
    input: >
      需求描述，可以是多行。
      保留约束写在需求里效果最好。
    answers: >
      预设的 clarification 回答。

  - name: 另一个 Case
    input: >
      另一个需求。
    answers: >
      另一个回答。
```

**YAML 结构说明**：

| 字段 | 层级 | 说明 |
|------|------|------|
| `project` | 顶层 | 默认项目路径 |
| `model` | 顶层 | 默认模型 |
| `build_cmd` | 顶层 | 默认测试命令 |
| `timeout` | 顶层 | 默认超时 |
| `cases[].name` | case | case 名称 |
| `cases[].input` | case | 需求描述 |
| `cases[].answers` | case | 预设回答 |
| `cases[].project` | case（可选） | 覆盖顶层 project |
| `cases[].model` | case（可选） | 覆盖顶层 model |
| `cases[].build_cmd` | case（可选） | 覆盖顶层 build_cmd |
| `cases[].timeout` | case（可选） | 覆盖顶层 timeout |

### 5.2 运行批量评估

```bash
codegate ab-batch --cases eval_cases/my_project_cases.yaml
```

### 5.3 产出结构

```
ab_results/batch_<timestamp>/
├── batch_report.md          # 汇总报告（6 章节 + 可选 §7 Blocked Cases）
├── batch_summary.json       # 结构化汇总数据
├── case_name_1_<ts>/
│   ├── audit_report.md      # 7 章节完整治理报告
│   ├── report.md            # 紧凑摘要
│   ├── ab_result.json       # 完整 raw 数据
│   └── codegate_artifacts/  # 治理证据（contract、findings、diff 等）
├── case_name_2_<ts>/
│   └── ...
└── ...
```

## 6. 阅读报告

### 6.1 audit_report.md（单 case 治理报告）

7 个章节，从上到下回答一个核心问题：**这个变更能不能放行？**

| 章节 | 内容 | 谁看 |
|------|------|------|
| §1 Clearance Decision | ✅/🔄/⚠️ 最终判定 + 依据 | 所有人 |
| §2 Risk Summary | 6 维风险评分表 | 所有人 |
| §3 Findings Detail | 每个 finding 的 severity、disposition、message、location、suggestion | 开发者 |
| §4 A/B Comparison | Line A vs Line B 对比（时间、文件、测试数、heuristic flags） | 开发者 |
| §5 Evidence Chain | 8 项 artifact 路径 + 存在性标注 | 审计 |
| §6 Reproducibility | 项目、模型、命令、时间戳 | 审计 |
| §7 Verdict | 最终判定 + 阻断原因（如有） | 所有人 |

**快速阅读路径**：只看 §1 + §7。如果是 ✅ APPROVE → 放行。如果是 🔴 → 看 §3 Findings Detail 了解具体问题。

### 6.2 batch_report.md（批量汇总报告）

| 章节 | 内容 |
|------|------|
| §1 Executive Summary | 总案例数、通过率、平均 overhead |
| §2 Case Results | 逐 case 汇总表（decision、drift、findings、tests、overhead） |
| §3 Aggregate Findings | 全局 findings 统计 |
| §4 Individual Reports | 每个 case 的 artifact ID 和 audit_report 路径 |
| §5 Reproducibility | cases file、project、model、时间 |
| §6 Batch Verdict | 🟢/🟡/🔴 总体判定 |
| §7 Blocked Cases | （仅在有阻断时出现）每个 blocked case 的 decision、finding、policy override |

## 7. 理解决策

### 7.1 三种决策

| 决策 | 含义 | 行动 |
|------|------|------|
| ✅ `APPROVE` | 实现符合契约，无阻断问题 | 可以放行 |
| 🔄 `REVISE_CODE` | 存在阻断问题，需要修改代码 | 查看 findings，修复后重跑 |
| ⚠️ `ESCALATE_TO_HUMAN` | 问题超出自动裁决范围 | 需要人工审查 |

### 7.2 决策树

```
              开始
               │
      ┌─ drift ≤ 30 且 blocking = 0？
      │        │
     Yes      No
      │        │
      │    ┌── drift > 30？
      │    │        │
      │   Yes      No
      │    │        │
      │    │   revise_code
      │    │
      │  escalate_to_human
      │
   approve
```

### 7.3 Policy Override

当 Gatekeeper（LLM 裁决者）判定 APPROVE，但存在以下情况时，Policy Engine 会强制覆盖：

- **Blocking findings > 0** → 覆盖为 `REVISE_CODE`
- **Timeout 未解决** → 覆盖为 `REVISE_CODE`
- **Max iterations 达到** → 覆盖为 `ESCALATE_TO_HUMAN`

在报告中表现为：

```
⚠️ Policy Override: Gatekeeper originally decided APPROVE,
but policy enforcement overrode to REVISE_CODE due to 1 blocking finding(s).
```

这通常意味着 **contract conflict** — 需求和保留约束之间存在张力。建议先审查契约设计，再修改代码。

### 7.4 Severity × Disposition

| Severity | 含义 |
|----------|------|
| P0 | 关键：约束违反、安全漏洞 |
| P1 | 重要：目标部分达成、静默行为变更 |
| P2 | 次要：风格、优化建议 |

| Disposition | Gate 行为 | 图标 |
|-------------|----------|------|
| blocking | 必须修复才能 approve | 🚫 |
| advisory | 建议修复，不阻断 | ⚠ |
| info | 仅供参考 | ℹ |

`P1 advisory` = "重要但不阻断"，这是合理的组合 — 例如 reviewer 发现了措辞与实现的细微不一致，值得注意但不阻止放行。

## 8. 编写好的 Case

### 8.1 需求描述原则

1. **明确约束**：在 `input` 里写清楚"不要做什么"，比如 "不要修改已有方法的签名和返回类型"、"不要新增 ExceptionHandler"
2. **指定错误码**：告诉 executor 用什么错误码，避免它自己编一个
3. **指定异常路径**：告诉 executor 抛什么异常、谁处理，避免它绕过现有错误处理链路
4. **说明保留要求**：如果有注解、签名、行为不能动，明确写出来

### 8.2 Answers 设计

`--answers` 是预设的 clarification 回答，用于跳过 Spec Council 的交互式提问。好的 answers 应该：

- 重申关键约束（"由 GlobalExceptionHandler.handleBadRequest 统一处理"）
- 消除歧义（"空字符串或 null 不做校验"）
- 指定边界行为（"dpi=600 是合法边界，dpi=601 是非法"）

### 8.3 参考 Case

内置的 `eval_cases/image2pdf_cases.yaml` 包含 4 个已验证的 case，可作为模板：

| Case | 类型 | 复杂度 |
|------|------|--------|
| 错误响应一致性 | 输入校验 + 错误处理 | 低 |
| DPI参数保护 | 参数边界校验 | 低 |
| 测试质量-空文件上传 | 参数校验 | 低 |
| 错误处理链路重构 | 逻辑重构 + 5 项保留约束 | 高（含 contract conflict） |

## 9. 交互式需求澄清（v0.2 新功能）

当使用 `codegate run` 且不提供 `--answers` 时，Spec Council 会在 CLI 中交互式提问：

```bash
codegate run \
  --input "为 /api/convert 增加文件名校验" \
  --executor opencode \
  --project-dir /path/to/project
```

### 9.1 交互流程

```text
🛡️ CodeGate Governance Pipeline
  Requirement: 为 /api/convert 增加文件名校验
  Executor: opencode

╭─────────────────────────────────────────╮
│ 📋 Spec Council 需要澄清以下问题       │
│                                         │
│ 请逐条回答，回答后 CodeGate 将生成      │
│ 实现契约并继续执行。                    │
│ 直接按回车跳过可选问题。输入 q 退出。   │
╰─────────────────────────────────────────╯

  必答 1. [必答] 非法文件名包含哪些字符？
  1> 包含 .. 或 /

  可选 2. [可选] 错误码应该使用什么？
  2> INVALID_FILENAME

  必答 3. [必答] 是否复用现有异常处理链路？
  3> 是，抛 IllegalArgumentException，由 handleBadRequest 处理

╭─── 📋 澄清问答摘要 ────────────────────╮
│ 1. [必答] 非法文件名包含哪些字符？      │
│    → 包含 .. 或 /                       │
│ 2. [可选] 错误码应该使用什么？           │
│    → INVALID_FILENAME                   │
│ 3. [必答] 是否复用现有异常处理链路？     │
│    → 是，抛 IllegalArgumentException    │
╰─────────────────────────────────────────╯

正在生成契约并执行治理管线...
```

### 9.2 两种模式对比

| 模式 | 适用场景 | 命令 |
|------|---------|------|
| **交互式** | 首次探索、需求不确定 | `codegate run --input "..." --executor opencode` |
| **预设回答** | 自动化、batch、CI | `codegate run --input "..." --answers "a1\|a2" --executor opencode` |

### 9.3 证据产出

交互式澄清完成后，额外生成 `clarification_qa.json`：

```json
{
  "round": 1,
  "questions": ["[必答] 非法文件名包含哪些字符？", "..."],
  "answers": ["包含 .. 或 /", "..."],
  "mode": "interactive"
}
```

`summary.json` 中也包含 `clarification_questions` 和 `clarification_answers` 字段。

### 9.4 注意事项

- **必答问题** 不能跳过（直接按回车会提示重新输入）
- **可选问题** 可以按回车跳过（记录为"（跳过）"）
- 输入 `q` 可随时退出，下次使用 `--answers` 重跑
- `codegate ab` 和 `codegate ab-batch` 仍然使用 `--answers` / YAML 中的 `answers` 字段，不支持交互

## 10. 已知限制

| 限制 | 说明 | Workaround |
|------|------|------------|
| **交互式 clarification** | `codegate run` 不带 `--answers` 时，Spec Council 会在 CLI 中交互式提问 | 如需非交互式，使用 `--answers` 预设回答 |
| **单次运行耗时较长** | 典型 4-12 分钟，取决于模型和任务复杂度 | 用 batch 模式并行概念上的 case |
| **必须在 clean copy 上跑** | CodeGate 自动创建临时副本，但源项目的 git status 必须干净 | 确保 `git status --porcelain` 输出为空 |
| **LLM 非确定性** | 同一 case 多次运行可能产出不同代码 | 这正是 CodeGate 存在的意义 — 治理层兜底 |
| **仅支持 OpenCode** | 当前只有 `opencode` 适配器 | 后续会增加 Cursor、Windsurf 等 |
| **Maven 中心** | 测试解析器针对 Maven surefire 优化 | `build_cmd` 支持任意命令，但测试数解析可能不完整 |

## 11. 推荐内测流程

### 第一步：跑内置 Case

```bash
# 用 image2Pdf 项目跑 4 个内置 case
codegate ab-batch --cases eval_cases/image2pdf_cases.yaml
```

预期结果：3 approve + 1 revise_code（Case 4 是 contract conflict）。

### 第二步：审查报告

1. 打开 `batch_report.md` — 看 §2 Case Results 表
2. 打开 Case 4 的 `audit_report.md` — 看 §1 Clearance Decision + §3 Findings Detail
3. 确认你能理解为什么 Case 4 被阻断

### 第三步：接入自己的模块

1. 选一个低风险模块（有测试、有清晰的 API 边界）
2. 参考 §8 编写 1-2 个 case
3. 先用 `codegate ab` 跑单个 case
4. 确认报告可读后，写入 YAML 用 `codegate ab-batch` 跑

### 第四步：反馈

请记录：

- 报告是否能看懂？哪里不清楚？
- 决策是否合理？有没有 false positive？
- 耗时是否可接受？
- 你希望增加什么能力？

---

## 附录 A: 证据 Artifact 说明

| 文件 | 内容 | 何时生成 |
|------|------|---------|
| `summary.json` | 最终状态摘要（decision、drift、tokens、timings） | 每次运行 |
| `contract.json` | Spec Council 生成的实现契约 | 每次运行 |
| `review_findings.json` | 最终 findings（post-filter 后） | 每次运行 |
| `raw_review_findings.json` | LLM 原始 findings（filter 前） | 每次运行 |
| `suppressed_findings.json` | 被 post-filter 压掉的 findings + 原因 | 有 suppression 时 |
| `structural_diff.json` | 确定性基线 diff（removed/added/preserved patterns） | 有 baseline 时 |
| `gate_decision.json` | Gatekeeper 裁决详情 | 每次运行 |
| `policy_result.json` | Policy Engine 覆盖记录 | 每次运行 |
| `clarification_qa.json` | 澄清问答记录（questions、answers、mode） | 有 clarification 时 |
| `phase_timings.json` | 各阶段耗时 | 每次运行 |
| `iteration_history.json` | 多轮迭代记录 | 有 retry 时 |

## 附录 B: 术语表

| 术语 | 定义 |
|------|------|
| **Spec Council** | 需求分析 agent，将自然语言需求转换为结构化契约 |
| **Contract** | Spec Council 的输出：goals、acceptance criteria、constraints |
| **Executor** | AI coding 工具（如 OpenCode），执行代码变更 |
| **Reviewer** | LLM 审查 agent，对比契约和实现，输出 findings |
| **Gatekeeper** | LLM 裁决 agent，综合 findings 做出 approve/revise/escalate 决策 |
| **Policy Engine** | 确定性规则引擎，在 Gatekeeper 之后强制执行安全策略 |
| **Structural Pre-check** | 确定性代码分析，在 LLM 审查前识别 baseline 模式变化 |
| **Post-filter** | 确定性过滤器，在 LLM 审查后压掉 ghost pattern 假阳性 |
| **Drift** | AI 实现偏离契约或 baseline 的程度（0-100 分） |
| **Line A** | A/B 评估中的对照组：纯 AI 执行，无治理 |
| **Line B** | A/B 评估中的实验组：CodeGate + AI 执行 |
| **Contract Conflict** | 需求和保留约束之间存在逻辑矛盾，导致 executor 无法同时满足两者 |
