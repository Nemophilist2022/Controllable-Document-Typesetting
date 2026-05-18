# AI 论文排版 Agent —— 需求文档

> 本文档与 `2026-04-15-ai-thesis-agent-architecture-design.md` 配套使用。
> 设计文档回答 **"怎么做"**，本文档回答 **"做什么、做到什么程度算完成"**。
> 每条需求都有可验证的验收条件，逐条评审。

## 1. 介绍

### 1.1 目的
基于现有 `thesis_formatter/*` 确定性算子库，新建 `thesis_agent/` 上层，提供一个可控的论文格式自动化交付系统：
- 用户给出原稿与模板规约
- 系统执行格式化
- 系统输出最终 docx **以及一份明确的完成度报告**：完成什么、未完成什么、为什么没完成

### 1.2 范围
- 在范围内：架构骨架、各层接口契约、MVP 端到端跑通、与现有代码的衔接
- 不在范围内：替代 Word 的 docx 渲染、内容查重润色、Web/在线协作版、PDF/LaTeX 输出

### 1.3 成功标准（整体验收）
1. `mode=fast` 路径行为与现行 `thesis_runner.run_format` 完全一致，所有现有 `tests/test_*.py` 全绿
2. `mode=full` 对内置 SCAU 样本 `tests/scenarios/fixtures/scau_perfect_thesis.docx` 跑通，输出 docx 与 `mode=fast` **语义级等价**（见 R10.2 定义），`report.json.summary` 为全 done
3. `mode=eval_only` 跑通后只产出 `report.md` + `report.json` + `trace.jsonl`，**输入文件保持不变**（见 R13.1）
4. 每条本文档列出的需求都有对应的自动化测试，并全部通过

### 1.4 术语表（Glossary）

| 术语 | 含义 |
|---|---|
| RuleSet | 模板规约编译后的机器可读规则集合 |
| Rule | 单条格式规则，含 id / scope / locator / predicate / expected / severity / fix_tool |
| Tool | 一个被 harness 显式注册、对文档执行确定性修改的算子 |
| ToolResult | Tool 的统一返回，含 ok / 改动列表 / 回滚 token |
| Evaluator / Check | 规则评测器，纯规则不调 LLM |
| EvalReport | 一次评测的聚合结果 |
| Diagnosis | LLM 对失败规则给出的根因 + 修复 ToolCall 列表 |
| Orchestrator / Harness | 主循环，负责 plan → act → eval → diagnose → replan |
| DeliveryReport | 交付层产出的人/机两份完成度报告 |
| Profile | 一份具名的 RuleSet（如 `scau_2024`、`generic_gb7714`） |
| 完成度状态 | done / partial / failed / skipped 四种之一 |
| Locator | 把规则 / 评测结果定位到具体段落、节、表格、样式的引用 |
| Trace | 全程 jsonl 日志，每条工具/评测/LLM 调用都落记录 |

---

## 2. 需求列表

### Requirement 1: 模板规约（RuleSet）管理

**用户故事**
作为同学院的论文模板维护者，我希望用一份 YAML（或现有 `defaults/scau_2024.yaml`）就能描述一所学校的全部格式要求，并被系统编译成可执行的规则集合，以便不写代码就能换学校、换院系。

**验收条件**

1.1 THE 系统 SHALL 提供 `thesis_agent/spec/rule_set.py`，定义 `Rule` 与 `RuleSet` 数据结构，且字段与设计文档第 3.2 节签名一致

1.2 THE 系统 SHALL 提供 `thesis_agent/spec/compiler.py`，可把 `defaults/scau_2024.yaml` 编译成 `RuleSet`

1.3 编译后的 `RuleSet` SHALL 至少覆盖以下规则维度：页面、字体字号、标题样式、标题编号、正文段落、图表题、三线表、目录、参考文献、页眉、页码、前置页

1.4 WHEN YAML 中存在编译器无法识别的字段（含嵌套字段），THE 编译器 SHALL 跳过该字段，**递归遍历**整个 YAML，把每个未知 key 以 dotted path（如 `body.unknown_subkey`）形式写入 `RuleSet.metadata.unknown_keys`，并在日志中给出 warning，不抛异常

1.5 IF 在合并所有 YAML 来源（base profile + 用户 override + CLI 覆盖）后的最终规则集合中存在重复的规则 id，THEN 编译器 SHALL 抛 `DuplicateRuleError` 并停止编译；单一 YAML 源里的重复 key 由 yaml 加载器先报错

1.6 THE `Rule.severity` SHALL 限定为 `must` / `should` / `info` 三种之一；其他值在编译期被拒绝

1.7 THE 系统 SHALL 提供 `thesis_agent/spec/profiles/scau_2024.py`，引用 `defaults/scau_2024.yaml`，使 `load_profile("scau_2024")` 等价于读 YAML 后再 `compile()`

---

### Requirement 2: 文档接入与归一化

**用户故事**
作为用户，我希望不管原稿是 docx / doc / txt / md / tex，都能用同一套上层流程处理；并且上层模块不需要直接依赖 `python-docx`。

**验收条件**

2.1 THE `thesis_agent/ingest/document_loader.py` SHALL 复用 `thesis_runner.find_pandoc` / `convert_doc_to_docx` 等现有转换链，不重复实现转换逻辑

2.2 WHERE 输入为 `.doc` 且当前环境无 Word COM，THE loader SHALL 返回 `LoadResult(ok=False, error=ErrorInfo(code="word_com_unavailable", message=...))`，而非直接抛 `WindowsError`；`LoadResult` 与 `ErrorInfo` 数据结构在 `ingest/types.py` 定义

2.3 THE 系统 SHALL 提供 `DocumentModel`，封装段落、节、样式、表格、图片、域六类对象，并提供两套 API：
   - **读 API**（供 Evaluator / Diagnoser 调用）：纯查询，返回不可变快照
   - **受控写 API**（供 Tool 调用）：每次写操作自动追踪到 `changed_paragraphs` / `changed_styles` / `changed_sections`，由 Tool 在 `ToolResult` 中带回

2.4 WHILE 任何 Tool / Evaluator / Diagnoser 运行，IT SHALL 通过 `DocumentModel` 访问文档，**不得直接 import `from docx import Document`**（强制约束，由代码评审与 lint 规则保证）；`DocumentModel` 内部允许使用 python-docx

2.5 WHEN 自然语言模板（如学校规范 PDF / md）经 `template_loader.from_natural_language()` 被抽成 YAML，THE 系统 SHALL 把生成的 YAML 写到磁盘，并返回 `pending_human_review=True`，**未审核状态下不得自动进入 RuleSet**

2.6 IF `template_loader.from_yaml()` 读到的 YAML 与 `DEFAULT_CONFIG` 完全无法 deep-merge（如顶层不是 dict），THEN 应抛 `InvalidTemplateError`

---

### Requirement 3: 工具层（Tools）

**用户故事**
作为编排层，我希望所有对文档的修改都通过显式注册的工具完成，每个工具签名一致、可幂等、可回滚，方便我安全地组合调度。

**验收条件**

3.1 THE 系统 SHALL 提供 `thesis_agent/tools/base.py`，定义 `Tool` 协议、`ToolResult`、`ToolContext` 三个类型

3.2 每个 Tool SHALL 满足：
   - 有 `name` / `description` / `input_schema` / `requires` / `idempotent` 五个静态属性
   - `run(doc, params, ctx) -> ToolResult` 不抛未捕获异常；任何异常以 `ToolResult(ok=False, message=...)` 返回
   - 在执行前由 `ctx.snapshot_mgr.take()` 打 docx 快照，结果中带回 `rollback_token`

3.3 THE 系统 SHALL 至少包装下列**原子 Tool**（与现有函数一一对应，包装不重写）：
   `tool_setup_page_layout` / `tool_assign_heading_styles` / `tool_renumber_headings` / `tool_normalize_heading_spacing` / `tool_format_body` / `tool_setup_multilevel_list` / `tool_format_figure_captions` / `tool_format_table_captions` / `tool_format_three_line_tables` / `tool_format_references` / `tool_setup_headers` / `tool_setup_page_numbers` / `tool_setup_page_numbers_strict` / `tool_insert_toc` / `tool_insert_cover_and_declaration` / `tool_word_postprocess`

3.4 IF 一个 Tool 在 `requires` 里声明依赖 `tool_X`，THE 编排层在调度时 SHALL 校验 `tool_X` 已在本次 plan 中执行过；未执行则**抛 `MissingPrerequisiteToolError`**，本次 plan 中止；编排层捕获后写入 trace 并按 R6.3 退出条件之一处理

3.5 WHEN Tool 执行成功，IT SHALL 返回精确的 `changed_paragraphs` / `changed_styles` / `changed_sections` 列表，供评测层做局部重检

3.6 THE 工具注册表 (`tools/registry.py`) SHALL 提供 `get(name) -> Tool` / `all_tools() -> list[Tool]` 两个 API；未注册的 `name` 抛 `UnknownToolError`

3.7 Tool **不得调用其他 Tool**；任何"组合操作"必须由编排层显式拼装

---

### Requirement 4: 规则评测层（Evaluators）

**用户故事**
作为质量门禁，我希望用同一份 RuleSet 既驱动执行也驱动校验，避免"既当裁判又当运动员"，并且评测过程不调 LLM。

**验收条件**

4.1 THE 系统 SHALL 提供 `thesis_agent/evaluators/runner.py: evaluate(doc, rule_set, only_rule_ids=None) -> EvalReport`

4.2 THE 评测层 SHALL **不得调用 LLM**；任何对外网/LLM 的依赖在评测代码中应触发代码评审拒绝

4.3 每条 `Rule` SHALL 对应**一个**确定性的 check 函数；check 输出 `CheckResult`，字段含 `rule_id` / `status` / `evidence` / `locator_resolved` / `severity`

4.4 THE 系统 SHALL 把现有 `thesis_formatter/structure.py: validate_structure` 与 `_common._check_caption_numbering` 的逻辑**复用并包装**为 Evaluator，不重写

4.5 WHEN `only_rule_ids` 非空，THE evaluator SHALL 只跑这些规则；这是为支持增量评测（Tool 改了哪些规则就只重测哪些）

4.6 状态值定义如下，须严格区分：
   - `pass`：规则在本上下文中评测通过
   - `fail`：规则适用且评测**未通过**
   - `skip`：规则在本上下文**不适用**（如 `mode=targeted` 跳过目录时，目录条目数规则）
   - `error`：规则适用但因 locator 找不到目标、文档异常等原因**无法判断**；`evidence` 中必须说明原因
   - 报告层（R7.4）映射规则：`pass→done` / `fail→partial 或 failed`（取决于是否有修复尝试）/ `skip→skipped` / `error→failed`，并把 `evaluation_error: <reason>` 写入 `diagnosis.rationale`

4.7 THE `EvalReport.summary` SHALL 至少包含 `total / pass / fail / skip / error` 五个字段（评测层原始口径）；交付层报告按 R7.2 的 `done / partial / failed / skipped` 四档汇总，两套口径转换关系由 R4.6 定义

4.8 THE 评测层 SHALL 在 100 段以下的文档上 1 秒内跑完一次全量评测（性能基准）

---

### Requirement 5: AI 诊断层（Diagnoser）

**用户故事**
作为系统，我希望规则评测失败时能调用 LLM 给出根因和修复计划，但 LLM 的输出必须是结构化的 ToolCall，**不能直接动文档**。

**验收条件**

5.1 THE 系统 SHALL 提供 `diagnoser/diagnoser.py: diagnose(report, doc, llm) -> list[Diagnosis]`

5.2 LLM 调用 SHALL 通过 `LLMClient` 抽象类访问，便于切换 OpenAI 兼容、本地模型、mock 三种后端

5.3 LLM 输出 SHALL 走 JSON Schema 校验；校验失败 SHALL 重试 ≤2 次，再失败则 `Diagnosis.needs_human=True`

5.4 LLM **绝不允许**返回以下形式：
   - 直接 docx XML / OOXML 节点
   - 跳过 Tool 自己写文档的指令
   - 不在 `RuleSet` 里的"自创规则"
   每种情况由 prompt + 后置校验双重防护，违反时拒绝并记录到 trace

5.5 `Diagnosis.confidence` 的生成与处理 SHALL 满足：
   - 由 LLM 在 JSON 输出中**自报**（system prompt 强制要求）
   - 系统侧夹紧到 `[0.0, 1.0]`
   - 同一 `(rule_id, evidence_hash)` 在本次 run 中第二次仍 fail 时，confidence 强制降至 ≤0.5
   - IF `confidence < 0.7`，THEN `needs_human` 自动置为 `True`（阈值见 D4，可配）

5.6 THE 系统 SHALL 缓存 `(rule_id, evidence_hash) -> Diagnosis`，命中缓存时不调用 LLM；`evidence_hash` 定义为
   `sha256(rule_id + "\n" + locator_canonical_json + "\n" + evidence_text_normalized)`，
   其中 `evidence_text_normalized` 去除多余空白与全角空格

5.7 WHERE 未配置任何 LLM 凭据，THE 诊断层 SHALL 跳过 LLM 调用，对每条 failure 返回 `Diagnosis(needs_human=True, fix_plan=[], rationale="未配置 LLM")`，不报错

5.8 THE LLM 接口 SHALL 默认禁用流式输出（防止解析中途中断），并设置 `temperature ≤ 0.2`

5.9 LLM 单次调用 SHALL 满足：超时 ≤30s（见 D1）、`max_tokens ≤4096`；超时按 R5.3 重试策略处理；累计超时 SHALL 写入 `report.json.meta.llm_timeouts_count`

---

### Requirement 6: 编排循环（Orchestrator）

**用户故事**
作为最高层调度器，我希望按 plan → act → eval → diagnose → replan 的固定循环跑流程，并能在收敛、超步数、人工介入时正确停下。

**验收条件**

6.1 THE 系统 SHALL 提供 `orchestrator/harness.py: run(input_path, profile, mode, options) -> DeliveryReport`

6.2 主循环 SHALL 严格按下列步骤推进，**不得调换顺序**：plan v1 → act → evaluate → diagnose → policies gate → replan → goto act

6.3 主循环 SHALL 在以下条件之一时退出：
   - 评测中所有 `severity=must` 的规则全部 pass
   - `iteration >= options.max_iterations`（默认 3，见 D5）
   - 新计划与上一轮计划**等价**（防死循环）；等价定义为：两个 plan 的 `tool` 序列完全一致，且每一步 `params` 的 canonical_json 完全相同
   - 用户在 human-in-loop 暂停点选择"取消"
   - 整次 run 已达全局 timeout（见 R6.9）

6.4 WHEN 任意 Tool 返回 `ok=False`，THE 编排层 SHALL **步级回滚**：仅回滚失败 step 自身的快照，本 plan 中已完成 step 的副作用保留；fail 写入 trace；本 plan 剩余 step 不再执行；下一轮 evaluate 重新校验当前文档状态。若需更激进的"plan 级回滚"，由 `policies.rollback_strategy="step"|"plan"` 控制，默认 `step`

6.5 IF `mode=dry_run`，THEN 主循环跑完 plan v1 + evaluate + diagnose 后停止，**不写出 docx**，只写 report

6.6 IF `mode=fast`，THEN 主循环退化为直接调用现有 `thesis_runner.run_format`，evaluators / diagnoser **整个跳过**

6.7 THE 编排层 SHALL 把每一次 plan / act / eval / diagnose / replan 写入 `trace.jsonl`

6.8 THE 编排层在执行前 SHALL 校验 `RuleSet` 与已注册 Tool 的兼容性：每条 `Rule.fix_tool` 必须能在 registry 中找到，否则抛 `UnboundFixToolError`

6.9 THE 整次 `run()` SHALL 受全局 timeout 约束（默认 10 min，见 D3，可由 `options.timeout_sec` 覆盖）；超时后立即停止后续 step，强制走交付层把当前进度写为 partial 报告，**不抛异常退出**

6.10 WHEN 进程崩溃且 `<stem>_snapshots/` 与 `<stem>_trace.jsonl` 仍存在，下次以 `--resume <stem>_trace.jsonl` 启动时 SHALL 能从最后一个成功 step 继续；trace 接续追加而非覆盖；恢复期间已 LLM 缓存的 Diagnosis 不重新调用

---

### Requirement 7: 完成度报告（Delivery）

**用户故事**
作为用户，我打开报告时必须立刻看到——"哪些做了、哪些没做、为什么没做、我下一步该改什么"。这是"完全可控"的核心可见证据。

**验收条件**

7.1 THE 系统在每次运行结束 SHALL 输出至少四个产物，文件名以输入 stem 为前缀：
   - `<stem>_formatted.docx`（mode=eval_only / dry_run 时不输出）
   - `<stem>_report.md`
   - `<stem>_report.json`
   - `<stem>_trace.jsonl`

7.2 THE `report.json.summary` SHALL 至少包含 `total / done / partial / failed / skipped` 五个键

7.3 THE `report.json.items` 的每一项 SHALL 至少包含：`rule_id` / `status` / `severity` / `evidence` / `locator` / `fix_attempts` / `diagnosis`（diagnosis 在未触发 LLM 时为 null）

7.4 报告中的 `status` 字段 SHALL 严格为 `done / partial / failed / skipped` 之一，定义如下：
   - `done`：规则评测 pass
   - `partial`：评测 fail，但已尝试修复，且诊断认为需要人工二次确认或仍有遗留
   - `failed`：评测 fail，且尝试修复无果或被策略拦截
   - `skipped`：本次模式或前置条件未触发该规则（如 mode=targeted 没跑目录）

7.5 THE `report.md` SHALL 按 ✅ 已完成 / ⚠️ 部分完成 / ❌ 未完成 / ⏭ 已跳过 四个区块组织，每条至少含一行可执行的"操作建议"

7.6 IF 文档包含可定位的 partial / failed 项（如"图 6 编号不连续"），THEN 系统 SHALL 优先以 **Word 批注（Comment）** 形式标注对应段落；若 Word 批注不可用（如 docx 写入受限），降级为浅蓝底色 `#E6F3FF`（避开常见的黄色高亮以免与原文冲突）。报告 `report.md` 末尾 SHALL 给出"清理批注 / 底色"的一键说明

7.7 THE `trace.jsonl` 每行 SHALL 是合法 JSON，字段至少含 `ts` / `kind` / `payload`；`kind` ∈ {`plan`,`tool_call`,`tool_result`,`eval`,`diagnose`,`policy`,`error`}

---

### Requirement 8: 运行模式控制

**用户故事**
作为不同场景下的用户（赶时间、只想评测、只改局部），我希望用一个 `mode` 参数控制系统行为，且各模式的副作用边界清晰。

**验收条件**

8.1 THE 系统 SHALL 支持以下 6 种 `mode`：`full` / `fast` / `eval_only` / `diagnose_only` / `targeted` / `dry_run`

8.2 各模式的副作用边界 SHALL 严格按下表：

| mode | 改 docx | 跑 evaluate | 跑 diagnose（LLM） | 写 docx | 写 report |
|---|---|---|---|---|---|
| full | 是 | 是 | 是 | 是 | 是 |
| fast | 是 | 否 | 否 | 是 | 是（仅汇总，不含规则级评测） |
| eval_only | 否 | 是 | 否 | 否 | 是 |
| diagnose_only | 否 | 是 | 是 | 否 | 是 |
| targeted | 是（局部） | 局部 | 否 | 是 | 是 |
| dry_run | 否 | 是 | 是 | 否 | 是 |

8.3 `mode=targeted` SHALL 直接复用现有 `only_insert` 局部模式（cover / toc / page_numbers / header_footer），且与设计文档"标准模式互斥"约束一致

8.4 IF 用户传入未列出的 mode，THEN 系统 SHALL 抛 `InvalidModeError` 并列出合法值

8.5 THE 默认 mode SHALL 为 `full`；GUI 默认勾选 `full`；CLI 默认 `full`；现有 `thesis_format_cli.py` 不传 `--mode` 时 SHALL 走 `fast` 以保证兼容

---

### Requirement 9: 人在回路与可控性

**用户故事**
作为用户，我希望对高风险或低置信度的修改有最终决定权，系统不能"静默地"做我不知情的大改。

**验收条件**

9.1 THE `policies.py` SHALL 暴露 `human_in_the_loop_at: list[str]` 配置项，默认包含：`front_matter` / `cover` / `ambiguous_headings` / `destructive_ops`。各触发点的具体条件：
   - `front_matter`：前置页识别置信度 < 0.7
   - `cover`：用户启用了"自动生成封面"且原稿已检测到疑似封面页
   - `ambiguous_headings`：识别置信度 < 0.7 的标题段落数 ≥ `max(3, 总标题数 × 10%)`
   - `destructive_ops`：诊断器输出的 `fix_plan` 中含删除 / 重排 / 跨节移动等不可逆操作

9.2 WHEN `auto_apply_diagnosis="confirm"`，THE 编排层在执行任何 `needs_human=True` 的 Diagnosis 前 SHALL 暂停，写出 `<stem>_pending.json`，并在 GUI / CLI 提示用户

9.3 IF `auto_apply_diagnosis="no"`，THEN 系统 SHALL 把所有 `needs_human=True` 的诊断写入 report.partial，并继续处理其他诊断

9.4 IF 用户使用 `--resume <pending.json>`，THE 系统 SHALL 从暂停点恢复，已执行的 Tool 不重跑

9.5 THE 系统 SHALL **绝不**在以下场景默认执行高风险操作（即使 confidence 高）：
   - 删除原稿中的段落（即使诊断认为是冗余）
   - 修改非格式相关的内容文字（标点符号自动规范、错别字纠正等不属于本系统职责）
   - 重排前置页顺序

9.6 IF 用户在配置中关闭 `human_in_the_loop_at` 全部触发点（强制全自动），THE 系统 SHALL 在日志中打 prominent warning：`已关闭人在回路，所有修改将自动执行，请审阅最终输出`

---

### Requirement 10: 与现有代码兼容

**用户故事**
作为现有用户，我不希望升级后老命令、老配置、老 GUI、老测试套有任何回归。

**验收条件**

10.1 THE 现有 `thesis_runner.run_format` 接口签名 SHALL 不变；其内部可改为转发到 `harness.run(mode="fast")`，但外部行为完全等价

10.2 THE 现有 `thesis_format_cli.py` 不带任何新参数运行时，SHALL 与改造前**语义级等价**：所有段落 (style_id, text, run.formatting) 序列一致；所有节属性一致；所有样式定义一致。docx ZIP 内的时间戳、随机 id 等不参与比对。系统 SHALL 提供 `tools/compare_docx.py` 实现该比较；CI 用此工具守护回归

10.3 THE 现有 `defaults/scau_2024.yaml` SHALL 不需要任何修改即可被 `compile()` 编译为 RuleSet；用户旧的 `thesis_config.yaml` 也同此

10.4 现有 `tests/test_*.py` 全部 SHALL 在不修改的前提下继续通过（除非测试本身依赖了被弃用的内部接口；此情况需在 PR 中显式列出并迁移）

10.5 THE 现有 GUI（`thesis_gui.py`） SHALL 不被破坏；新功能（完成度报告标签页）以**新增**形式出现，不替换原有面板

10.6 THE `thesis_formatter/*` 现有公开函数签名 SHALL 不变；新行为通过新增参数（带默认值）或新增函数加入

10.7 IF Tool 包装层需要现有函数支持新参数（如 `dry_run`），THEN 该参数 SHALL 默认值为现有行为，不影响老调用

10.8 GUI 集成 SHALL 分阶段引入：MVP（v0.1）阶段不强制要求 GUI 改动，CLI 出报告即满足验收；新链路稳定后（v0.3）再在 GUI 中新增"完成度报告"标签页

---

### Requirement 11: 可观测性与审计

**用户故事**
作为开发者排查问题、作为用户做审计，我都希望能看到"系统到底干了什么"。

**验收条件**

11.1 THE 系统 SHALL 在每次 run 输出 `<stem>_trace.jsonl`，每行一条 JSON 记录

11.2 THE trace 记录类型至少包含：`plan` / `tool_call` / `tool_result` / `eval` / `diagnose` / `policy` / `error` / `llm_request`（仅在 LOG_LEVEL=DEBUG 时） / `llm_response`（仅在 LOG_LEVEL=DEBUG 时）

11.3 WHILE LOG_LEVEL=DEBUG，THE 系统 SHALL 把 LLM 的 prompt 与 raw response 落到 trace；非 DEBUG 时仅落 `model_id` / `token_usage`

11.4 THE 系统 SHALL 在 `<stem>_snapshots/` 下保留每个 Tool 调用前的 docx 快照，文件名 `step_<n>_<tool_name>_pre.docx`

11.5 THE 快照保留策略 SHALL 可配（默认保留最近 10 步）；超出后旧快照按 LRU 删除，记录到 trace

11.6 THE `report.json.meta` SHALL 包含：`profile` / `mode` / `iterations` / `duration_ms` / `tool_calls_count` / `llm_calls_count` / `git_sha`（如可获取）

11.7 IF 任何 LLM 调用产生费用，THE 系统 SHALL 把估算 token 与成本写入 `report.json.meta.llm_cost_estimate_usd`，缺省 0

11.8 THE 日志级别 SHALL 可由环境变量 `THESIS_AGENT_LOG=DEBUG/INFO/WARN/ERROR` 或 CLI `--log-level` 配置，CLI 优先级更高；默认 INFO

---

### Requirement 12: 配置与扩展性

**用户故事**
作为后续维护者 / 第三方学校，我希望加新规则、新 Tool、新模板时**不动核心代码**。

**验收条件**

12.1 新增一条 Rule SHALL 不需要修改 `evaluators/runner.py`；只需在某个 `checks/check_*.py` 中实现 check 并注册到对应的 predicate 调度表

12.2 新增一个 Tool SHALL 不需要修改 `orchestrator/harness.py`；只需在 `tools/registry.py` 注册

12.3 新增一个 Profile SHALL 仅需新增 `spec/profiles/<name>.py` 与 `defaults/<name>.yaml` 两个文件，不动既有 profile

12.4 THE 系统 SHALL 提供 `thesis-agent list profiles` / `list tools` / `list rules <profile>` 三个内省命令

12.5 THE 配置项的优先级 SHALL 自高到低为：CLI 参数 > 输入目录的 `thesis_config.yaml` > 可执行文件目录的同名文件 > 内置默认（与现有 `resolve_config` 行为一致）

12.6 IF 用户给 Profile 提供了一份"差异 YAML"（只覆盖个别字段），THE compiler SHALL 用 deep-merge 与 base profile 合并，不要求用户复制全量配置

12.7 THE 系统 SHALL 在启动时**自动扫描**注册三个目录下的模块：
   - `thesis_agent/spec/profiles/*.py`
   - `thesis_agent/tools/*.py`（实现了 Tool 协议的类）
   - `thesis_agent/evaluators/checks/check_*.py`
   新增模块**不需要**修改任何 `__init__.py` 或核心代码；扫描失败的模块写入 trace 但不阻塞启动

---

### Requirement 13: 数据安全与原稿保护

**用户故事**
作为用户，我希望系统**绝不**修改我的输入文件，输出文件名永远是新的，避免误操作覆盖原稿。

**验收条件**

13.1 THE 系统 SHALL 永远输出到 `<stem>_formatted.docx`，**不得**覆盖输入文件；IF `output_path == input_path`（解析后的绝对路径），THEN 编排层 SHALL 抛 `OverwriteInputError` 并立即退出

13.2 THE 系统 SHALL 在每次写出 docx 前校验目标路径，若已存在同名文件，SHALL 自动追加 `_1` / `_2` 等后缀，避免静默覆盖；该行为可由 `options.overwrite_output=true` 关闭

13.3 任何向 LLM 发送的请求 SHALL **不携带**原稿正文长串内容；只允许传：规则 id、locator、evidence 摘要（≤80 字符）、上下文段落 hash。该约束由 `LLMClient` 出站 hook 强制校验，违反时拒绝发送并落 trace

---

## 3. 跨需求约束（横切要求）

下列约束适用于所有需求：

- **C1 中文优先**：用户可见输出（report.md、CLI 提示、GUI 文案）一律为简体中文；代码注释、技术术语可保留英文
- **C2 平台**：核心逻辑 SHALL 在 Windows / macOS / Linux 三平台都能跑通；Word COM 后处理仅在 Windows + Word 环境启用，其他平台优雅降级
- **C3 Python 版本**：>=3.10
- **C4 依赖**：除 LLM 客户端外，新模块新增依赖须经评审；优先复用现有 `python-docx` / `pyyaml` / `pywin32` / `ttkbootstrap`
- **C5 安全**：trace 与报告中**不得**包含原稿正文长串内容；evidence 文本最长 80 字符，超长截断并加 `…`，原段落 hash 写入 metadata.text_hash；仅含段落 idx / hash / 简短 evidence；防止论文外泄
- **C6 性能**：100 段以下文档，`mode=full` 一次运行（含 LLM 调用 ≤3 次）耗时 ≤30s（不含 Word COM 后处理时间）。基准硬件：Intel i5 12 代或同档 / 16GB RAM / NVMe SSD / Win11；其他平台允许 ±50% 浮动
- **C7 可测试性**：每个 Tool / Evaluator / Diagnoser SHALL 有对应单测；端到端场景测试覆盖至少 3 种典型论文样本

---

## 4. MVP 验收（v0.1）

为尽快得到可演示版本，MVP 仅需满足以下子集：

- ✅ R1（基本 RuleSet 编译）：覆盖正文字体字号、行距、一级标题样式、目录条目数 4 个维度即可
- ✅ R2.1 / R2.3 / R2.4
- ✅ R3.1 / R3.2 / R3.6 / R3.7；R3.3 仅需提供 `tool_format_body` / `tool_assign_heading_styles` / `tool_insert_toc` / `tool_word_postprocess` 四个 Tool
- ✅ R4.1 / R4.2 / R4.3 / R4.4 / R4.7
- ⏭ R5（v0.2 再加 LLM；MVP 用 mock diagnoser，对每条 fail 返回 `needs_human=True`）
- ✅ R6.1 / R6.2 / R6.3 / R6.4 / R6.6 / R6.7
- ✅ R7.1 / R7.2 / R7.3 / R7.4 / R7.5 / R7.7
- ✅ R8.1 / R8.2 / R8.5（仅支持 `full` / `fast` / `eval_only`）
- ⏭ R9（v0.3 再做完整人在回路；MVP 不支持 resume）
- ✅ R10（**全部**，硬性兼容）
- ✅ R11.1 / R11.2 / R11.6 / R11.8
- ✅ R12.1 / R12.2 / R12.3
- ✅ R13.1 / R13.2（R13.3 LLM 出站 hook 在 v0.2 加 LLM 时一并）

MVP 的端到端验收（修订）：

- **Happy path**（验证整条链路在 MVP 范围内闭环）：
  1. 准备 fixture `scau_perfect_thesis.docx`，**用代码手工构造**，仅覆盖 MVP 4 条规则的"完美"状态（Normal 样式宋体 12pt + 1.5 倍行距 / 至少一个 Heading 1 段 / 含 TOC 或 TOC placeholder）。**禁止用 `mode=fast` 路径生成**，否则 fixture 会自带 fast 路径的全部副作用，不再是 MVP 范围内的"完美"。
  2. 跑 `thesis-agent run --input scau_perfect_thesis.docx --profile scau_2024 --mode full`
  3. 输出 4 个文件：docx / report.md / report.json / trace.jsonl
  4. 断言：
     - `report.json.summary.done >= 4`
     - `report.json.summary.failed == 0`
     - 4 个 MVP rule_id（`body.font.east_asia` / `body.font.size` / `body.line_spacing` / `heading.h1.style_present`）都在 `report.json.items` 中且 `status=="done"`
     - 输出 docx 文件存在且能被 `python-docx.Document(...)` 重新打开
  5. **不再做 `full ↔ fast` 段落级一致比对**：MVP 仅覆盖 4 个 Tool，`mode=full` 与 `mode=fast` 在样式表、节属性、题注域注入上必然不一致；该对比留给 v0.2 全集 Tool 落地后做。

- **Sad path**（验证规则真的能识破问题）：
  1. 准备 fixture `scau_messy_thesis.docx`（在 perfect 基础上引入：行距改为 2.0 倍 / 删掉 Heading 1 样式 / 目录条目数与正文标题数不一致 等至少 3 处违规）
  2. 跑 `mode=eval_only`
  3. 断言：
     - `report.json.summary.failed + partial >= 3`
     - 能列出对应 `rule_id` 与 `evidence`，并附可执行的"操作建议"（advice 字段非空）

---

## 5. 评审清单（逐条勾选）

> 评审时请逐条标 ✅ / ❌ / ⚠️。⚠️ 须在"评审意见"里写明歧义点，议定后再改本文档。

- [ ] R1.1 ~ R1.7 是否清晰、可测、覆盖完整
- [ ] R2.1 ~ R2.6 是否清晰、可测、覆盖完整
- [ ] R3.1 ~ R3.7 是否清晰、可测、覆盖完整
- [ ] R4.1 ~ R4.8 是否清晰、可测、覆盖完整
- [ ] R5.1 ~ R5.9 是否清晰、可测、覆盖完整
- [ ] R6.1 ~ R6.10 是否清晰、可测、覆盖完整
- [ ] R7.1 ~ R7.7 是否清晰、可测、覆盖完整
- [ ] R8.1 ~ R8.5 是否清晰、可测、覆盖完整
- [ ] R9.1 ~ R9.6 是否清晰、可测、覆盖完整
- [ ] R10.1 ~ R10.8 是否清晰、可测、覆盖完整
- [ ] R11.1 ~ R11.8 是否清晰、可测、覆盖完整
- [ ] R12.1 ~ R12.7 是否清晰、可测、覆盖完整
- [ ] R13.1 ~ R13.3 是否清晰、可测、覆盖完整
- [ ] C1 ~ C7 是否清晰、可测、覆盖完整
- [ ] MVP 切分是否合理，是否过紧或过松
- [ ] D1 ~ D8 默认值是否接受（见下表）

### 评审意见

> 在此填写每条的评审反馈。

```
R?.?: 
R?.?: 
```

---

## 6. 默认值冻结（D1 ~ D8）

> 以下默认值已确认冻结。改动需走 RFC 流程，更新后 bump 文档版本号。

| 编号 | 项 | 冻结值 | 关联条款 |
|---|---|---|---|
| D1 | LLM 单次调用超时 | 30s | R5.9 |
| D2 | LLM 输出校验失败重试次数 | 2 | R5.3 |
| D3 | 整次 run 全局超时 | 10 min（600s） | R6.9 |
| D4 | confidence 触发 needs_human 阈值 | 0.7 | R5.5 |
| D5 | max_iterations | 3 | R6.3 |
| D6 | snapshot 保留数量 | 10 | R11.5 |
| D7 | LLM 成本估算开关 | 默认开启 | R11.7 |
| D8 | docx 标注形式 | 优先 Word 批注，降级浅蓝底色 | R7.6 |

文档冻结日期：2026-04-15。后续如需调整，请新建 RFC 文档并明确指出哪些 D 值变更、原因与影响范围。
