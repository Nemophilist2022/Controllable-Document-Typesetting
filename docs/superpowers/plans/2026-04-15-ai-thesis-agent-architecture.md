# AI 论文排版 Agent 架构落地计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不影响现有 `thesis_runner` / `thesis_formatter/*` 的前提下，新增 `thesis_agent/` 顶层模块，落地"基于规则评测 + AI 诊断的论文格式自动化交付系统" MVP（v0.1）。MVP 端到端可跑通 happy path 与 sad path。

**Architecture:** 见 `docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-design.md`。简言之：分接入 / 规约 / 工具 / 评测 / 诊断 / 编排 / 交付七层；现有 `thesis_formatter/*` 作为底层算子库被薄包装，不重写。

**Requirements:** 见 `docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-requirements.md`，MVP 范围在第 4 节，默认值在第 6 节冻结。

**Tech Stack:** Python 3.10+，新增依赖以 `python-docx` / `pyyaml` / `pywin32` / `ttkbootstrap` 为主；LLM 客户端在 v0.2 引入；测试用 `unittest`。

---

## 全局执行约束

- **TDD**：每个 Task 都先写失败测试，再实现，再验证。
- **零回归**：所有现有 `tests/test_*.py` 必须保持绿；`mode=fast` 走原 `thesis_runner.run_format`，不修改其行为。
- **包装不重写**：现有 `thesis_formatter/*` 函数签名不变，新逻辑通过包装层加。
- **运行命令**：所有验证用 `py -3.10 -m unittest discover -s tests -p "<pattern>" -v`。
- **提交规范**：每个 Task 末尾打一个 commit；commit message 用 `feat(agent): <短句>` 或 `test(agent): <短句>`。
- **目录约束**：新代码放在 `thesis_agent/`，新测试放在 `tests/agent/`；fixtures 放在 `tests/scenarios/fixtures/`。
- **MVP 范围**：实现 R1 / R2 / R3 / R4 / R6 / R7 / R8（部分）/ R10 / R11（部分）/ R12（部分）/ R13；R5（LLM）用 mock，R9（人在回路）暂跳。

---

## 任务依赖图

```
T1 (骨架)──┐
T2 (类型) ─┼─→ T3 (ingest) ──┐
           ├─→ T4 (spec) ────┤
           │                 ├─→ T6 (4 Tool) ──────┐
           ├─→ T5 (tool 基) ─┘                     │
           │                                       │
           ├─→ T7 (eval 基) ──→ T8 (4 Check) ─────┤
           │                                       │
           ├─→ T10 (mock diagnoser) ───────────────┤
           │                                       │
           └─→ T11 (delivery) ─────────────────────┤
                                                   ▼
                              T9 (orchestrator) ──→ T12 (CLI/兼容) ──→ T13 (E2E) ──→ T14 (docs)
```

允许并行：T1 与 T2 / T3 与 T4 / T5 与 T7 / T6 与 T8 / T10 与 T11。

---

## File Map（创建 / 修改 / 测试）

### 创建
- `thesis_agent/__init__.py` 及全部子目录骨架（T1）
- `thesis_agent/ingest/types.py` `document_loader.py` `document_model.py` `template_loader.py`（T2 / T3）
- `thesis_agent/spec/rule_set.py` `predicates.py` `compiler.py` `profiles/scau_2024.py`（T2 / T4）
- `thesis_agent/tools/base.py` `registry.py` `body_tools.py` `heading_tools.py` `toc_tools.py` `word_postprocess_tools.py`（T2 / T5 / T6）
- `thesis_agent/evaluators/types.py` `runner.py` `checks/check_fonts.py` `check_body.py` `check_headings.py` `check_toc.py`（T2 / T7 / T8）
- `thesis_agent/diagnoser/types.py` `diagnoser.py` `llm_client.py`（T2 / T10）
- `thesis_agent/orchestrator/snapshot.py` `planner.py` `harness.py` `policies.py`（T9）
- `thesis_agent/delivery/trace.py` `report.py`（T11）
- `thesis_agent/cli.py`（T12）
- `tools/compare_docx.py`（T1，根目录的实用工具，对应 R10.2）
- `tests/scenarios/fixtures/scau_perfect_thesis.docx` `scau_messy_thesis.docx`（T13）
- `tests/agent/`（每个 Task 都新增对应测试文件）

### 修改
- `thesis_runner.py`（T12，确保 `run_format` 默认行为不变 + 可选转发到 harness fast path）
- `README.md`（T14，新增"thesis-agent 命令行"章节）

---

## Task 1: 项目骨架与 docx 语义比较工具

**Files:**
- Create: `thesis_agent/__init__.py` + 全部子目录 `__init__.py`
- Create: `tools/compare_docx.py`
- Create: `tests/agent/__init__.py` + `tests/agent/test_skeleton.py`
- Create: `tests/test_compare_docx.py`

**Why first:** 后续所有 Task 的 import 都依赖目录骨架；`compare_docx` 是 R10.2 的兜底工具，端到端验收用得到。

- [ ] **Step 1: 写骨架自检测试**

新建 `tests/agent/test_skeleton.py`，断言所有目标子模块可导入。

```python
import unittest

class TestThesisAgentSkeleton(unittest.TestCase):
    def test_top_level_package_importable(self):
        import thesis_agent  # noqa

    def test_all_subpackages_importable(self):
        for name in ["ingest", "spec", "tools", "evaluators",
                     "diagnoser", "orchestrator", "delivery"]:
            __import__(f"thesis_agent.{name}")
```

- [ ] **Step 2: 写 compare_docx 失败测试**

新建 `tests/test_compare_docx.py`，覆盖 R10.2 三类语义维度。

```python
def test_compare_docx_segment_level_equal(self):
    # 同一份 docx 复制两份，segment_equal 应返回 True
    ...

def test_compare_docx_detects_paragraph_text_diff(self):
    # 改一段文本，segment_equal=False，diff 列出该段
    ...

def test_compare_docx_ignores_zip_metadata(self):
    # 重新打包 docx 让 ZIP 时间戳变化，但内容一致 → 仍判等
    ...
```

- [ ] **Step 3: 跑测试，确认失败**

```
py -3.10 -m unittest discover -s tests -p "test_skeleton.py" -v
py -3.10 -m unittest discover -s tests -p "test_compare_docx.py" -v
```

预期：FAIL（`thesis_agent` 不存在 / `compare_docx` 不存在）。

- [ ] **Step 4: 创建目录骨架**

按 File Map 创建所有 `__init__.py`，每个写一个简短的模块 docstring。

- [ ] **Step 5: 实现 compare_docx**

`tools/compare_docx.py` 提供：
- `segment_equal(path_a, path_b) -> bool`：比对所有段落 `(style_id, text, run.formatting)`、节属性、样式定义
- `segment_diff(path_a, path_b) -> list[Diff]`：返回结构化差异，每条含 `kind` / `locator` / `actual` / `expected`

实现要点：
- 不参与比较：docx ZIP 时间戳、`docPr.id`、`rsid*`、`themeFontLang` 等随机/构建时元数据
- 字段比较顺序固定，避免输出抖动

- [ ] **Step 6: 跑测试，确认通过**

```
py -3.10 -m unittest discover -s tests -p "test_skeleton.py" -v
py -3.10 -m unittest discover -s tests -p "test_compare_docx.py" -v
```

- [ ] **Step 7: 提交**

```
git add thesis_agent/ tools/compare_docx.py tests/agent/__init__.py tests/agent/test_skeleton.py tests/test_compare_docx.py
git commit -m "feat(agent): bootstrap thesis_agent skeleton and add docx semantic comparator"
```

---

## Task 2: 冻结数据契约（types 模块集合）

**Files:**
- Create: `thesis_agent/ingest/types.py`
- Create: `thesis_agent/spec/rule_set.py`
- Create: `thesis_agent/tools/base.py`
- Create: `thesis_agent/evaluators/types.py`
- Create: `thesis_agent/diagnoser/types.py`
- Create: `tests/agent/test_data_contracts.py`

**Why next:** 设计文档第 4 节 "关键数据契约"明确说"先冻结再实现"。所有上层模块都引用这些类型。

- [ ] **Step 1: 写契约形状测试**

```python
def test_rule_severity_must_be_in_enum(self):
    with self.assertRaises(ValueError):
        Rule(id="x", scope="paragraph", locator={}, predicate="equals",
             expected=1, severity="critical", fix_tool=None,
             fix_params_template={})

def test_check_result_status_enum(self):
    self.assertEqual(set(CheckStatus), {"pass","fail","skip","error"})

def test_diagnosis_confidence_clamped_to_unit_interval(self):
    d = Diagnosis(rule_id="x", root_cause="", fix_plan=[],
                  confidence=1.5, needs_human=False, rationale="")
    self.assertEqual(d.confidence, 1.0)

def test_tool_result_default_ok_false_means_no_change_lists(self):
    r = ToolResult(ok=False, message="boom")
    self.assertEqual(r.changed_paragraphs, [])
    self.assertEqual(r.changed_styles, [])
    self.assertEqual(r.changed_sections, [])
```

- [ ] **Step 2: 跑测试，确认失败**

```
py -3.10 -m unittest discover -s tests -p "test_data_contracts.py" -v
```

- [ ] **Step 3: 实现 `spec/rule_set.py`**

按 R1.1 / R1.6：
```python
@dataclass(frozen=True)
class Rule:
    id: str
    scope: Literal["doc","section","paragraph","run","table","style"]
    locator: dict
    predicate: str
    expected: Any
    severity: Literal["must","should","info"]
    fix_tool: Optional[str] = None
    fix_params_template: dict = field(default_factory=dict)
    def __post_init__(self):
        if self.severity not in ("must","should","info"):
            raise ValueError(f"invalid severity: {self.severity}")

@dataclass
class RuleSet:
    profile: str
    version: str
    rules: list[Rule]
    metadata: dict = field(default_factory=dict)
```

- [ ] **Step 4: 实现 `evaluators/types.py`**

按 R4.3 / R4.6 / R4.7：`CheckStatus = Literal["pass","fail","skip","error"]`，`CheckResult` 与 `EvalReport` 数据类，`EvalReport.summary` 含 `total / pass / fail / skip / error` 五字段。

- [ ] **Step 5: 实现 `diagnoser/types.py`**

按 R5.5：`Diagnosis.confidence` 在 `__post_init__` 夹紧到 `[0.0, 1.0]`；`ToolCall` 数据类。

- [ ] **Step 6: 实现 `tools/base.py`**

按 R3.1 / R3.2：`Tool` 协议（含 5 个静态属性 + `run`）、`ToolResult`、`ToolContext`。`ToolResult` 的 `changed_*` 字段 default_factory=list。

- [ ] **Step 7: 实现 `ingest/types.py`**

按 R2.2 / m1：`ErrorInfo(code: str, message: str)`、`LoadResult(ok: bool, document_path: Optional[str], error: Optional[ErrorInfo])`。

- [ ] **Step 8: 跑测试，确认通过**

```
py -3.10 -m unittest discover -s tests -p "test_data_contracts.py" -v
```

- [ ] **Step 9: 提交**

```
git add thesis_agent/ingest/types.py thesis_agent/spec/rule_set.py thesis_agent/tools/base.py thesis_agent/evaluators/types.py thesis_agent/diagnoser/types.py tests/agent/test_data_contracts.py
git commit -m "feat(agent): freeze core data contracts (Rule/CheckResult/Diagnosis/ToolResult)"
```

---

## Task 3: 接入层（DocumentModel + Loader + Template Loader）

**Files:**
- Create: `thesis_agent/ingest/document_model.py`
- Create: `thesis_agent/ingest/document_loader.py`
- Create: `thesis_agent/ingest/template_loader.py`
- Create: `tests/agent/test_document_model.py`
- Create: `tests/agent/test_document_loader.py`
- Create: `tests/agent/test_template_loader.py`

- [ ] **Step 1: 写 DocumentModel 读 / 受控写测试（R2.3 / R2.4）**

```python
def test_paragraphs_are_readable_immutable_view(self):
    dm = DocumentModel.from_path(fixture("minimal.docx"))
    paragraphs = dm.paragraphs()  # 返回 tuple 或 frozen list
    with self.assertRaises((TypeError, AttributeError)):
        paragraphs[0].text = "mutated"

def test_set_paragraph_text_tracks_change(self):
    dm = DocumentModel.from_path(fixture("minimal.docx"))
    with dm.write() as w:
        w.set_paragraph_text(0, "新文本")
    self.assertIn(0, dm.last_changes.paragraphs)

def test_save_writes_to_path(self):
    dm = DocumentModel.from_path(fixture("minimal.docx"))
    with dm.write() as w:
        w.set_paragraph_text(0, "新")
    out = tmp / "out.docx"
    dm.save(str(out))
    self.assertTrue(out.exists())
```

- [ ] **Step 2: 写 document_loader 测试（R2.1 / R2.2）**

```python
def test_load_docx_passthrough(self): ...
def test_load_doc_without_word_returns_load_result_error(self):
    # 在没有 Word COM 的环境里，必须返回 LoadResult(ok=False, error.code="word_com_unavailable")
    # 不抛 WindowsError
    ...
def test_load_unsupported_extension_returns_error(self): ...
```

- [ ] **Step 3: 写 template_loader 测试（R2.5 / R2.6 / R1.2 / R1.3）**

```python
def test_from_yaml_uses_existing_resolve_config(self):
    # 直接复用 thesis_config.resolve_config，不重复实现
    ...
def test_from_yaml_with_non_dict_root_raises(self):
    with self.assertRaises(InvalidTemplateError):
        from_yaml(broken_yaml_path)

def test_from_natural_language_writes_yaml_and_marks_pending(self):
    result = from_natural_language(spec_text)
    self.assertTrue(result.pending_human_review)
    self.assertTrue(Path(result.yaml_path).exists())
```

- [ ] **Step 4: 跑全部 ingest 测试，确认失败**

```
py -3.10 -m unittest discover -s tests/agent -p "test_document_*.py" -v
py -3.10 -m unittest discover -s tests/agent -p "test_template_loader.py" -v
```

- [ ] **Step 5: 实现 DocumentModel**

```python
class DocumentModel:
    @classmethod
    def from_path(cls, path: str) -> "DocumentModel": ...
    def paragraphs(self) -> tuple[ParagraphView, ...]: ...      # 只读
    def sections(self) -> tuple[SectionView, ...]: ...
    def styles(self) -> StylesView: ...
    def tables(self) -> tuple[TableView, ...]: ...
    @contextmanager
    def write(self) -> Iterator["DocumentWriter"]: ...          # 受控写
    @property
    def last_changes(self) -> ChangeSet: ...
    def save(self, path: str) -> None: ...
```

- 内部允许直接用 `python-docx`（这是唯一允许 import 的位置）
- 写操作通过 `DocumentWriter`，每次写自动累加到 `last_changes`，进而被 Tool 用于填 `ToolResult.changed_*`

- [ ] **Step 6: 实现 document_loader**

复用 `thesis_runner.find_pandoc` / `convert_doc_to_docx` / `pandoc` 调用链。环境检测失败必须返回 `LoadResult(ok=False, ...)`，绝不抛非业务异常。

- [ ] **Step 7: 实现 template_loader**

`from_yaml` 直接走 `thesis_config.resolve_config` 拿到 dict（保持 R12.5 优先级），返回 dict 等待 `compiler.compile()`；`from_natural_language` 在 v0.1 阶段返回 stub（写 placeholder yaml 到磁盘 + `pending_human_review=True`），实际 LLM 调用在 v0.2 接入。

- [ ] **Step 8: 跑测试通过**

```
py -3.10 -m unittest discover -s tests/agent -v
```

- [ ] **Step 9: 提交**

```
git add thesis_agent/ingest/ tests/agent/test_document_model.py tests/agent/test_document_loader.py tests/agent/test_template_loader.py
git commit -m "feat(agent): add DocumentModel with read/write APIs and reuse existing loader chain"
```

---

## Task 4: 规约层（Predicates + Compiler + Profile）

**Files:**
- Create: `thesis_agent/spec/predicates.py`
- Create: `thesis_agent/spec/compiler.py`
- Create: `thesis_agent/spec/profiles/__init__.py`
- Create: `thesis_agent/spec/profiles/scau_2024.py`
- Create: `tests/agent/test_predicates.py`
- Create: `tests/agent/test_compiler.py`
- Create: `tests/agent/test_profiles.py`

- [ ] **Step 1: 写 predicates 测试**

```python
def test_equals_predicate(self): ...
def test_one_of_predicate(self): ...
def test_regex_predicate(self): ...
def test_range_predicate_inclusive(self): ...
def test_exists_predicate(self): ...
def test_unknown_predicate_raises(self): ...
```

- [ ] **Step 2: 写 compiler 测试（R1.1~R1.7）**

```python
def test_compiler_emits_mvp_dimensions(self):
    rs = compile(load_yaml("defaults/scau_2024.yaml"))
    rule_ids = {r.id for r in rs.rules}
    self.assertIn("body.font.east_asia", rule_ids)
    self.assertIn("body.line_spacing", rule_ids)
    self.assertIn("heading.h1.style_present", rule_ids)
    self.assertIn("toc.entry_count", rule_ids)

def test_compiler_collects_unknown_keys_with_dotted_path(self):
    rs = compile({"body": {"unknown_subkey": 1}, "_unknown_top": "x"})
    self.assertIn("body.unknown_subkey", rs.metadata.unknown_keys)
    self.assertIn("_unknown_top", rs.metadata.unknown_keys)

def test_compiler_rejects_invalid_severity(self): ...

def test_compiler_raises_on_duplicate_rule_id_after_merge(self):
    with self.assertRaises(DuplicateRuleError):
        compile(merge_two_yamls_with_same_rule_id())
```

- [ ] **Step 3: 写 profile 测试（R1.7 / R10.3）**

```python
def test_load_profile_scau_2024_equivalent_to_yaml_compile(self):
    rs_a = load_profile("scau_2024")
    rs_b = compile(load_yaml("defaults/scau_2024.yaml"))
    self.assertEqual([r.id for r in rs_a.rules], [r.id for r in rs_b.rules])
```

- [ ] **Step 4: 跑测试，确认失败**

- [ ] **Step 5: 实现 predicates.py**

注册表式：`PREDICATES = {"equals": equals_pred, "one_of": ..., ...}`，`evaluate(predicate_name, actual, expected) -> bool`。

- [ ] **Step 6: 实现 compiler.py**

YAML dict → list[Rule]，**MVP 至少产出 4 个核心规则**（满足 MVP 第 1 项）：
- `body.font.east_asia` / `body.font.size` → equals
- `body.line_spacing` → equals
- `heading.h1.style_present` → exists
- `toc.entry_count` → equals

剩余维度（R1.3 完整列表）作为已识别但暂不展开的 placeholder rule（`metadata.deferred=True`），不影响 MVP，未来扩展直接在 compiler 加 mapping。

递归收集 unknown keys 到 `RuleSet.metadata.unknown_keys: list[str]`（dotted path）。

- [ ] **Step 7: 实现 profiles/scau_2024.py**

```python
def load() -> RuleSet:
    yaml_path = Path(__file__).parents[2] / "defaults" / "scau_2024.yaml"
    return compile(load_yaml(yaml_path))
```

并提供顶层 `load_profile(name: str) -> RuleSet` API。

- [ ] **Step 8: 跑测试通过**

- [ ] **Step 9: 提交**

```
git add thesis_agent/spec/ tests/agent/test_predicates.py tests/agent/test_compiler.py tests/agent/test_profiles.py
git commit -m "feat(agent): compile YAML templates into RuleSet with 4 MVP rules"
```

---


## Task 5: 工具层基础设施（Registry + 自动发现）

**Files:**
- Create: `thesis_agent/tools/registry.py`
- Create: `tests/agent/test_tool_registry.py`

- [ ] **Step 1: 写 registry 测试（R3.6 / R12.2 / R12.7）**

```python
def test_register_and_get(self):
    registry.clear()
    registry.register(FakeTool())
    self.assertIs(registry.get("fake_tool"), registry._tools["fake_tool"])

def test_get_unknown_raises(self):
    registry.clear()
    with self.assertRaises(UnknownToolError):
        registry.get("nope")

def test_all_tools_returns_registered(self):
    registry.clear()
    registry.register(FakeTool())
    self.assertEqual([t.name for t in registry.all_tools()], ["fake_tool"])

def test_autoload_scans_tools_dir(self):
    # 在 thesis_agent/tools/ 下放一个 dummy 模块，autoload 后能找到它
    registry.autoload()
    self.assertTrue(any(t.name == "tool_format_body" for t in registry.all_tools()))
```

- [ ] **Step 2: 跑测试，确认失败**

- [ ] **Step 3: 实现 registry.py**

```python
_tools: dict[str, Tool] = {}

def register(tool: Tool) -> None: ...
def get(name: str) -> Tool: ...
def all_tools() -> list[Tool]: ...
def clear() -> None: ...
def autoload() -> None:
    """扫描 thesis_agent/tools/*.py，凡 module.TOOLS 列表里的 Tool 实例都注册"""
    ...
```

`autoload` 失败的模块写 `WARN` 日志但不阻塞（R12.7）。

- [ ] **Step 4: 跑测试通过**

- [ ] **Step 5: 提交**

```
git add thesis_agent/tools/registry.py tests/agent/test_tool_registry.py
git commit -m "feat(agent): add tool registry with auto-discovery"
```

---

## Task 6: MVP 四个核心 Tool（包装现有算子）

**Files:**
- Create: `thesis_agent/tools/body_tools.py`
- Create: `thesis_agent/tools/heading_tools.py`
- Create: `thesis_agent/tools/toc_tools.py`
- Create: `thesis_agent/tools/word_postprocess_tools.py`
- Create: `tests/agent/test_tool_format_body.py`
- Create: `tests/agent/test_tool_assign_heading_styles.py`
- Create: `tests/agent/test_tool_insert_toc.py`
- Create: `tests/agent/test_tool_word_postprocess.py`

**Why:** 满足 MVP R3.3 子集（`tool_format_body` / `tool_assign_heading_styles` / `tool_insert_toc` / `tool_word_postprocess`）。所有 Tool 都是对现有 `thesis_formatter/*` 函数的薄包装。

- [ ] **Step 1: 写 4 个 Tool 的契约测试（R3.2 / R3.5）**

每个 Tool 都覆盖：
- 静态属性 `name` / `description` / `input_schema` / `requires` / `idempotent` 存在且类型正确
- `run` 不抛未捕获异常；`run` 失败返回 `ToolResult(ok=False)` 不是 raise
- 成功后 `changed_*` 至少有一个非空（除 `tool_word_postprocess` 外）
- 可重复调用且第二次 `changed_*` 为空集合（幂等）
- 调用前 `ctx.snapshot_mgr.take()` 被调用过一次（用 mock SnapshotMgr 验证）

```python
def test_tool_format_body_changes_normal_style_runs(self):
    dm = DocumentModel.from_path(fixture("body_wrong_font.docx"))
    ctx = ToolContext(snapshot_mgr=FakeSnapshotMgr(), trace=Trace(), config={}, runtime={})
    result = body_tools.tool_format_body.run(dm, {"east_asia_font":"宋体","line_spacing":1.5}, ctx)
    self.assertTrue(result.ok)
    self.assertIn("Normal", result.changed_styles)
    self.assertEqual(ctx.snapshot_mgr.take_calls, 1)

def test_tool_format_body_idempotent(self):
    # 同样参数二次调用 changed_* 应为空
    ...

def test_tool_format_body_swallows_exception(self):
    # 用一个会 raise 的 mock DocumentWriter，断言返回 ok=False 而非异常上抛
    ...
```

类似地为另外 3 个 Tool 写。

- [ ] **Step 2: 跑测试，确认失败**

- [ ] **Step 3: 实现 `tool_format_body`（包装 `formatter.py` 内 body 段处理）**

```python
class FormatBody:
    name = "tool_format_body"
    description = "Apply body font / size / line spacing to all Normal-style paragraphs"
    input_schema = {
        "type": "object",
        "properties": {
            "east_asia_font": {"type": "string"},
            "size": {"type": "number"},
            "line_spacing": {"type": "number"},
            "first_line_indent": {"type": "number"},
            "align": {"type": "string"},
        },
        "additionalProperties": False,
    }
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params, ctx):
        token = ctx.snapshot_mgr.take(doc)
        try:
            with doc.write() as w:
                # 调用现有 thesis_formatter._common.set_style_font / apply_line_spacing 等
                ...
            return ToolResult(ok=True, changed_styles=["Normal"], rollback_token=token, ...)
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc), rollback_token=token)

TOOLS = [FormatBody()]
```

- [ ] **Step 4: 实现 `tool_assign_heading_styles`**

直接复用 `thesis_formatter.headings.auto_assign_heading_styles`，把返回的 `changes` 列表展开成 `changed_paragraphs`。

- [ ] **Step 5: 实现 `tool_insert_toc`**

复用 `thesis_formatter.toc.insert_toc` + `ensure_toc_styles`。`requires=["tool_assign_heading_styles"]`。

- [ ] **Step 6: 实现 `tool_word_postprocess`**

包装 `word_postprocess.postprocess`，参数 `{mode: "full"|"fields_only"|"none"}`。在非 Windows 平台或没有 Word COM 时直接返回 `ToolResult(ok=True, message="postprocess skipped (env)")`，由调用方决定是否计为 partial（R7.4）。

- [ ] **Step 7: 跑全部 4 个 Tool 测试通过**

- [ ] **Step 8: 提交**

```
git add thesis_agent/tools/body_tools.py thesis_agent/tools/heading_tools.py thesis_agent/tools/toc_tools.py thesis_agent/tools/word_postprocess_tools.py tests/agent/test_tool_*.py
git commit -m "feat(agent): wrap 4 MVP tools (body/heading/toc/postprocess) with Tool protocol"
```

---

## Task 7: 评测层基础设施（Runner）

**Files:**
- Create: `thesis_agent/evaluators/runner.py`
- Create: `tests/agent/test_eval_runner.py`

- [ ] **Step 1: 写 runner 测试（R4.1 / R4.2 / R4.5 / R4.6 / R4.7 / R4.8）**

```python
def test_runner_returns_eval_report_with_all_summary_fields(self):
    rs = RuleSet(profile="t", version="1", rules=[fake_rule_pass()])
    report = evaluate(fake_doc(), rs)
    for k in ["total","pass","fail","skip","error"]:
        self.assertIn(k, report.summary)

def test_runner_only_runs_subset_when_only_rule_ids_given(self):
    rs = RuleSet(profile="t", version="1",
                 rules=[fake_rule_pass("a"), fake_rule_pass("b")])
    report = evaluate(fake_doc(), rs, only_rule_ids=["a"])
    self.assertEqual({r.rule_id for r in report.results}, {"a"})

def test_runner_error_status_when_locator_missing(self):
    rs = RuleSet(profile="t", version="1", rules=[rule_with_bad_locator()])
    report = evaluate(fake_doc(), rs)
    self.assertEqual(report.results[0].status, "error")
    self.assertIn("locator", report.results[0].evidence)

def test_runner_no_llm_imports(self):
    # 静态扫描：evaluators 目录下不得 import openai / anthropic / requests 到外网
    ...

def test_runner_perf_under_1s_for_100_paragraph_doc(self):
    # 标记 @perf；100 段 docx 跑 41 条 rule 必须 ≤1s
    ...
```

- [ ] **Step 2: 跑测试，确认失败**

- [ ] **Step 3: 实现 evaluators/runner.py**

```python
def evaluate(doc, rule_set, only_rule_ids=None) -> EvalReport:
    results = []
    for rule in rule_set.rules:
        if only_rule_ids and rule.id not in only_rule_ids:
            continue
        try:
            results.append(_run_one_check(doc, rule))
        except LocatorError as exc:
            results.append(CheckResult(rule.id, status="error", evidence=str(exc), ...))
        except Exception as exc:
            # 评测器自身异常也归为 error
            results.append(CheckResult(rule.id, status="error", evidence=f"check error: {exc}", ...))
    return EvalReport(profile=rule_set.profile, results=results, summary=_summarize(results))

def _run_one_check(doc, rule) -> CheckResult:
    # 1. 用 locator 找到目标
    # 2. 用 predicates.evaluate(rule.predicate, actual, rule.expected) 判定
    # 3. 包装为 CheckResult
    ...
```

- [ ] **Step 4: 加 lint 守护（R4.2）**

新增 `tests/agent/test_evaluators_no_llm_imports.py`：扫描 `thesis_agent/evaluators/**/*.py`，断言不出现 `import openai` / `import anthropic` / `from requests` 等。

- [ ] **Step 5: 跑测试通过**

- [ ] **Step 6: 提交**

```
git add thesis_agent/evaluators/runner.py tests/agent/test_eval_runner.py tests/agent/test_evaluators_no_llm_imports.py
git commit -m "feat(agent): add evaluator runner with rule-id filter and error status handling"
```

---

## Task 8: MVP 四个核心 Check

**Files:**
- Create: `thesis_agent/evaluators/checks/__init__.py`
- Create: `thesis_agent/evaluators/checks/check_body.py`
- Create: `thesis_agent/evaluators/checks/check_fonts.py`
- Create: `thesis_agent/evaluators/checks/check_headings.py`
- Create: `thesis_agent/evaluators/checks/check_toc.py`
- Create: `tests/agent/test_check_body.py`
- Create: `tests/agent/test_check_headings.py`
- Create: `tests/agent/test_check_toc.py`

**Why:** 满足 MVP 验收的"4 个维度"（正文字体字号、行距、一级标题样式、目录条目数）。

- [ ] **Step 1: 写 check 单测**

每个 check 至少覆盖：
- pass 情况
- fail 情况（含 evidence 文本不超过 80 字符且包含期望/实际值，对应 C5）
- skip 情况
- error 情况（locator 找不到目标）

```python
def test_check_body_line_spacing_pass(self):
    rule = Rule(id="body.line_spacing", scope="style",
                locator={"style_name":"Normal"}, predicate="equals",
                expected=1.5, severity="must")
    doc = fake_doc_with_normal_line_spacing(1.5)
    result = check_body.run(doc, rule)
    self.assertEqual(result.status, "pass")

def test_check_body_line_spacing_fail_evidence_truncated(self):
    rule = Rule(id="body.line_spacing", ..., expected=1.5)
    doc = fake_doc_with_normal_line_spacing(20.0)  # 固定 20pt
    result = check_body.run(doc, rule)
    self.assertEqual(result.status, "fail")
    self.assertLessEqual(len(result.evidence), 80)
    self.assertIn("20", result.evidence)
```

- [ ] **Step 2: 跑测试，确认失败**

- [ ] **Step 3: 实现 4 个 check**

每个 check 是一个 callable：`def run(doc: DocumentModel, rule: Rule) -> CheckResult`。逻辑约 30 行以内：
- `check_body`：处理 `body.line_spacing` / `body.first_line_indent` 等
- `check_fonts`：处理 `body.font.east_asia` / `body.font.size`
- `check_headings`：处理 `heading.h1.style_present` 等（**复用 `thesis_formatter.structure.validate_structure` 的局部逻辑** — R4.4）
- `check_toc`：处理 `toc.entry_count`（数 toc 字段 vs 数 heading 段）

注册到 evaluators/runner.py 的调度表（R12.1）。

- [ ] **Step 4: 加 evidence 长度守护**

在 `evaluators/types.py` 的 `CheckResult.__post_init__` 加：若 evidence > 80 字符，截断并加 `…`，原文 hash 写入 `metadata.text_hash`。

- [ ] **Step 5: 跑测试通过**

- [ ] **Step 6: 提交**

```
git add thesis_agent/evaluators/checks/ tests/agent/test_check_*.py
git commit -m "feat(agent): implement 4 MVP checks (body/fonts/headings/toc)"
```

---

## Task 9: 编排层（Snapshot + Planner + Harness + Policies）

**Files:**
- Create: `thesis_agent/orchestrator/snapshot.py`
- Create: `thesis_agent/orchestrator/policies.py`
- Create: `thesis_agent/orchestrator/planner.py`
- Create: `thesis_agent/orchestrator/harness.py`
- Create: `tests/agent/test_snapshot.py`
- Create: `tests/agent/test_policies.py`
- Create: `tests/agent/test_planner.py`
- Create: `tests/agent/test_harness_loop.py`

**Why:** 这是 harness 的"心脏"，把前面所有层串起来。

- [ ] **Step 1: 写 snapshot 测试（R6.4 / R11.4 / R11.5）**

```python
def test_take_creates_pre_snapshot_file(self):
    sm = SnapshotManager(work_dir=tmp, capacity=10)
    token = sm.take(dm, step=0, tool_name="tool_format_body")
    self.assertTrue((tmp / "snapshots" / "step_0_tool_format_body_pre.docx").exists())

def test_rollback_last_restores_state(self):
    sm = SnapshotManager(...)
    sm.take(dm, ...)
    dm.write_something()
    sm.rollback_last(dm)
    self.assertEqual(dm.paragraphs()[0].text, original_text)

def test_lru_eviction_after_capacity(self):
    sm = SnapshotManager(work_dir=tmp, capacity=2)
    for i in range(5):
        sm.take(dm, step=i, tool_name=f"t{i}")
    self.assertEqual(len(list((tmp / "snapshots").iterdir())), 2)

def test_step_level_rollback_only(self):
    # R6.4: 仅回滚失败 step 自己的 snapshot，前面成功 step 的副作用保留
    ...
```

- [ ] **Step 2: 写 policies 测试（R6.3 / R6.9 / R9.1 等）**

```python
def test_should_exit_when_must_severity_all_pass(self): ...
def test_should_exit_when_max_iterations_reached(self): ...
def test_should_exit_when_plans_equivalent(self):
    # 两个 plan 的 tool 序列与 params canonical_json 完全一致 → 等价
    ...
def test_human_in_loop_triggered_for_destructive_ops(self): ...
def test_global_run_timeout_writes_partial_report(self): ...
```

- [ ] **Step 3: 写 planner 测试**

```python
def test_default_plan_for_full_mode(self):
    rs = load_profile("scau_2024")
    plan = planner.default_plan(rs, mode="full")
    names = [s.tool for s in plan]
    self.assertEqual(names[:2], ["tool_assign_heading_styles", "tool_format_body"])

def test_replan_appends_diagnosis_fix_plan(self):
    diagnoses = [Diagnosis(rule_id="body.line_spacing", ...,
                           fix_plan=[ToolCall("tool_format_body", {"line_spacing":1.5})])]
    new_plan = planner.replan(diagnoses, prev_plan=[])
    self.assertEqual(new_plan[0].tool, "tool_format_body")

def test_replan_returns_equivalent_plan_to_signal_convergence(self):
    # 当所有 diagnoses 都 needs_human=True 时，新计划与上一轮等价
    ...
```

- [ ] **Step 4: 写 harness 主循环测试（R6.1 ~ R6.10）**

```python
def test_full_mode_runs_plan_act_eval_then_exits_on_pass(self):
    delivery = harness.run(input_path=fixture("scau_perfect_thesis.docx"),
                           profile="scau_2024", mode="full",
                           options=RunOptions(max_iterations=3))
    self.assertEqual(delivery.summary["failed"], 0)
    self.assertGreaterEqual(delivery.summary["done"], 4)

def test_fast_mode_delegates_to_thesis_runner(self):
    with mock.patch("thesis_runner.run_format", return_value=True) as m:
        harness.run(input_path=p, profile="scau_2024", mode="fast", options=...)
    m.assert_called_once()

def test_dry_run_writes_report_no_docx(self):
    delivery = harness.run(..., mode="dry_run", ...)
    self.assertFalse(Path(delivery.docx_path or "x").exists()) if delivery.docx_path is None else self.assertIsNone(delivery.docx_path)
    self.assertTrue(Path(delivery.report_md_path).exists())

def test_eval_only_does_not_modify_input_docx(self):
    in_bytes = Path(input_path).read_bytes()
    harness.run(input_path=input_path, mode="eval_only", ...)
    self.assertEqual(in_bytes, Path(input_path).read_bytes())   # R13.1

def test_unbound_fix_tool_raises(self):
    # RuleSet 里有 fix_tool="tool_unknown" 但 registry 没注册
    with self.assertRaises(UnboundFixToolError):
        harness.run(...)

def test_overwrite_input_path_raises(self):
    with self.assertRaises(OverwriteInputError):
        harness.run(input_path=p, output_path=p, ...)   # R13.1

def test_step_rollback_on_tool_failure_keeps_prior_changes(self): ...
```

- [ ] **Step 5: 跑全部 orchestrator 测试，确认失败**

- [ ] **Step 6: 实现 SnapshotManager**

文件命名规则按 R11.4：`step_<n>_<tool_name>_pre.docx`。LRU 容量 D6=10。`rollback_last` 只回滚最后一个未 commit 的 step。

- [ ] **Step 7: 实现 policies.py**

冻结值：D3=600s / D4=0.7 / D5=3 / D6=10 / D7=enabled。`should_exit(report, iter_count, prev_plan, new_plan, deadline)` 返回退出原因枚举。

- [ ] **Step 8: 实现 planner.py**

`default_plan(rule_set, mode) -> list[Step]`：MVP 阶段返回固定顺序 `[assign_heading_styles, format_body, insert_toc, word_postprocess]`，`Step.tool` / `Step.params` 来自 RuleSet 的 `fix_params_template`。

`replan(diagnoses, prev_plan) -> list[Step]`：把可执行（非 needs_human）的 `fix_plan` 拼到新 plan；全部 needs_human 时返回与 prev_plan 等价。

- [ ] **Step 9: 实现 harness.run**

严格按 R6.2 顺序：plan v1 → act → evaluate → diagnose → policies gate → replan → loop。退出条件 R6.3，超时 R6.9，崩溃恢复占位 R6.10（v0.1 仅打 trace，真正 resume 在 v0.3）。

`mode=fast` 走 `thesis_runner.run_format`（R6.6），`mode=dry_run` 在 act 前禁用 DocumentWriter 的真正写盘。

- [ ] **Step 10: 跑测试通过**

- [ ] **Step 11: 提交**

```
git add thesis_agent/orchestrator/ tests/agent/test_snapshot.py tests/agent/test_policies.py tests/agent/test_planner.py tests/agent/test_harness_loop.py
git commit -m "feat(agent): orchestrator main loop with snapshot/policies/planner"
```

---

## Task 10: 诊断层（Mock LLM Diagnoser）

**Files:**
- Create: `thesis_agent/diagnoser/llm_client.py`
- Create: `thesis_agent/diagnoser/diagnoser.py`
- Create: `thesis_agent/diagnoser/prompts/__init__.py`
- Create: `thesis_agent/diagnoser/prompts/system.md`（占位）
- Create: `tests/agent/test_diagnoser_mock.py`

**Why:** MVP 不接真 LLM。提供 `MockLLMClient` + diagnoser 框架，使 orchestrator 主循环能跑通；R5 真 LLM 留到 v0.2。

- [ ] **Step 1: 写 mock diagnoser 测试**

```python
def test_diagnose_with_no_llm_returns_needs_human(self):
    # R5.7
    report = EvalReport(..., results=[fail_result()])
    out = diagnose(report, fake_doc(), llm=None)
    self.assertTrue(out[0].needs_human)
    self.assertEqual(out[0].rationale, "未配置 LLM")
    self.assertEqual(out[0].fix_plan, [])

def test_diagnose_with_mock_llm_returns_structured_diagnosis(self):
    llm = MockLLMClient(canned={"body.line_spacing": {
        "root_cause":"...", "fix_plan":[{"tool":"tool_format_body","params":{"line_spacing":1.5}}],
        "confidence":0.9, "needs_human":False, "rationale":"..."}})
    out = diagnose(report_with_one_fail("body.line_spacing"), doc, llm)
    self.assertEqual(out[0].fix_plan[0].tool, "tool_format_body")

def test_diagnose_clamps_confidence_above_1(self):
    # confidence 自报 1.5 → 系统夹紧到 1.0；R5.5
    ...

def test_diagnose_force_low_confidence_after_repeat(self):
    # 同 (rule_id, evidence_hash) 第二次 fail → confidence 强降至 ≤0.5
    ...

def test_diagnosis_cache_uses_evidence_hash(self):
    # 同一 evidence_hash 第二次 diagnose → llm 不被调用；R5.6
    ...
```

- [ ] **Step 2: 跑测试，确认失败**

- [ ] **Step 3: 实现 LLMClient 抽象 + MockLLMClient**

```python
class LLMClient(Protocol):
    def complete(self, prompt: str, schema: dict) -> dict: ...

class MockLLMClient:
    def __init__(self, canned: dict[str, dict]): ...
    def complete(self, prompt, schema):
        # 按 prompt 中嵌入的 rule_id 查表返回；schema 不一致时返回畸形以测重试
        ...
```

- [ ] **Step 4: 实现 diagnoser.py**

```python
def diagnose(report: EvalReport, doc: DocumentModel,
             llm: Optional[LLMClient]) -> list[Diagnosis]:
    out = []
    for cr in report.results:
        if cr.status not in ("fail","error"):
            continue
        cache_key = _evidence_hash(cr)
        if cache.has(cache_key): out.append(cache.get(cache_key)); continue
        if llm is None:
            d = Diagnosis(rule_id=cr.rule_id, root_cause="", fix_plan=[],
                          confidence=0.0, needs_human=True,
                          rationale="未配置 LLM")
        else:
            d = _call_llm_with_retries(llm, cr, max_retries=2)   # D2=2
            d = _post_process(d, cr)                              # 夹紧 confidence、强降阈值
        cache.set(cache_key, d)
        out.append(d)
    return out
```

`_call_llm_with_retries` 走 JSON Schema 校验（R5.3 / R5.4）；R13.3 出站 hook 在 v0.2 加 LLM 时一并实现，MVP 仅 mock。

- [ ] **Step 5: 跑测试通过**

- [ ] **Step 6: 提交**

```
git add thesis_agent/diagnoser/ tests/agent/test_diagnoser_mock.py
git commit -m "feat(agent): diagnoser framework with mock LLM client (real LLM deferred to v0.2)"
```

---

## Task 11: 交付层（Trace + Report）

**Files:**
- Create: `thesis_agent/delivery/trace.py`
- Create: `thesis_agent/delivery/report.py`
- Create: `tests/agent/test_trace.py`
- Create: `tests/agent/test_report.py`

- [ ] **Step 1: 写 trace 测试（R7.7 / R11.1 / R11.2 / R11.3 / R11.6 / R11.8）**

```python
def test_trace_writes_one_json_per_line(self):
    t = Trace(path=tmp/"trace.jsonl")
    t.record(kind="plan", payload={"steps":[]})
    t.record(kind="tool_call", payload={"tool":"x"})
    lines = (tmp/"trace.jsonl").read_text().splitlines()
    self.assertEqual(len(lines), 2)
    for line in lines:
        json.loads(line)  # 必须可解析

def test_trace_kinds_whitelist(self):
    with self.assertRaises(InvalidTraceKindError):
        Trace(path=...).record(kind="random", payload={})

def test_trace_omits_llm_payloads_when_log_level_info(self):
    # 非 DEBUG 时只落 model_id / token_usage
    ...

def test_log_level_from_env(self):
    with env(THESIS_AGENT_LOG="DEBUG"): ...
def test_log_level_cli_overrides_env(self):
    ...
```

- [ ] **Step 2: 写 report 测试（R7.1 ~ R7.6 / R7.4 状态映射）**

```python
def test_report_md_has_four_sections(self):
    delivery = make_delivery_with_mixed_results()
    md = render_md(delivery)
    self.assertIn("✅ 已完成", md); self.assertIn("⚠️ 部分完成", md)
    self.assertIn("❌ 未完成", md); self.assertIn("⏭ 已跳过", md)

def test_report_json_summary_keys(self):
    j = render_json(delivery)
    for k in ["total","done","partial","failed","skipped"]:
        self.assertIn(k, j["summary"])

def test_report_json_items_required_fields(self):
    j = render_json(delivery)
    for it in j["items"]:
        for k in ["rule_id","status","severity","evidence","locator","fix_attempts","diagnosis"]:
            self.assertIn(k, it)

def test_status_mapping_error_to_failed_with_evaluation_error_rationale(self):
    # R4.6: error → failed，rationale 含 evaluation_error
    ...

def test_outputs_no_full_paragraph_text(self):
    # C5: trace / report 不含原稿正文长串
    ...
```

- [ ] **Step 3: 跑测试，确认失败**

- [ ] **Step 4: 实现 trace.py**

`Trace.record(kind, payload)`：kind 白名单 R7.7；写盘走追加模式（为 R6.10 崩溃恢复留口）；payload 进入前过 evidence 截断 + 段落正文剥离（C5 / R13.3）。

LOG_LEVEL 由环境变量 + CLI 双源（R11.8）。

- [ ] **Step 5: 实现 report.py**

`build_delivery(doc, rule_set, eval_report, trace, snapshots) -> DeliveryReport`。

`render_md` 按四区块 + 操作建议；`render_json` 按 R7.2 / R7.3 schema；状态映射按 R4.6 / R7.4。

R7.6 docx 标注（D8 = 优先 Word 批注）：在 docx 写出后调用 `_annotate_partial_failed_paragraphs(doc_path, items)`，加 Word Comment XML；失败回退到浅蓝底色 `#E6F3FF`。

`report.json.meta` 按 R11.6 / R11.7 / R11.8 填字段。

- [ ] **Step 6: 跑测试通过**

- [ ] **Step 7: 提交**

```
git add thesis_agent/delivery/ tests/agent/test_trace.py tests/agent/test_report.py
git commit -m "feat(agent): delivery layer with trace and four-bucket report"
```

---

## Task 12: CLI 与现有兼容（thesis-agent 命令 + thesis_runner 不变）

**Files:**
- Create: `thesis_agent/cli.py`
- Modify: `thesis_runner.py`（仅校验"行为不变"，不主动改）
- Create: `tests/agent/test_cli.py`
- Create: `tests/agent/test_compat_thesis_runner.py`

- [ ] **Step 1: 写 CLI 测试（R8.1 / R8.4 / R12.4）**

```python
def test_cli_run_full_mode_outputs_four_files(self):
    rc = cli.main(["run","--input",fix("perfect.docx"),"--profile","scau_2024","--mode","full"])
    self.assertEqual(rc, 0)
    self.assertTrue(out.with_suffix(".docx").exists())  # _formatted.docx
    # 等等

def test_cli_eval_only_does_not_write_docx(self): ...
def test_cli_invalid_mode_exits_with_helpful_message(self):
    # R8.4: InvalidModeError + 列出合法值
    ...
def test_cli_list_profiles(self): ...
def test_cli_list_tools(self): ...
def test_cli_list_rules_scau_2024(self): ...
def test_cli_log_level_flag(self):
    cli.main(["run","--log-level","DEBUG",...])   # R11.8
```

- [ ] **Step 2: 写兼容测试（R10.1 / R10.2 / R10.4 / R10.6）**

```python
def test_existing_thesis_runner_run_format_signature_unchanged(self):
    sig = inspect.signature(thesis_runner.run_format)
    self.assertEqual(list(sig.parameters), ["input_path","output_path","log","config","config_path"])

def test_existing_format_cli_still_works_without_new_args(self):
    # subprocess 调用 thesis_format_cli.py，对比 mode=fast 与未改造前的输出
    a = run_old_format(); b = run_new_format()
    from tools.compare_docx import segment_equal
    self.assertTrue(segment_equal(a, b))

def test_all_existing_unit_tests_still_pass(self):
    # 直接 discover 现有 tests/test_*.py（不含 tests/agent/），全绿
    ...
```

- [ ] **Step 3: 跑测试，确认失败**

- [ ] **Step 4: 实现 cli.py**

argparse 子命令：
- `run --input X --profile Y --mode {full,fast,eval_only,diagnose_only,targeted,dry_run} [--output Z] [--log-level INFO]`
- `list profiles | tools | rules <profile>`（R12.4）

CLI 入口注册到 `pyproject.toml`/`setup.py` 的 `console_scripts`（如已有）。

`thesis_format_cli.py` 不变；新 CLI 是独立入口（R10.5）。

- [ ] **Step 5: 验证 thesis_runner.py 不需要修改**

按 R10.1，`run_format` 签名 + 行为已等价于 `harness.run(mode="fast")`。**MVP 阶段不主动改动 `thesis_runner.py`，只在测试里验证现有行为不变**；T6 阶段（v0.2）再做转发优化。

- [ ] **Step 6: 跑全部测试通过**

```
py -3.10 -m unittest discover -s tests -v
```

- [ ] **Step 7: 提交**

```
git add thesis_agent/cli.py tests/agent/test_cli.py tests/agent/test_compat_thesis_runner.py
git commit -m "feat(agent): thesis-agent CLI with backward compatibility guard tests"
```

---

## Task 13: 端到端验证（Happy + Sad path 黄金样本）

**Files:**
- Create: `tests/scenarios/__init__.py`
- Create: `tests/scenarios/fixtures/__init__.py`
- Create: `tests/scenarios/fixtures/build_fixtures.py`（**代码构造** fixture，禁止依赖 fast 路径）
- Create: `tests/scenarios/test_e2e_happy.py`
- Create: `tests/scenarios/test_e2e_sad.py`

**Why:** 验证 MVP 整条链路。对应修订后的 requirements.md §4 "MVP 端到端验收"。

**关键约束（务必遵守）：**

- **不允许扩展 MVP Tool 能力**。T13 不得把 `apply_format` 里的 normalize_sections / renumber_headings / caption / table / abstract 等能力以任何形式偷渡进来。
- **fixture 用代码手工构造**，禁止 `thesis_format_cli.py` 或 `thesis_runner.run_format` 路径生成。每次跑测试由 `build_fixtures.py` 现造，不入 git。
- **happy path 不再做 full ↔ fast 段落级对比**。

- [ ] **Step 1: 写 fixture 构造器**

`tests/scenarios/fixtures/build_fixtures.py` 用 `python-docx` 直接拼装，覆盖 MVP 4 条规则：

```python
def build_perfect_docx(path):
    """SCAU 2024 默认 MVP 4 条 rule 全部 pass 的最小样本。
    
    覆盖：
    - body.font.east_asia = "宋体"
    - body.font.size = 12pt
    - body.line_spacing = 1.5
    - heading.h1.style_present = True
    - toc.entry_count: TOC 条目数 == Heading 数（最简：0=0）
    """
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.size = Pt(12)
    _set_east_asia(normal, "宋体")
    normal.paragraph_format.line_spacing = 1.5
    doc.add_paragraph("第一章 绪论", style="Heading 1")
    doc.add_paragraph("正文段落。", style="Normal")
    doc.save(path)


def build_messy_docx(path):
    """在 perfect 基础上引入 ≥3 处违规。"""
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.size = Pt(12)
    _set_east_asia(normal, "宋体")
    normal.paragraph_format.line_spacing = 2.0   # ❌ body.line_spacing
    # ❌ heading.h1.style_present: 不应用任何 Heading 样式
    doc.add_paragraph("第一章 绪论")
    doc.add_paragraph("正文")
    # 通过样式名 'TOC 1' 添一个 toc 条目，但没有对应 Heading
    # → ❌ toc.entry_count 不一致
    doc.add_paragraph("目录占位 1", style="TOC 1") if "TOC 1" in [s.name for s in doc.styles] else None
    doc.save(path)
```

- [ ] **Step 2: 写 happy path 测试**

```python
def test_happy_path_full_mode_done_at_least_4(self):
    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / "scau_perfect_thesis.docx"
        build_perfect_docx(str(in_path))

        rc = cli.main([
            "run", "--input", str(in_path),
            "--profile", "scau_2024", "--mode", "full",
            "--output-dir", tmp,
        ])
        self.assertEqual(rc, 0)

        # 4 件产物
        out_docx = Path(tmp) / "scau_perfect_thesis_formatted.docx"
        out_md   = Path(tmp) / "scau_perfect_thesis_report.md"
        out_json = Path(tmp) / "scau_perfect_thesis_report.json"
        out_tr   = Path(tmp) / "scau_perfect_thesis_trace.jsonl"
        for f in (out_docx, out_md, out_json, out_tr):
            self.assertTrue(f.exists(), msg=f"missing: {f}")

        # docx 可重新打开
        Document(str(out_docx))   # 不抛即过

        # 报告 summary
        report = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertGreaterEqual(report["summary"]["done"], 4)
        self.assertEqual(report["summary"]["failed"], 0)

        # 4 个 MVP rule_id 都 done
        statuses = {it["rule_id"]: it["status"] for it in report["items"]}
        for rid in ("body.font.east_asia", "body.font.size",
                    "body.line_spacing", "heading.h1.style_present"):
            self.assertEqual(statuses.get(rid), "done",
                             msg=f"{rid} status was {statuses.get(rid)!r}")
```

- [ ] **Step 3: 写 sad path 测试**

```python
def test_sad_path_eval_only_lists_violations(self):
    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / "scau_messy_thesis.docx"
        build_messy_docx(str(in_path))

        rc = cli.main([
            "run", "--input", str(in_path),
            "--profile", "scau_2024", "--mode", "eval_only",
            "--output-dir", tmp,
        ])
        self.assertEqual(rc, 0)

        report = json.loads(
            (Path(tmp) / "scau_messy_thesis_report.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(
            report["summary"]["failed"] + report["summary"]["partial"], 3
        )
        # 报告必须列出 rule_id + evidence + advice 三个非空字段
        violators = [
            it for it in report["items"]
            if it["status"] in ("failed", "partial")
        ]
        for it in violators[:3]:
            self.assertTrue(it["rule_id"])
            self.assertTrue(it["evidence"])
            self.assertTrue(it["advice"])

        # eval_only 不写 docx
        self.assertFalse((Path(tmp) / "scau_messy_thesis_formatted.docx").exists())
        # 输入文件未被修改
        ...
```

- [ ] **Step 4: 跑 T13 + 全量回归**

```
py -m unittest discover -s tests/scenarios -v
py -m unittest discover -s tests -v
```

期望：T13 全绿；现有 117 条 + T13 新增 ≥2 条全绿，零回归。

- [ ] **Step 5: 提交**

```
git add tests/scenarios/
git commit -m "test(agent): e2e happy + sad path with hand-built fixtures"
```

---

## Task 14: 文档与冻结

**Files:**
- Modify: `README.md`
- Create: `docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-changelog.md`
- Modify: 各模块 docstring（按需）

- [ ] **Step 1: README 新增章节**

在现有 README 的"项目结构"前后加一节"thesis-agent 命令行（实验性 / v0.1）"，介绍：
- 6 种 mode 表（与设计文档第 3.6 节对齐）
- 3 个产物（docx / report.md / report.json + trace.jsonl）
- 与现有 GUI / CLI 的关系（R10.5）：`thesis_format_cli.py` 不变；新 CLI `thesis-agent` 是独立入口
- 链接到设计 / 需求 / 计划三份 spec

- [ ] **Step 2: 写 changelog**

新建 `2026-04-15-ai-thesis-agent-architecture-changelog.md`，列：
- v0.1 已实现：T1 ~ T13
- v0.2 计划：真 LLM 接入（R5 全部）+ R13.3 出站 hook + 大量 Tool 包装（R3.3 全集）+ `thesis_runner` 转发到 harness
- v0.3 计划：人在回路全套（R9）+ resume（R6.10）+ GUI 完成度报告标签页（R10.8）
- 已知限制：R5 真 LLM 未接，R9 resume 未实现，evidence 截断行为对部分中文逗号可能截在多字节边界（已用 ellipsis 兜底）

- [ ] **Step 3: 提交**

```
git add README.md docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-changelog.md
git commit -m "docs(agent): document v0.1 thesis-agent CLI and roadmap"
```

- [ ] **Step 4: 最终全量回归（验收前最后一步）**

```
py -3.10 -m unittest discover -s tests -v
```

预期：所有测试全绿。如有失败，遵循 @superpowers:verification-before-completion，在声称完成前修干净。

- [ ] **Step 5: 打 v0.1 tag**

```
git tag -a thesis-agent-v0.1 -m "thesis-agent MVP: rule-based formatting + structured report (no real LLM yet)"
```

---

## 完成度自检清单

执行结束后请逐项确认（对应 requirements.md 验收点）：

- [ ] R1 子集（4 维度）：编译器能从 `defaults/scau_2024.yaml` 产出至少 4 条 MVP rule
- [ ] R2.1 / R2.3 / R2.4：DocumentModel 提供读 / 受控写 API；上层不直接 import python-docx
- [ ] R3.1 / R3.2 / R3.6 / R3.7 + 4 Tool：4 个 MVP Tool 满足契约 + registry 自动发现
- [ ] R4.1 ~ R4.7：评测 runner + 4 Check 全通过
- [ ] R5 mock：未配 LLM 时 fail 项标 `needs_human=True`，不阻塞主循环
- [ ] R6.1 ~ R6.10：主循环 6 种 mode + 步级回滚 + 全局 timeout
- [ ] R7.1 ~ R7.6：四产物 + 四档报告 + Word 批注标注
- [ ] R8.1 / R8.2 / R8.5：CLI 支持 `full` / `fast` / `eval_only`
- [ ] R10.1 ~ R10.8：现有命令、GUI、yaml、tests 全部不动；段落级等价由 compare_docx 保证
- [ ] R11.1 / R11.2 / R11.6 / R11.8：trace + meta + LOG_LEVEL
- [ ] R12.1 / R12.2 / R12.3 / R12.7：新 Rule / Tool / Profile 不动核心代码 + 自动发现
- [ ] R13.1 / R13.2：原稿不被覆盖
- [ ] C1 ~ C7：中文优先 / 平台优雅降级 / Python 3.10+ / 性能基准 / 不外泄正文 / 单测齐全
- [ ] MVP happy path：4 文件产出 + done≥4 + failed=0 + 段落级等价 fast 模式
- [ ] MVP sad path：能识别 ≥3 条违规 + 给出可执行的操作建议

---

## 风险与备忘

- **fixture 准备**：`scau_perfect_thesis.docx` 需要在 T13 之前手工准备好。建议先用 `thesis_format_cli.py` 跑现有 `thesis-typeset-main` 自带任意 docx 后定型，存进 git。
- **Word 批注 XML**（R7.6 / D8）：python-docx 不直接支持 Comment，需要手写 OOXML（参考 `<w:commentRangeStart/end>` + `comments.xml` part）。如成本过高可先降级到底色高亮，标记为 `tech-debt-T11`。
- **崩溃恢复（R6.10）**：v0.1 仅落 trace 占位，真正 resume 在 v0.3。tasks.md 明确不在 MVP 里实现 `--resume`。
- **现有测试回归风险点**：`thesis_runner.run_format` / `thesis_format_cli.py` / `thesis_formatter/*.apply_format` 都不能动；T12 用 `compare_docx` 守护 `mode=fast` 输出与改造前一致。
- **依赖添加**：MVP 不引入新 PyPI 依赖；如 fixture 生成或 schema 校验需要，请单独 PR 加，不混入本计划。
