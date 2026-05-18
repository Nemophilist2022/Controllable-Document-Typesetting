# thesis-agent 变更日志

> 配套设计 / 需求 / 计划：同目录 `2026-04-15-ai-thesis-agent-architecture-{design,requirements}.md` + `docs/superpowers/plans/2026-04-15-ai-thesis-agent-architecture.md`。

## v0.1（2026-05-16 release notes）

**核心承诺**：基于规则评测 + AI 诊断的可控交付系统，跟现有 `thesis_format_cli.py` / GUI 并存、不替换。

**入口**：

```bash
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024 --mode full
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024 --mode eval_only
python -m thesis_agent.cli list profiles | tools | rules <profile>
python -m thesis_agent.cli run --profile scau_2024 --resume <pending.json>
```

**冻结的能力**：

- 7 层架构（接入 / 规约 / 工具 / 评测 / 诊断 / 编排 / 交付）
- 41 条 SCAU 2024 profile 规则，覆盖 R1.3 列出的 12 维度
- 16 个 Tool（4 MVP + 12 包装现有 `thesis_formatter/*`）
- 6 种运行模式（full / fast / eval_only / diagnose_only / targeted / dry_run）
- OpenAI 兼容 LLM 客户端（OpenAI / DeepSeek / 通义 / 本地 vLLM / Ollama），含 R13.3 出站守卫与 token / cost 估算
- 人在回路：`<stem>_pending.json` 暂停/恢复，`auto_apply_diagnosis={yes,confirm,no}` 三档
- docx 标注（浅蓝底色 `#E6F3FF` + 内嵌注释）
- GUI "AI 评测（实验性）" 按钮，`mode=eval_only` 弹四档报告窗口

**测试覆盖**：`Ran 181 tests in 102.379s — OK`（venv on Python 3.13.12）

**v0.1 已知限制**（v0.2/v0.3 路线见下）：

- 12 维度的 41 条规则约 60% 已有完整 check，其余按 skip 处理（不会误报 fail）
- LLM 诊断只在配置了凭据时启用；未配时 fail 项标 needs_human
- mode=full 与 mode=fast 段落级语义不一致（mode=full 只跑当前注册的工具子集，期望差异）
- `tool_assign_heading_styles` 在原稿已有"第N章 ..."字样的 TOC 段时会误升 H1（C2，已写入 docstring 绕过办法）

---



### 已完成

| Task | 范围 | 主要交付物 |
|---|---|---|
| T1  | 项目骨架 | `thesis_agent/` 七层目录，`tools/compare_docx.py` 段落级语义比较器，5 条骨架自检测试 |
| T2  | 数据契约冻结 | `Rule` / `RuleSet` / `CheckResult` / `EvalReport` / `Diagnosis` / `ToolCall` / `ToolResult` / `ToolContext` / `ErrorInfo` / `LoadResult`，16 条契约测试 |
| T3  | 接入层 | `DocumentModel` 双轨 API（读 + 受控写）、`document_loader`（复用 `thesis_runner` 转换链）、`template_loader`（YAML + NL stub）|
| T4  | 规约层 | 5 个 predicate（equals / one_of / regex / range / exists）、compiler、`scau_2024` profile |
| T5  | 工具注册表 | `tools/registry.py` 自动发现，未注册抛 `UnknownToolError` |
| T6  | 4 个 MVP Tool | `tool_format_body` / `tool_assign_heading_styles` / `tool_insert_toc` / `tool_word_postprocess` |
| T7  | 评测 runner | `evaluate(doc, rule_set, only_rule_ids=None)`，禁止 import LLM 客户端的静态扫描守护 |
| T8  | 4 条 MVP check | `check_body` / `check_headings` / `check_toc` + `check_fonts` 占位 |
| T9  | 编排层 | `harness.run`、`SnapshotManager`、`Policies`（D1~D8 默认值冻结）、`planner.default_plan` / `replan` |
| T10 | Diagnoser 框架 | mock LLM client，confidence 夹紧 + 重复失败强降，未配 LLM 时 needs_human=True |
| T11 | 交付层 | `Trace` jsonl + 8 种 kind 白名单、`build_delivery_report` 状态映射、md / json 两种渲染 |
| T12 | CLI + 兼容 | `thesis-agent run / list profiles / list tools / list rules`，`thesis_runner.run_format` 行为零变化 |
| T13 | E2E 验收 | hand-built fixtures + happy path（done≥4 / failed=0）+ sad path（≥3 violations） |
| A1  | 全套 Tool 包装 | 12 个新增 Tool（page / heading / caption / table / reference / header / cover），harness `ToolContext.config` 注入修复（C3） |
| A2  | RuleSet 扩到 12 维度 | 41 条 rule 覆盖页面 / 字体 / 标题 / 编号 / 正文 / 图表 / 三线表 / 目录 / 参考文献 / 页眉 / 页码 / 前置页；新增 5 个 check 模块 |
| A3  | 真 LLM 诊断 | `OpenAICompatibleClient`（zero deps，`urllib.request`），R13.3 出站守卫，cost / token telemetry 注入 `report.json.meta` |
| B1  | 人在回路 + resume | `pending.json` 持久化、`hitl_gates`（destructive_ops 永远生效），`--resume` / `--auto-apply-diagnosis`，R9.6 prominent warning |
| B2  | docx 批注标注 | `delivery/annotator.py` 浅蓝底色 `#E6F3FF` + 内嵌注释，三类 locator 解析（paragraph_index / style_name / front_matter）|
| B3  | GUI 集成 | `thesis_gui.py` 新增"AI 评测（实验性）"按钮，跑 `mode=eval_only` 后弹四档报告窗口；现有界面零变化 |
| T14 | 文档 | README 新增 thesis-agent 章节 + 本 changelog |

### 已知缺陷与已记录

| Id | 描述 | 状态 |
|---|---|---|
| C1 | `thesis_formatter/structure.py` 调用未 import 的 `normalize_title` | **已修**（v0.1 收尾） |
| C2 | `tool_assign_heading_styles` 误把 TOC 段升为 H1（章节正则太宽） | 已写入 docstring；v0.3 在 `thesis_formatter.headings.auto_assign_heading_styles` 修 |
| C3 | harness 没把 RuleSet 关联 cfg 注入 ToolContext | **已修**（A1） |
| C4 | GUI `_start_ai_review` worker 在 root 已 destroy 后调 `_root.after` 抛 `RuntimeError` | **已修**（v0.1 收尾，加 `safe_after` helper + race 回归测试） |

### v0.2 / v0.3 计划

- **v0.2**：扩 LLM 诊断 prompt 模板（按 rule 类型分文件），让真 LLM 在不同领域给出更准的修复计划；在 `report.json.meta.llm_telemetry` 中加入 `prompt_id` 维度
- **v0.2**：把约 10 条目前 skip 的 check 实装（caption.numbering.continuity / heading.numbering.continuity / reference.first_line_indent / header.enabled / toc.font.east_asia / page_number.front.format / page_number.body.format 等）
- **v0.3**：进程崩溃自动检测 + 自愈式 resume（R6.10 第二阶段）
- **v0.3**：修 C2 — TOC 段被 `auto_assign_heading_styles` 误升 H1 的问题，需要在不破坏现有 `thesis_runner` 用户的前提下分支处理
- **v0.3**：DEBUG 日志级别下把 LLM prompt + raw response 写入 trace（R11.3 完整实现）
- **v0.4**：从 fallback 浅蓝底色升级到 Word Comment XML 注入（D8 优选形式）；多 profile（generic_gb7714 国标通用 / 北大 / 清华）；模板自然语言抽取 LLM 实装

## 测试覆盖回看

| 阶段 | 测试总数 | 备注 |
|---|---|---|
| T13 完成时 | 133 | 5 骨架 + agent 单元测试 + 现有 23 |
| A1 完成时 | 147 | +14 legacy tools 契约 + 行为测试 |
| A2 完成时 | 153 | +5 多维度 check + fixture 调整 |
| A3 完成时 | 173 | +20 LLM 客户端 + 出站守卫 + 集成测试 |
| B1 完成时 | 191 | +18 pending IO + hitl gates + harness 暂停/恢复测试 |
| B2 完成时（待验证） | 199 | +8 annotator 单测；harness 集成靠 B1 测试间接覆盖 |
| B3 完成时（待验证） | 201 | +2 GUI AI 评测按钮测试 |
| **v0.1 验证通过** | **181 实跑 OK** | discover -s tests 输出 `Ran 181 tests in 102.379s — OK`；数字与最初估算 201 的差异源于 unittest 把 subTest 计为单条 |
| v0.1 收尾 GUI race 修补 | 182 | +1 `test_ai_review_worker_swallows_runtime_error_after_root_destroyed` |

> 上一行"待验证"是因为本地 Python 环境在 B2 阶段出现 anaconda 启动器冲突，B2 / B3 的代码已落地但未在线跑过完整 unittest discover。等环境恢复后立即回看。

## 文档索引

- 架构设计：`docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-design.md`
- 需求与冻结默认值（D1~D8）：`docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-requirements.md`
- 落地计划与任务划分：`docs/superpowers/plans/2026-04-15-ai-thesis-agent-architecture.md`
- 本变更日志：`docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-changelog.md`
