# AI 论文排版 Agent — 需求评审分析报告

> 对 `2026-04-15-ai-thesis-agent-architecture-requirements.md` 做逐条交叉检查。
> 只列出**有问题**的条目；未列出的视为通过。

## 0. 总体结论

整体覆盖完整，12 条主需求 + 7 条横切约束 + MVP 切分能支撑后续开发。但有以下问题需要在动工前解决：

- **3 个严重问题（Major）**：会导致跨需求逻辑冲突或实现卡壳
- **9 个中等问题（Moderate）**：歧义点会让实现者做随意决定
- **6 个轻微问题（Minor）**：完整性补充
- **5 项缺失需求**：备份策略、日志级别入口、插件发现、崩溃恢复、GUI 集成时间表
- **4 项待你拍板**：阈值、超时、默认值

---

## 1. 严重问题（Major）— 必须修

### M1. 状态值在 R4 与 R7 之间不一致

- **现象**：
  - R4.6 规定 `CheckResult.status` 可为 `pass / fail / skip / error`
  - R7.4 规定报告 `status` 严格为 `done / partial / failed / skipped`
  - 没有定义 `error` 在报告里如何呈现

- **影响**：实现 `delivery/report.py` 时不知怎么把 `error` 映射到四档

- **建议修复**：
  - 在 R4.6 后追加："report 层把 `error` 映射为 `failed`，并在 `diagnosis.rationale` 注明 `evaluation_error: <reason>`"
  - 或增加第五档 `error`，覆盖到 R7.4 / R7.5（更准确，但报告分块多一类）
  - **推荐**：保持四档，error → failed 映射，理由："对用户来说 error 和 failed 都需要关注"

### M2. R3.4 "报错并跳过" 自相矛盾

- **现象**：R3.4 原文 "未执行则报错并跳过"。报错 = 异常中断，跳过 = 继续；语义冲突。

- **建议修复**：改为 "未执行则**抛 `MissingPrerequisiteToolError`，本次 plan 中止；编排层捕获后写入 trace，按 R6.3 第二个退出条件计入 max_iterations**"

### M3. R6.4 回滚粒度模糊（步级 vs plan 级）

- **现象**：R6.4 "立即调用 `rollback_last`" 没说回滚整个 plan 还是单步。
  - 假设 plan 含 P1 P2 P3，P3 失败，前面 P1 P2 是否回滚？

- **影响**：决定整个事务模型。两种方案差异巨大。

- **建议修复**：明确语义为
  - **步级回滚**（推荐）：只回滚失败步本身的快照，前面成功步保留 → plan 部分完成；评测会反映这一现实
  - 在 R6.4 追加："回滚仅作用于失败的当前 step；本 plan 中已完成的 step 保留其副作用，由 `evaluate` 重新校验"

---

## 2. 中等问题（Moderate）— 需要明确

### Mo1. R1.4 嵌套未知字段处理未定义
- 现象：`body.unknown_subkey` 这种嵌套字段是顶层跳过还是递归收集？
- 建议：追加"递归遍历，所有未知 key 以 dotted path 形式（如 `body.unknown_subkey`）收集到 `metadata.unknown_keys`"

### Mo2. R1.5 重复 id 出现的来源未说明
- 现象：单个 YAML 不太会写两条同 id；但 profile 继承（`extends:`）+ 用户覆盖时可能产生
- 建议：澄清为"在合并所有 YAML 来源后的最终规则集合中，若有重复 id"

### Mo3. R2.3 "只读视图" 与 R3 写入需求冲突
- 现象：Tools 必须改 `DocumentModel`；R2.3 只说"只读视图"
- 建议：把 R2.3 改为 **`DocumentModel` 提供读 API（给 Evaluator）+ 受控写 API（给 Tool，写入会自动追踪 `changed_*`）**

### Mo4. R4.7 `error` 与 `skip` 区分模糊
- 现象：什么情况是 skip？什么情况是 error？
- 建议：
  - `skip`：规则不适用本上下文（如"目录条目数"在 mode=targeted 跳过目录时）
  - `error`：规则适用但因文档异常无法判断（如 locator 找不到段落）

### Mo5. R5.5 confidence 来源未说明
- 现象：0.7 阈值是 LLM 自己报的还是系统估算？
- 建议：澄清"`confidence` 由 LLM 在 JSON 输出中自报；系统对其值再做夹紧 [0,1] 与最低保护：相同 evidence 重复出现两次仍 fail 时 confidence 强制降至 0.5 以下"

### Mo6. R5.6 缓存键 evidence_hash 输入未定义
- 现象：直接 hash evidence 文本可能命中率低（小改动 → key 变了）
- 建议：定义为 `sha256(rule_id + locator_canonical_json + evidence_text_normalized)`，evidence_text_normalized 去多余空白与全角

### Mo7. R6.3 "新计划与上一轮等价" 等价定义缺失
- 现象：含义不清；plan 里 ToolCall 顺序、参数都参与比较吗
- 建议：定义为"new_plan 与 prev_plan 的 `tool` 序列与每个 step 的 params canonical_json 完全一致"

### Mo8. R7.6 docx 标注与既有高亮冲突
- 现象：用户文档可能已有黄色高亮；系统再加高亮容易被误认为原文
- 建议：
  - 用 **Word 批注**（Comment）作为主形式，不改文档可见样式
  - 备选用浅蓝底色 `#E6F3FF`（与常见黄色区分）；并在 report 末尾给出"清理批注/底色"的一键命令

### Mo9. R10.2 "字节级等价" 不可达
- 现象：docx ZIP 含时间戳、随机 id；同一逻辑产物 ZIP 不会字节相等
- 建议：改为"以下三类语义级等价：所有段落 (style, text, runs.formatting) 序列一致；所有节属性一致；所有样式定义一致。提供 `tools/compare_docx.py` 做这个对比"

---

## 3. 轻微问题（Minor）

### m1. R2.2 失败结果对象类型未声明
建议：声明为 `LoadResult(ok=False, error=ErrorInfo(code, message))`

### m2. R5 缺超时与 token 上限
建议：追加 R5.9 "LLM 单次调用超时 ≤30s，max_tokens ≤4096，超时按重试策略处理"

### m3. R6 缺整体超时
建议：追加 R6.9 "整次 run 默认 timeout 10 分钟可配，超时强制写出 partial 报告"

### m4. R9.1 ambiguous_headings 阈值未定
建议：触发条件 = "段落标题级别识别置信度 < 0.7 的标题数 ≥ max(3, 总标题数的 10%)"

### m5. C5 evidence 字符上限未定
建议：追加 "evidence 文本最长 80 字符；超长截断并加 `...`，原文 hash 写到 metadata.text_hash"

### m6. C6 性能基准缺硬件锚
建议：追加 "基准硬件：Intel i5 12 代 / 16GB RAM / NVMe SSD / Win11"

---

## 4. 缺失需求（应补充）

### N1. 备份与原稿保护
**用户故事**：作为用户，我希望系统**绝不**修改我的输入文件。
**建议新增 R13.1**：
> THE 系统 SHALL 永远输出到 `<stem>_formatted.docx`，**不得**覆盖输入文件；若 `output_path == input_path`，编排层 SHALL 抛 `OverwriteInputError`

### N2. 日志级别入口
**建议新增 R11.8**：
> THE LOG_LEVEL SHALL 可通过环境变量 `THESIS_AGENT_LOG=DEBUG/INFO/WARN/ERROR` 或 CLI `--log-level` 配置，CLI 优先级更高

### N3. Profile / Tool / Check 的发现机制
**建议新增 R12.7**：
> THE 系统 SHALL 在启动时扫描 `thesis_agent/spec/profiles/` / `tools/` / `evaluators/checks/` 三个目录，自动注册其中所有符合协议的模块；新增模块**不需要**修改任何 `__init__.py`

### N4. 崩溃恢复
**建议新增 R6.10**：
> WHEN 进程崩溃且存在快照，下次以 `--resume <snapshot_dir>` 启动时 SHALL 能从最后一个成功 step 继续；trace 接续追加而非覆盖

### N5. GUI 集成时间表
**建议新增 R10.8**：
> 现有 GUI SHALL 在新链路稳定（v0.3）后增加"完成度报告"标签页；MVP（v0.1）阶段不强制要求 GUI 改动，CLI 出报告即满足验收

---

## 5. 待你拍板（建议默认值已给）

| 编号 | 待定项 | 建议默认 | 备选 |
|---|---|---|---|
| D1 | LLM 单次超时 | 30s | 60s（慢但稳） |
| D2 | LLM 重试次数 | 2 | 3（更宽容） |
| D3 | 整次 run 超时 | 10 min | 30 min（大文档） |
| D4 | confidence 阈值 | 0.7 | 0.6（少触发人在回路） / 0.8（更严） |
| D5 | max_iterations | 3 | 5（更耐心） |
| D6 | snapshot LRU 容量 | 10 | 5（省盘） / 30（方便回看） |
| D7 | LLM 成本估算开关 | 默认开启 | 默认关闭（隐私 / 不联网时） |
| D8 | docx 标注形式 | Word 批注 | 浅蓝底色 |

---

## 6. 跨需求一致性矩阵

把每个核心实体在各需求中的定义抽出来，看是否一致：

| 实体 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | 一致？ |
|---|---|---|---|---|---|---|---|---|
| `Rule` | ✅ 定义 | — | 引用 fix_tool | 引用 id / severity | 引用 id | 校验 fix_tool 绑定 | 引用 id | ✅ |
| `DocumentModel` | — | ✅ 定义只读 | **写** | 读 | 读 | 协调 | 读 | ⚠️ Mo3 |
| `ToolResult` | — | — | ✅ 定义 | — | — | 读 ok / changed_* | 引用 fix_attempts | ✅ |
| `EvalReport.status` | — | — | — | ✅ pass/fail/skip/error | — | 读 | **done/partial/failed/skipped** | ⚠️ M1 |
| `Diagnosis.confidence` | — | — | — | — | ✅ <0.7 → human | 引用 needs_human | 引用 | ✅ |
| `mode` | — | — | — | only_rule_ids | 是否调 LLM | 决定循环 | 决定输出 | ✅ |

**结论**：状态值（M1）和 DocumentModel 读写（Mo3）需要在文档中统一。

---

## 7. MVP 验收的可达性检查

逐项确认 MVP 能否在不开 R5（LLM）的前提下端到端跑通：

- ✅ R1 子集（4 维度规则）：编译器实现成本低，配 4 条 Rule 足够
- ✅ R2 接入：现有转换链直接复用
- ✅ R3 4 个 Tool：`tool_format_body` / `tool_assign_heading_styles` / `tool_insert_toc` / `tool_word_postprocess` 都是现成函数包装
- ✅ R4 评测：相应 4 个 check 实现简单
- ⚠️ **R5 mock**：MVP 用 mock diagnoser，对每条 fail 返回 `needs_human=True` → 没有实际修复 → MVP 端到端要求 `failed=0` 不可达
- ✅ R6 主循环：有 mock diagnoser 时第一轮 evaluate 后没有可执行的修复，按 R6.3 第三条退出
- ✅ R7 报告：按四档生成
- ✅ 端到端：用 `scau_perfect_thesis.docx`（fixture 假设已对齐 SCAU 模板）跑 mode=full 应直接 done=4，failed=0

**修订 MVP 验收**：
> "用 fixture **完美样本** 跑 mode=full，should 全部 pass；只用 fixture **不规范样本** 跑 mode=eval_only，应得到 failed/partial 报告项"
> 这样才能既验证 happy path 又验证规则真的能识破问题

---

## 8. 综合修订建议

下一步落地时，建议分两批改 requirements.md：

**批次一（无歧义，可立刻应用）**
M1 / M2 / M3 / Mo1 / Mo2 / Mo3 / Mo4 / Mo6 / Mo7 / Mo8 / Mo9 / m1 / m2 / m3 / m4 / m5 / m6 / N1 / N2 / N3 / N4 / N5 / MVP 验收文案

**批次二（需要你确认）**
Mo5（confidence 由谁定）/ D1 ~ D8（默认值）

如果你同意上述修订思路，我立刻把批次一全部落到 requirements.md，并把批次二在文档里以 `<!-- TODO: 待用户确认 D1=30s -->` 形式标出来等你拍板。
