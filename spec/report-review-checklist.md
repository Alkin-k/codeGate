# CodeGate 报告审查清单

> 用途：每次生成 benchmark 报告或阶段性总结前，对照此清单逐条自检。
> 维护者：AI Agent + 项目负责人
> 规则：犯过的错不重犯。每次被指出新问题，追加到对应章节。

---

## 1. 代码-文档一致性（最高优先级）

> **核心原则：报告中声称"已实现/已对齐"的，必须在代码中可验证。**

- [ ] **Prompt 与 Policy Engine 规则数一致**
  - engine.py 有 N 条规则 → gatekeeper.md 的 Hard Policy Rules 段必须列 N 条
  - 教训来源：V2.2 报告说"8 条规则代码与文档完全对齐"，但 gatekeeper.md 仍只有 5 条

- [ ] **Prompt 中的阈值与 engine.py 的硬编码阈值完全匹配**
  - 包括 risk-aware 分层阈值（如 high: drift≤15, coverage≥85）
  - 教训来源：V1 时 prompt 写 drift≤20，engine 写 drift≤30 → 灰区

- [ ] **报告引用的 schema 字段在代码中实际被消费**
  - 如果说"risk_level 已进入治理"，必须验证至少一个 node/policy 读取了它
  - 教训来源：V2.0 宣称 risk_level 流转，实际没有任何节点读取

- [ ] **报告说"已修复"的 bug，对应代码的 diff 可追溯**
  - 不能只凭"run 结果变好了"就说修复了，要指向具体代码行
  - 教训来源：V2.1 文档宣称 Rule 6/7/8 已落地，但 engine.py 只有 5 条

---

## 2. 数据表述准确性

> **核心原则：区分"已证明"和"推论"。**

- [ ] **不把模拟数据当真实商业数据引用**
  - BuiltinLLMExecutor 产出的 timing 只能说"模拟链路真实测量"
  - 不能说"接入外部 executor 后用户感知延迟是 X 秒"
  - 教训来源：V2.2 报告中"用户唯一感知到的额外延迟"措辞过于确定

- [ ] **"通过率"必须区分首轮和最终**
  - "4/5 approve" 要注明哪些是首轮直接 approve、哪些是经修订后 approve
  - 教训来源：V2.0 的 "5/5 approve" 掩盖了 gate 偏松

- [ ] **未触发的规则不能算"已验证"**
  - 规则存在但没有被触发 ≠ 规则正确工作
  - 要说"有效但未触发"，不能说"验证通过"
  - 教训来源：V2.2 报告 Rule 6/7/8 均无触发样本

- [ ] **版本对比要控制变量**
  - 如果 prompt 变了 + policy 变了 + case 解读可能不同 → 对比只能做方向判断
  - 不能做强归因"改进来自 X"，除非其他变量被固定
  - 教训来源：V2.1 retro 文档 §4.5 指出的可比性问题

---

## 3. 证据链完整性

> **核心原则：报告中的每个结论，在 run 目录里必须有可独立复盘的 evidence。**

- [ ] **多轮修订的每一轮 evidence 单独持久化**
  - 不能只存最终态的 findings/gate_decision
  - 教训来源：V2.2 Case 2/3 的首轮拦截数据不可从 evidence 重放

- [ ] **空 findings 也要落盘**
  - `findings=[]` 是一个有意义的审计事实（说明 reviewer 判定无缺陷）
  - 而不是"没有文件"

- [ ] **phase_timings.json 必须与报告数字一致**
  - 报告引用的 overhead 秒数应该能从 evidence 中的 phase_timings.json 加和验证

---

## 4. 产品表述边界

> **核心原则：不过度包装当前阶段能力。**

- [ ] **区分"阈值分层"和"流程分层"**
  - 如果不同 risk_level 只是 Policy Engine 阈值不同 → 说"阈值分层"
  - 只有 graph.py 的节点/路径因 risk_level 而不同时，才能说"流程分层"
  - 教训来源：V2.2 报告没有明确区分这两个概念

- [ ] **不声称"完全对齐"除非逐文件验证过**
  - "代码与文档完全对齐" 是一个很强的断言
  - 需要逐个检查：engine.py ↔ gatekeeper.md ↔ reviewer.md ↔ system.md ↔ ADR
  - 教训来源：V2.2 报告的"完全对齐"在 gatekeeper.md 处失效

- [ ] **"治理价值"的说法需要对应具体拦截样本**
  - 不能泛泛说"系统具备拦截能力"
  - 要说"Case X 首轮被 Rule Y 拦截，原因是 Z，经修订后通过"
  - 教训来源：V2.0 全量 approve 时仍声称有治理价值

---

## 5. 报告结构自检

- [ ] 结论章节区分了"已证明"和"尚未证明"
- [ ] 遗留问题章节列出了所有已知未解决项
- [ ] 数据表格可从 benchmark_report.json 直接验证
- [ ] 每个数字引用都有对应的 evidence 文件路径或代码行号
- [ ] **同一份报告内部各表格数字必须交叉一致**
  - 总览表、首轮/最终对照表、evidence 验证表中的 findings 数必须一致
  - 教训来源：V2.3 报告 Case 3 在 §2 写 8→0、在 §5 写 1 (non-blocking)，实际 evidence 是 1

---

## 6. Findings 语义纯度

> **核心原则：findings 只能包含实际缺陷，不能包含"通过判定"或"非缺陷描述"。**

- [ ] **review_findings.json 中不得出现 "No issue" / "No finding" / "No action needed" 等文本**
  - 如果 finding 的 message 描述的是"没有问题"，则它不是 finding，应该被移除
  - 教训来源：V2.3 Case 3 有 "No finding for this."、Case 7 有 "No action needed."

- [ ] **空 findings 必须落盘为 `[]`**
  - `review_findings.json = []` 是一个有意义的审计事实（说明 reviewer 判定无缺陷）
  - 代码中不能用 `if findings:` 来条件写入
  - 教训来源：V2.3 Case 1/5/6 无 review_findings.json 文件

- [ ] **iteration_history 必须使用自然轮次编号**
  - `round` 字段从 1 开始，不能因为内部 state.iteration 先 increment 而从 2 开始
  - `round` 反映的是"这是第几轮审查"，不是 state 内部控制变量
  - 教训来源：V2.3 Case 3/6 的 iteration_history 首条记录 iteration=2

- [ ] **findings 噪音检查不能只做词法匹配，必须包含语义判断**
  - 黑名单短语归零 ≠ findings 语义纯度达标
  - 需要额外检查：message 中是否描述"当前实现可接受/正确/没问题"
  - 教训来源：V2.3.1 Case 8 有 "This is correct ... which is fine" 和 security P0 说"当前实现可接受"

---

## 7. Policy Override 证据一致性

> **核心原则：Policy Engine override 后，gate_decision 的所有字段必须自洽。**

- [ ] **override 后 next_action 必须同步重写**
  - 不能出现 decision=escalate_to_human 但 next_action="Merge the implementation"
  - 教训来源：V2.3.1 Case 4 decision=escalate 但 next_action="Merge"；Case 8 同理

- [ ] **区分"gatekeeper 同向判定"和"Policy Engine override"**
  - 只有 policy_result.json 中 override_applied=true 才能说"Rule X 被 Policy Engine 触发"
  - 如果 gatekeeper 自己判了 revise/escalate 而 Policy 没有 override → 不算 Policy 触发
  - 教训来源：V2.3.1 报告把 Case 3 round 1 的 gatekeeper revise 算成了 Rule 1 的 Policy override

- [ ] **policy_result.json 必须为每个 case 落盘**
  - 包括 violations=[] 的 case（代表 Policy 审查通过）

---

## 变更记录

| 日期 | 新增条目 | 来源 |
|------|---------|------|
| 2026-04-24 | 全部初始条目 | V1→V2.0→V2.1→V2.2 四轮踩坑汇总 |
| 2026-04-24 | §5 报告内部交叉一致、§6 findings 纯度（3 条） | V2.3 报告审查反馈 |
| 2026-04-24 | §6 语义噪音、§7 Policy override 一致性（3 条） | V2.3.1 报告审查反馈 |
