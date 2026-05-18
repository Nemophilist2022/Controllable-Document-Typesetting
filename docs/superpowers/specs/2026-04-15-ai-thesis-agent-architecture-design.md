# AI 论文排版 Agent —— 整体架构设计

> 目标：基于现有 `thesis_formatter/*` 确定性算子库，构建一个**基于规则评测 + AI 诊断**的论文格式自动化交付系统。
> 用户指定模板与任务后，系统须给出最终 docx，并**明确说明哪部分完成、哪部分未完成、为什么没完成**。

## 一、设计目标与核心原则

### 1. 设计目标
- **完全可控**：每次运行都产出"完成度报告"，明确列出 done / partial / failed / skipped 四类结果及其原因。
- **模板可换**：换学校 = 换一份规约（YAML 或自然语言模板），不改代码。
- **可复现可审计**：每一步工具调用、每一次规则评测、每一次 LLM 调用都落 trace。
- **本地优先**：默认不依赖云端 LLM 也能完成 80% 工作；LLM 仅在规则覆盖不到的语义/版面歧义场景兜底。

### 2. 核心原则
1. **确定性优先，AI 兜底**：能用规则解决的（字体、字号、缩进、编号、分节、目录），全部用确定性算子 + 规则评测；AI 只做规则难以覆盖的诊断与歧义判断。
2. **Harness 化**：参考 agent harness 的"工具受限 + 全程 trace"思路。Agent 不直接改文档，只能调用显式注册的 Tool；每次调用前后打快照，结果可回放、可回滚。
3. **模板即规约（Template as Spec）**：模板被编译成机器可读的 `RuleSet`，既驱动执行、也驱动评测，二者用同一份事实源。
4. **三段闭环：执行 → 评测 → 诊断 → 重排**：每一段独立可跑、独立可测；中间产物均为结构化数据。
5. **完成度可见**：交付物不是单一 docx，而是 `docx + report.md + report.json + trace.jsonl`。

---

## 二、整体分层架构

```
┌────────────────────────────────────────────────────────────────────┐
│  交付层  Delivery                                                  │
│  最终 docx  +  完成度报告(md/json)  +  trace.jsonl  +  diff 视图    │
└────────────────────────────────────────────────────────────────────┘
                                ▲
┌────────────────────────────────────────────────────────────────────┐
│  编排层  Orchestrator (Agent Harness)                              │
│  Plan → Act → Evaluate → Diagnose → Replan 循环                    │
│  控制策略：max_iterations / 失败重试 / 人在回路 / 模式开关          │
└────────────────────────────────────────────────────────────────────┘
        ▲              ▲                ▲              ▲
┌───────┴──────┐ ┌─────┴────────┐ ┌─────┴────────┐ ┌──┴────────┐
│  执行层      │ │  评测层       │ │  诊断层       │ │  规约层    │
│  Tools       │ │  Evaluators   │ │  AI Diagnoser │ │  Spec     │
│ (确定性)     │ │  (纯规则)     │ │  (LLM)        │ │           │
│              │ │               │ │               │ │           │
│ 包装现有     │ │ check_*.py:   │ │ 看 failure +  │ │ Template  │
│ thesis_      │ │  fonts/toc/   │ │ 给根因 + 修复 │ │   ↓ 编译  │
│ formatter/*  │ │  headings...  │ │ 计划(ToolCall)│ │ RuleSet   │
└──────────────┘ └───────────────┘ └───────────────┘ └───────────┘
        ▲              ▲
┌───────┴──────────────┴─────────────────────────────────────────────┐
│  接入层  Ingestion                                                  │
│  原稿：docx / doc / txt / md / tex（沿用现有转换链）                 │
│  模板：YAML 直读 / 自然语言模板说明书 → LLM 抽 Spec → 落盘人工审核   │
└────────────────────────────────────────────────────────────────────┘
```

### 与"agent harness"思路的对应关系
| Harness 概念 | 在本系统的体现 |
|---|---|
| 工具白名单 | `tools/` 目录下显式注册的 Tool；Agent 不能直接调 `python-docx` |
| 状态机 | `Orchestrator.harness` 主循环：plan → act → eval → diagnose → replan |
| Trace / Replay | `delivery/trace.py` 落 jsonl，每条记录可重放 |
| 评测器 | `evaluators/`，规则与执行解耦，避免"既当裁判又当运动员" |
| 人在回路 | `policies.py` 暴露 `human_in_the_loop_at` 暂停点 |
| 工具沙箱 | 每个 Tool 调用前打 docx 快照，失败可回滚 |

---

## 三、核心模块设计

### 3.1 接入层 Ingestion

**职责**：把不同形式的原稿与模板，归一化为系统内部的 `DocumentModel` 与 `RuleSet`。

| 文件 | 职责 |
|---|---|
| `thesis_agent/ingest/document_loader.py` | `.docx/.doc/.txt/.md/.tex` → 标准 docx，**沿用现有 `thesis_runner.py` 的转换链**（pandoc / Word COM） |
| `thesis_agent/ingest/document_model.py` | docx → `DocumentModel`（段落、节、样式、表格、图片、域），上层只与本模型交互 |
| `thesis_agent/ingest/template_loader.py` | YAML → `RuleSet`；自然语言模板 → 调 LLM 抽 YAML，**抽完后必须落盘并请用户审一次** |

**关键设计**：所有上层模块（Tools / Evaluators / Diagnoser）只与 `DocumentModel` 打交道，不直接依赖 `python-docx`。这层薄抽象是后续替换底层（例如换 `docx2python` 或自研解析器）的关键。

### 3.2 规约层 Spec

**职责**：把"模板要求"翻译成机器可读的规则集合。

| 文件 | 职责 |
|---|---|
| `thesis_agent/spec/rule_set.py` | 定义 `Rule` / `RuleSet` 数据结构 |
| `thesis_agent/spec/compiler.py` | `scau_2024.yaml` → `RuleSet`（解耦"配置项"与"规则"，规则可比配置项更细） |
| `thesis_agent/spec/profiles/scau_2024.py` | 内置 profile，引用 `defaults/scau_2024.yaml` |

**`Rule` 数据结构**：
```python
@dataclass
class Rule:
    id: str                       # "body.font.east_asia"
    scope: Literal["doc","section","paragraph","run","table","style"]
    locator: dict                 # 如 {"style": "Normal"} 或 {"heading_level": 1}
    predicate: str                # equals / one_of / regex / range / exists
    expected: Any
    severity: Literal["must","should","info"]
    fix_tool: Optional[str]       # 修复用哪个 Tool
    fix_params_template: dict     # 修复参数模板（带 {expected} 占位）
```

**示例**：
```python
Rule(
    id="body.font.east_asia",
    scope="style",
    locator={"style_name": "Normal"},
    predicate="equals",
    expected="宋体",
    severity="must",
    fix_tool="tool_format_body",
    fix_params_template={"east_asia_font": "{expected}"},
)
```

### 3.3 执行层 Tools（Harness 的"手"）

**职责**：把现有 `thesis_formatter/*` 的每个能力，包装成统一签名的 Tool。

**Tool 协议**（`thesis_agent/tools/base.py`）：
```python
class Tool(Protocol):
    name: str                           # "tool_format_body"
    description: str                    # 给 LLM 看的英文/中文描述
    input_schema: dict                  # JSON Schema，用于 LLM 校验
    requires: list[str]                 # 依赖的前置 Tool（如 toc 依赖 heading）
    idempotent: bool                    # 是否幂等

    def run(self,
            doc: DocumentModel,
            params: dict,
            ctx: ToolContext) -> ToolResult: ...

@dataclass
class ToolResult:
    ok: bool
    changed_paragraphs: list[ParaRef]   # 改了哪些段落（locator）
    changed_styles: list[str]
    changed_sections: list[int]
    message: str
    warnings: list[str]
    rollback_token: str                 # snapshot id，用于回滚
```

**Tool 清单**（一一对应现有模块）：

| Tool | 包装的现有函数 |
|---|---|
| `tool_setup_page_layout` | `thesis_formatter/page.py: normalize_sections` 等 |
| `tool_assign_heading_styles` | `headings.auto_assign_heading_styles` |
| `tool_renumber_headings` | `headings.renumber_headings` |
| `tool_normalize_heading_spacing` | `headings.normalize_heading_spacing` |
| `tool_format_body` | `formatter.py` 内 body 段处理 |
| `tool_setup_multilevel_list` | `numbering.setup_multilevel_list` |
| `tool_format_figure_captions` | `numbering.setup_figure_captions` |
| `tool_format_table_captions` | `numbering.setup_table_captions` |
| `tool_format_three_line_tables` | `formatter._format_tables` |
| `tool_format_references` | `references.apply_ref_crosslinks` |
| `tool_setup_headers` | `headers.setup_headers` |
| `tool_setup_page_numbers` | `page.setup_page_numbers` |
| `tool_setup_page_numbers_strict` | `page.setup_page_numbers_strict`（已存在，单独改页码） |
| `tool_insert_toc` | `toc.insert_toc` |
| `tool_insert_cover_and_declaration` | `cover.insert_cover_and_declaration` |
| `tool_word_postprocess` | `word_postprocess.postprocess`（支持 `full / fields_only / none`） |

**关键约束**：
- 每个 Tool **只做一件事，幂等，能回滚**（调用前由 `Orchestrator.snapshot` 打快照）。
- Tool 不调用其他 Tool，组合由编排层负责。
- Tool 返回的 `changed_*` 字段供评测层做"局部重检"使用。

### 3.4 评测层 Evaluators（规则评测）

**职责**：跑 `RuleSet`，输出 `EvalReport`，**纯规则、不调 LLM**。

| 文件 | 职责 |
|---|---|
| `thesis_agent/evaluators/runner.py` | 主入口：跑全量或增量评测，聚合 `EvalReport` |
| `thesis_agent/evaluators/checks/check_page.py` | 页边距、装订线、纸张、页眉页脚距 |
| `thesis_agent/evaluators/checks/check_fonts.py` | 各级标题/正文字体字号 |
| `thesis_agent/evaluators/checks/check_headings.py` | 层级连续、编号连续、缩进、间距 |
| `thesis_agent/evaluators/checks/check_toc.py` | 目录条目数 vs 实际标题数、页码对齐 |
| `thesis_agent/evaluators/checks/check_captions.py` | 图表编号连续、题注字体 — **复用现有 `_check_caption_numbering`** |
| `thesis_agent/evaluators/checks/check_references.py` | 悬挂缩进、`[n]` 连号 |
| `thesis_agent/evaluators/checks/check_sections.py` | 分节、页眉页码作用域 |
| `thesis_agent/evaluators/checks/check_front_matter.py` | 摘要/Abstract/关键词存在性 — **复用现有 `validate_structure` 逻辑** |

**`CheckResult` 数据结构**：
```python
@dataclass
class CheckResult:
    rule_id: str
    status: Literal["pass","fail","skip","error"]
    evidence: str                     # 实际值，如 "宋体 → 实际为 SimSun"
    locator_resolved: dict            # 定位到具体段落 idx / 节 idx / 表格 idx
    severity: Literal["must","should","info"]
    metadata: dict                    # 给诊断器的额外上下文

@dataclass
class EvalReport:
    profile: str
    results: list[CheckResult]
    summary: dict                     # {total, pass, fail, skip, error}
    duration_ms: int
```

**复用策略**：现有的 `structure.validate_structure` 和 `_common._check_caption_numbering` 已经是事实上的"规则评测"，**不要重写，直接包装**为 `Evaluator`。

### 3.5 诊断层 AI Diagnoser

**职责**：仅在评测失败 / 评测无法判断时调用。看 `EvalReport.failed` 加文档上下文，输出**结构化诊断**。

| 文件 | 职责 |
|---|---|
| `thesis_agent/diagnoser/llm_client.py` | 抽象 LLM 接入（OpenAI / 本地 / 自研），同步异步两套 |
| `thesis_agent/diagnoser/prompts/` | 各类诊断 prompt 模板（按规则类型分文件） |
| `thesis_agent/diagnoser/diagnoser.py` | 主入口：`diagnose(report, model) -> list[Diagnosis]` |

**`Diagnosis` 数据结构**：
```python
@dataclass
class ToolCall:
    tool: str
    params: dict
    expected_effect: str

@dataclass
class Diagnosis:
    rule_id: str
    root_cause: str
    fix_plan: list[ToolCall]
    confidence: float                 # 0.0 ~ 1.0
    needs_human: bool                 # 置信度低时为 True
    rationale: str                    # 给用户看的解释
```

**LLM 三个使用场景**：
1. **诊断**：评测失败时，给出根因 + ToolCall 修复计划
2. **歧义判断**：段落是否为"标题"、"附录"、"参考文献"（带置信度）
3. **NL → Spec**：自然语言模板说明书抽取为 YAML（结果落盘 + 人工审核）

**LLM 严禁做的事**（`prompts/` 必须明确写在 system prompt 里）：
- 直接输出 docx XML 或 OOXML
- 跳过 Tool 自己改文档
- 决定是否执行高风险操作（决定权在 `Orchestrator.policies`）
- 编造规则（只能基于传入的 `RuleSet` 推理）

### 3.6 编排层 Orchestrator（Agent Harness 主循环）

**职责**：组合执行 → 评测 → 诊断 → 重排，是"完全可控"的核心。

| 文件 | 职责 |
|---|---|
| `thesis_agent/orchestrator/planner.py` | 生成执行计划（默认计划 + LLM 重排） |
| `thesis_agent/orchestrator/harness.py` | 主循环 |
| `thesis_agent/orchestrator/snapshot.py` | docx 快照 / 回滚 |
| `thesis_agent/orchestrator/policies.py` | 重试 / 收敛 / 人工介入策略 |

**主循环伪代码**：
```python
def run(input_path, profile, mode, options) -> DeliveryReport:
    # 1. 接入
    doc_model = ingest.load_document(input_path)
    rule_set  = ingest.load_template(profile)

    # 2. 初始计划
    plan = planner.default_plan(rule_set, mode)

    snapshots = [snapshot.take(doc_model)]
    trace = Trace()

    # 3. 主循环
    for iteration in range(policies.max_iterations):
        # 3a. 执行
        for step in plan:
            ctx = ToolContext(trace=trace, snapshot_mgr=snapshots)
            result = tools[step.tool].run(doc_model, step.params, ctx)
            trace.record(step, result)
            if not result.ok:
                snapshots.rollback_last()
                break

        # 3b. 评测
        report = evaluators.run(doc_model, rule_set)
        trace.record_eval(report)

        if report.all_pass(severity="must"):
            break

        # 3c. 诊断
        diagnoses = diagnoser.diagnose(report, doc_model, llm_client)
        trace.record_diagnoses(diagnoses)

        # 3d. 人在回路
        diagnoses = policies.gate_human_in_loop(diagnoses, options)

        # 3e. 重排
        new_plan = planner.replan(diagnoses, plan)
        if new_plan == plan:
            break          # 防死循环
        plan = new_plan

    # 4. 交付
    return delivery.build_report(doc_model, rule_set, report, trace, snapshots)
```

**模式开关**（"完全可控"的关键）：
| 模式 | 含义 |
|---|---|
| `mode=full` | 完整流程，evaluate + diagnose + replan |
| `mode=fast` | 现有 `thesis_runner` 的快通道（不评测、不诊断） |
| `mode=eval_only` | 只跑评测，输出报告，不改文档 |
| `mode=diagnose_only` | 跑评测 + 诊断，输出修复建议但不执行 |
| `mode=targeted` | 复用现有 `only_insert` 局部模式（封面/目录/页码/页眉） |
| `mode=dry_run` | 全流程模拟，输出会改什么但不真正落盘 |

**控制开关**：
- `max_iterations: int = 3`
- `auto_apply_diagnosis: Literal["yes","confirm","no"] = "confirm"`
- `human_in_the_loop_at: list[str] = ["front_matter","cover","ambiguous_headings"]`
- `severity_gate: Literal["must","should","info"] = "must"`（必须全部通过的最低严重度）

### 3.7 交付层 Delivery

**这一层是"完成什么、没完成什么必须说明"的落点**。

| 文件 | 职责 |
|---|---|
| `thesis_agent/delivery/report.py` | 生成 `report.md`（人看）+ `report.json`（机读） |
| `thesis_agent/delivery/diff_view.py` | 段落级 hash diff，输出 `diff.html` |
| `thesis_agent/delivery/trace.py` | jsonl trace |

**输出文件清单**：
1. `<论文>_formatted.docx` —— 最终文档
2. `<论文>_report.md` —— 人看的完成度报告
3. `<论文>_report.json` —— 机读的完成度报告
4. `<论文>_trace.jsonl` —— 全程 trace
5. `<论文>_diff.html` —— 关键差异视图（可选）

**`report.md` 结构示例**：
```markdown
# 论文排版完成度报告

- 文件：论文.docx
- 模板：scau_2024
- 模式：full
- 用时：12.3s

## ✅ 已完成 (32 / 41)
- 页面边距、装订线、页眉页脚距
- 正文字体（宋体）、字号（小四 12pt）、行距（1.5 倍）
- 一/二/三/四级标题样式与编号
- 三线表（顶线 1.5pt / 栏目线 1pt / 底线 1.5pt）
- 目录插入与样式
- 参考文献悬挂缩进
- ...

## ⚠️ 部分完成 (5)
- **图表题注字体**：已统一为宋体 10.5pt，但**图 6 编号不连续**（图 5 后跳到 图 7），
  已在文档中标黄；建议人工核对。
  - 触发规则：`captions.numbering.continuity`
  - 工具：`tool_format_figure_captions` 已执行，但语义层无法自动决定是补编号还是删段落
- **英文摘要**：识别置信度 0.62，已保留原文未强行格式化
  - 触发规则：`front_matter.en_abstract.detect`

## ❌ 未完成 (3)
- **封面页**：未提供自定义封面 docx，已跳过
  - 操作建议：在配置中提供 `cover.custom_docx`
- **附录 B 图题位置**：图题前未紧邻图片，触发规则 `captions.layout.figure_above`
  - 操作建议：手工调整附录 B 第 3 张图的题注位置
- **页眉「章名引用」**：检测到现有分节结构与正文边界不一致，单独改页眉模式不会
  自动重建分节

## ⏭ 已跳过 (1)
- **目录**：本次为 `mode=targeted`（单独改页码），未触发目录处理
```

**`report.json` 结构**：
```json
{
  "summary": {"total": 41, "done": 32, "partial": 5, "failed": 3, "skipped": 1},
  "items": [
    {
      "rule_id": "captions.numbering.continuity",
      "status": "partial",
      "evidence": "图 6 缺失，5 之后是 7",
      "locator": {"paragraph_index": 142},
      "fix_attempts": [
        {"tool": "tool_format_figure_captions", "ok": true, "message": "..."}
      ],
      "diagnosis": {
        "root_cause": "...",
        "needs_human": true,
        "confidence": 0.71
      }
    }
  ]
}
```

---

## 四、关键数据契约

让所有模块无歧义地协作，三个核心数据结构必须先冻结：

```python
# spec/rule_set.py
@dataclass
class Rule: ...
@dataclass
class RuleSet:
    profile: str
    version: str
    rules: list[Rule]

# evaluators/types.py
@dataclass
class CheckResult: ...
@dataclass
class EvalReport: ...

# diagnoser/types.py
@dataclass
class ToolCall: ...
@dataclass
class Diagnosis: ...

# tools/base.py
@dataclass
class ToolResult: ...
@dataclass
class ToolContext:
    trace: Trace
    snapshot_mgr: SnapshotManager
    config: dict
    runtime: dict                     # 复用现有 cfg["_runtime"]
```

**关键约束**：所有 Tool / Evaluator / Diagnoser 的输入输出都用这套结构，便于回放、单元测试、换模型。

---

## 五、典型执行流程（端到端示例）

以"用户用 SCAU 模板格式化一份草稿"为例：

```
[ingest]
  论文.docx → DocumentModel (含 138 段, 7 节, 3 表, 5 图)
  scau_2024.yaml → RuleSet (含 41 条规则)

[plan v1]   默认计划:
  P1 setup_page_layout
  P2 assign_heading_styles
  P3 setup_multilevel_list
  P4 renumber_headings (skip, scau_2024 启用了 Word 多级列表)
  P5 normalize_heading_spacing
  P6 format_body
  P7 format_figure_captions
  P8 format_table_captions
  P9 format_three_line_tables
  P10 format_references
  P11 setup_page_numbers
  P12 setup_headers (跳过，scau_2024 不要页眉)
  P13 insert_toc
  P14 insert_cover_and_declaration
  P15 word_postprocess (full)

[act]
  逐 Tool 执行，每步前打 snapshot_<n>.docx

[evaluate]   跑 41 条规则
  result: 36 pass, 3 fail, 2 skip
  failures:
    - body.line_spacing             (实际 20pt 固定, 期望 1.5 倍)
    - captions.numbering.continuity (图 6 缺失)
    - toc.entry_count               (目录 14 条, 实际标题 16 条)

[diagnose]   LLM 看 3 条 failure + 上下文
  diagnoses:
    - body.line_spacing:
        root_cause: "原文使用了固定 20pt 行距"
        fix_plan: [tool_format_body{line_spacing: 1.5, scope: "all_body"}]
        confidence: 0.95
        needs_human: false
    - captions.numbering.continuity:
        root_cause: "图 6 段落丢失或被合并"
        fix_plan: []
        confidence: 0.55
        needs_human: true
    - toc.entry_count:
        root_cause: "两个新加的 H2 标题未应用 Heading2 样式"
        fix_plan: [
          tool_assign_heading_styles{force: true},
          tool_insert_toc{regenerate: true},
          tool_word_postprocess{mode: "full"}
        ]
        confidence: 0.88
        needs_human: false

[policies.gate_human_in_loop]
  captions.numbering.continuity 标为 needs_human:
    - auto_apply_diagnosis="confirm" → 暂停，等用户确认
    - auto_apply_diagnosis="no"      → 写入 report.partial，不修

[replan v2]
  追加 fix_plan 中的 ToolCall

[act + evaluate]
  loop 收敛检查

[deliver]
  → 论文_formatted.docx
  → 论文_report.md / json
  → 论文_trace.jsonl
```

---

## 六、目录结构与文件职责

把现有项目作为底层 toolbox，新建 harness 上层：

```
thesis-typeset-main/                  # 现有根目录
├─ thesis_formatter/                  # 现有 — 作为底层算子库（不大改）
│  ├─ formatter.py
│  ├─ page.py
│  ├─ headings.py
│  ├─ headers.py
│  ├─ numbering.py
│  ├─ references.py
│  ├─ toc.py
│  ├─ cover.py
│  ├─ structure.py
│  └─ _common.py
│
├─ thesis_runner.py                   # 现有 — 作为 mode=fast 快通道保留
├─ thesis_format_cli.py               # 现有 CLI
├─ thesis_gui.py                      # 现有 GUI
├─ thesis_config.py                   # 现有配置加载
├─ word_postprocess.py                # 现有 Word COM 后处理
├─ defaults/scau_2024.yaml            # 现有默认模板
│
├─ thesis_agent/                      # 新增 ★ 主要工作在这里
│  ├─ __init__.py
│  │
│  ├─ ingest/
│  │  ├─ document_loader.py           # 复用 thesis_runner 转换链
│  │  ├─ document_model.py            # docx → 内部模型
│  │  └─ template_loader.py           # YAML / NL → RuleSet
│  │
│  ├─ spec/
│  │  ├─ rule_set.py                  # Rule / RuleSet 数据类
│  │  ├─ compiler.py                  # yaml → RuleSet
│  │  ├─ predicates.py                # equals / one_of / regex / range / exists
│  │  └─ profiles/
│  │     ├─ scau_2024.py              # 引用 defaults/scau_2024.yaml
│  │     └─ generic_gb7714.py         # 国标通用 profile
│  │
│  ├─ tools/                          # 全部包装现有 thesis_formatter/*
│  │  ├─ base.py                      # Tool 协议 + ToolResult
│  │  ├─ registry.py                  # 工具注册表
│  │  ├─ page_tools.py
│  │  ├─ heading_tools.py
│  │  ├─ body_tools.py
│  │  ├─ caption_tools.py
│  │  ├─ table_tools.py
│  │  ├─ reference_tools.py
│  │  ├─ header_tools.py
│  │  ├─ page_number_tools.py
│  │  ├─ toc_tools.py
│  │  ├─ cover_tools.py
│  │  └─ word_postprocess_tools.py
│  │
│  ├─ evaluators/
│  │  ├─ runner.py                    # 评测主入口
│  │  ├─ types.py                     # CheckResult / EvalReport
│  │  └─ checks/
│  │     ├─ check_page.py
│  │     ├─ check_fonts.py
│  │     ├─ check_headings.py         # 复用 structure.validate_structure 逻辑
│  │     ├─ check_toc.py
│  │     ├─ check_captions.py         # 复用 _check_caption_numbering
│  │     ├─ check_references.py
│  │     ├─ check_sections.py
│  │     └─ check_front_matter.py
│  │
│  ├─ diagnoser/
│  │  ├─ types.py                     # ToolCall / Diagnosis
│  │  ├─ llm_client.py                # OpenAI/本地 LLM 抽象
│  │  ├─ diagnoser.py
│  │  └─ prompts/
│  │     ├─ system.md
│  │     ├─ diagnose_default.md
│  │     ├─ diagnose_captions.md
│  │     ├─ diagnose_headings.md
│  │     └─ nl_to_spec.md
│  │
│  ├─ orchestrator/
│  │  ├─ planner.py
│  │  ├─ harness.py                   # 主循环
│  │  ├─ snapshot.py                  # docx 快照管理
│  │  └─ policies.py                  # 重试 / 收敛 / 人工介入
│  │
│  ├─ delivery/
│  │  ├─ report.py                    # md + json 报告生成
│  │  ├─ diff_view.py
│  │  └─ trace.py                     # jsonl trace
│  │
│  └─ cli.py                          # 新 CLI:
│                                     # thesis-agent run --input X --profile Y --mode full
│
└─ tests/
   ├─ existing tests (unchanged)
   ├─ unit/
   │  ├─ test_tool_*.py               # 每个 Tool 单测
   │  ├─ test_check_*.py              # 每个 Evaluator 单测
   │  └─ test_compiler.py
   └─ scenarios/
      ├─ fixtures/
      │  ├─ minimal_thesis.docx
      │  ├─ messy_thesis.docx
      │  └─ scau_perfect_thesis.docx
      └─ test_e2e_*.py
```

**关键设计**：`thesis_agent/` 是新增目录，不动现有 `thesis_formatter/*`。所有 Tool 都是对现有函数的薄包装，保证现有 `thesis_runner` 路径完全不受影响。

---

## 七、AI 边界与人在回路

### 7.1 AI 可以做的事

| 场景 | 触发条件 | 输出 |
|---|---|---|
| 评测失败诊断 | `EvalReport.has_failure(must)` | `Diagnosis` 含 `fix_plan` |
| 标题级别歧义判断 | `check_headings` 报"未识别为 Heading 但疑似" | 段落 + 置信度的级别 |
| 自然语言模板抽 Spec | 接入 `.pdf/.md` 模板说明书 | 草稿 YAML，**必须落盘人工审核** |
| 完成度报告语言润色 | 生成 `report.md` 时 | 把 evidence 译成自然语言 |

### 7.2 AI 不能做的事

- 直接输出 docx XML 或 OOXML 节点
- 跳过 Tool 自己写文档
- 决定是否执行高风险操作（"重排前置页"、"删除分节"）
- 编造规则集里没有的规则

### 7.3 人在回路触发点

`policies.human_in_the_loop_at` 默认包含：
- `front_matter`：前置页识别置信度 < 0.7
- `cover`：用户启用了"自动生成封面"且原稿已有疑似封面页
- `ambiguous_headings`：超过 N 个段落标题级别识别置信度 < 0.7
- `destructive_ops`：诊断器输出的修复计划包含删除/重排操作

触发时 Orchestrator 暂停，把当前状态写入 `pending.json`，等用户在 GUI 或 CLI `--resume` 后继续。

---

## 八、与现有代码的衔接（渐进迁移路径）

### 阶段 1：非侵入式接入（≈1 周）
- 新增 `thesis_agent/` 目录，**不动现有任何代码**。
- 实现 `tools/base.py` + 1 个 Tool（`tool_format_body`）+ 1 个 Evaluator（`check_body_line_spacing`）+ 最简 Orchestrator。
- 跑通最小闭环：act → eval → diagnose（mock LLM）→ replan。
- 目标：证明架构可工作。

### 阶段 2：包装现有算子（≈2 周）
- 把 `thesis_formatter/*` 中所有可独立调用的函数，逐个包装成 Tool。
- 把 `structure.validate_structure` 和 `_common._check_caption_numbering` 包装成 Evaluator。
- 编写 `spec/compiler.py`，把 `defaults/scau_2024.yaml` 完整编译成 RuleSet。
- 目标：所有现有能力都可在 harness 模式下复现。

### 阶段 3：接入 LLM 诊断（≈1 周）
- 实现 `diagnoser/llm_client.py`，先支持 OpenAI compatible 接口。
- 写 5~10 个高频 prompt 模板。
- 加 `mode=eval_only / diagnose_only`，让用户先看到评测和诊断，再决定是否执行。

### 阶段 4：交付层与 GUI 对接（≈1 周）
- 实现 `delivery/report.py`，输出 md + json 报告。
- GUI 增加"完成度报告"标签页，渲染 `report.json`。
- CLI 增加 `thesis-agent` 命令。

### 阶段 5：渐进切换（持续）
- 现有 `thesis_runner.run_format` 默认改为调 `harness.run(mode="fast")`，行为不变。
- 用户可显式选 `mode=full` 切到新链路。
- 长期目标：废弃 `thesis_runner.py`，全部走 harness。

---

## 九、最小可行版本（MVP）切分

为了尽快验证整个链路，第一个可用版本只做下列功能：

| 范围 | 是否在 MVP |
|---|---|
| `mode=fast` 沿用现有链路 | ✅ |
| `mode=full`：act + eval + 报告 | ✅（不接 LLM） |
| `mode=eval_only`：只评测 | ✅ |
| 5 个核心 Tool：page / heading / body / toc / postprocess | ✅ |
| 5 个核心 Evaluator：page / fonts / headings / toc / front_matter | ✅ |
| `report.md` + `report.json` | ✅ |
| `trace.jsonl` | ✅ |
| LLM 诊断 | ❌（v0.2） |
| NL → Spec | ❌（v0.3） |
| 人在回路 / GUI 集成 | ❌（v0.3） |
| 全量 Tool 包装 | ❌（v0.2） |

MVP 的成功标准：用 SCAU 默认模板对 `tests/scenarios/fixtures/scau_perfect_thesis.docx` 跑 `mode=full`，输出与 `mode=fast` 一致的 docx，并且 `report.md` 显示 41/41 全部 done。

---

## 十、测试与可观测性策略

### 10.1 测试金字塔
- **单元测试**：每个 Tool / Evaluator 一份 `test_*.py`，输入小 docx fixture，断言精确效果。
- **集成测试**：`tests/scenarios/`，端到端跑完整 harness，断言 `report.json.summary`。
- **回归测试**：保留所有现有 `tests/test_*.py`，确保现有 `thesis_runner` 路径不被破坏。
- **黄金样本对比**：对每个 profile 维护一份"正确答案 docx"，新版本输出和它做段落级 diff。

### 10.2 可观测性
- `trace.jsonl`：每条记录 `{ts, kind, tool, params, result, snapshot_id}`。
- `LOG_LEVEL=DEBUG` 时 LLM prompt + response 也落 trace。
- `snapshots/` 保留每步的 docx，便于 bisect 找出哪步出错。
- `report.json` 自带 `meta.duration_per_step_ms`，性能分析用。

### 10.3 LLM 测试
- 所有 LLM 调用在测试中 mock，断言 prompt 内容和对响应的解析。
- 单独的 `tests/llm/` 跑真实 LLM，标记 `@pytest.mark.llm`，CI 可选触发。

---

## 十一、风险与限制

| 风险 | 缓解 |
|---|---|
| LLM 输出格式不稳定 | 所有 LLM 输出走 JSON Schema 校验，失败重试 ≤2 次，再失败标 `needs_human` |
| LLM 成本失控 | 默认本地优先，`mode=full` 也仅在评测失败才调 LLM；缓存上次的 `(rule_id, evidence_hash) → diagnosis` |
| 复杂版面诊断失败 | 触发 `human_in_the_loop`，**绝不静默修改**，写入 partial |
| 现有 `thesis_runner` 行为被破坏 | `mode=fast` 路径完全保留，CI 跑现有所有 `tests/test_*.py` 不变 |
| 段落 locator 失效 | docx 增删段落后段落索引会变；用 (style_name, text_hash, ordinal) 联合定位，不依赖纯 index |
| 模板自然语言抽错 | NL → Spec 的产出**强制要求人工审核**，不直接进入 RuleSet |
| Word COM 不可用 | 后处理走 `mode=none`，把"未刷新域"作为 partial 写入报告 |

---

## 十二、非目标

本架构**不做**以下事情，避免范围蔓延：

- 不做论文内容改写、查重、润色
- 不做参考文献条目语义校验（只校验格式）
- 不接 PDF 输出（只交付 docx）
- 不做协作编辑 / 在线版
- 不替换 Word 作为最终渲染器
- 不在第一版集成 Latex 输出回路

---

## 十三、后续工作（脱离本文档范围）

- 多 profile 同时维护（清华 / 北大 / 复旦 / 国标通用）
- Web 版前端（替代 tkinter GUI）
- 模板自学习（基于若干样本反推 RuleSet）
- 增量格式化（只对改动段落重跑相关 Tool）
- 多语言论文支持（英文论文 / 双语论文）

---

## 附录 A：现有文件与新模块的映射表

| 现有文件 | 在新架构中的角色 | 新位置 / 调用方 |
|---|---|---|
| `thesis_formatter/formatter.py: apply_format` | 旧"全流程"入口，作为 fast path 保留 | 由 `thesis_agent/orchestrator/harness.py mode=fast` 直接调 |
| `thesis_formatter/page.py` | 算子 | `tools/page_tools.py` 包装 |
| `thesis_formatter/headings.py` | 算子 | `tools/heading_tools.py` 包装 |
| `thesis_formatter/headers.py` | 算子 | `tools/header_tools.py` 包装 |
| `thesis_formatter/numbering.py` | 算子 + 预检 | `tools/caption_tools.py` 包装；预检逻辑 → `evaluators/checks/check_captions.py` |
| `thesis_formatter/structure.py: validate_structure` | 评测 | 直接复用，包装为多个 `check_*.py` |
| `thesis_formatter/_common.py: _check_caption_numbering` | 评测 | 直接复用，包装为 `evaluators/checks/check_captions.py` |
| `thesis_formatter/toc.py` | 算子 | `tools/toc_tools.py` 包装 |
| `thesis_formatter/cover.py` | 算子 | `tools/cover_tools.py` 包装 |
| `thesis_formatter/references.py` | 算子 + 评测 | 拆为 `tools/reference_tools.py` + `evaluators/checks/check_references.py` |
| `thesis_runner.py: run_format` | fast path | 保留；新 `mode=full` 走 harness |
| `word_postprocess.py: postprocess` | 算子 | `tools/word_postprocess_tools.py` 包装，已支持 `mode=full/fields_only/none` |
| `thesis_config.py: resolve_config` | 模板加载 | `ingest/template_loader.py` 复用 |
| `thesis_format_cli.py` | CLI | 现有保留；新增 `thesis_agent/cli.py` |
| `thesis_gui.py` | GUI | 现有保留；后续接 `thesis_agent` 加"完成度报告"标签页 |

## 附录 B：核心工程接口签名速查

```python
# === Spec ===
def compile(yaml_dict: dict) -> RuleSet: ...
def load_profile(name: str) -> RuleSet: ...

# === Tools ===
class Tool(Protocol):
    def run(self, doc: DocumentModel, params: dict, ctx: ToolContext) -> ToolResult: ...

# === Evaluators ===
def evaluate(doc: DocumentModel, rule_set: RuleSet,
             only_rule_ids: Optional[list[str]] = None) -> EvalReport: ...

# === Diagnoser ===
def diagnose(report: EvalReport, doc: DocumentModel,
             llm: LLMClient) -> list[Diagnosis]: ...

# === Orchestrator ===
def run(input_path: str, profile: str, mode: str,
        options: RunOptions) -> DeliveryReport: ...

# === Delivery ===
def build_report(doc: DocumentModel, rule_set: RuleSet,
                 final_report: EvalReport, trace: Trace,
                 snapshots: SnapshotManager) -> DeliveryReport: ...
def write_report_md(delivery: DeliveryReport, path: str) -> None: ...
def write_report_json(delivery: DeliveryReport, path: str) -> None: ...
```
