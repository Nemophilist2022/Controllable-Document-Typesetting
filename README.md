# Thesis Typeset Agent

> A controllable thesis formatting system for Word documents. It extracts YAML formatting rules from natural-language requirements or Word templates, then checks, fixes, re-checks, and reports thesis formatting completion.

## Project Description

Thesis Typeset Agent is a Windows-first automation tool for academic thesis formatting. It converts formatting requirements into executable YAML rules, applies them to Word documents, and produces traceable delivery reports that show which rules were completed, partially fixed, failed, or skipped.

## Key Features

- Natural language to YAML formatting rules.
- Word `.docx` template to YAML formatting rules.
- Custom profile formatting via `--config template.yaml`.
- Closed-loop checking and repair: evaluate -> fix -> re-evaluate.
- Machine-readable and human-readable reports: `report.json` and `report.md`.
- Supports `.docx`, `.doc`, `.txt`, `.md`, and `.tex` inputs.
- CLI and GUI workflows coexist.

## Suggested GitHub About Description

```text
Controllable thesis formatting agent: extract YAML rules from natural language or Word templates, auto-format Word theses, and generate completion reports.
```

## Suggested Topics

```text
thesis-formatting, word-automation, docx, yaml, academic-writing, python, formatting-agent
```

---

# 论文排版工具

面向通用论文场景的 Windows 桌面排版工具。

这个版本更强调“直接好用”：
- 参数集中在一个桌面工作台里完成
- 常见论文格式问题可以一次处理
- 操作路径更清晰，适合赶论文时快速使用

## 当前版本亮点

### 1. 一套流程处理常见论文排版任务
- 支持 `.docx`、`.doc`、`.txt`、`.md`、`.tex` 输入，统一输出 `.docx`
- 页面、正文、标题、页眉页码、目录、图表、封面声明都能集中配置
- 支持配置保存和加载，方便同校同学复用模板

### 2. 更适合桌面效率工具的界面
- 左侧导航、右侧配置区、底部操作区分工更清楚
- 长页面可以直接滚动，不用反复拖滚动条
- 主操作按钮和运行日志更容易找到
- 界面语言和交互都更偏实用，不做花哨装饰

### 3. 覆盖论文里最麻烦的一批格式问题
- 标题层级、编号与段距统一
- 页码、页眉、前置页与正文分区处理
- 图表题注、三线表、参考文献缩进等高频问题可配置
- 支持封面、声明页和特殊标题映射

## 主要优点

- 不只是改字体字号，而是把论文里常见的排版环节放到一套流程里处理
- 对“标题编号乱、目录不一致、页码不对、题注不规范、参考文献缩进错误”这类问题更有针对性
- 上手门槛低，适合先用默认配置直接跑，再按学校要求微调
- 既能点界面，也能走命令行，方便个人使用和分发给同学

## 使用时需要知道的边界

1. **仍然建议人工复核最终文档**
   - 这个工具能大幅减少重复劳动，但不能替代最终审稿和格式核对。

2. **不同学校要求差异大时，仍需要自己调配置**
   - 默认配置偏向 SCAU 2024。
   - 换学校时，封面、声明、摘要页、特殊标题等通常需要按本校要求调整。

3. **原稿越规范，自动处理效果越稳定**
   - 如果标题、题注、结构写法非常随意，工具可能无法完全按预期识别。

4. **部分能力依赖本机环境**
   - `.doc` 转换、目录更新等场景在 Windows + Word 环境下效果更完整。
   - `.txt/.md/.tex` 转换需要 Pandoc。

5. **复杂版面仍可能需要手工微调**
   - 比如图片内部文字、复杂表格局部布局、特殊文本框等，不属于完全自动处理范围。

## 适用场景

- 论文初稿已经写完，需要统一格式
- 学校有一套明确规范，但手工调整太耗时
- 同一学院或同学之间希望共享一套配置模板
- 想先快速生成一版规范文档，再做最后人工检查

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

当前依赖：
- `python-docx`
- `pyyaml`
- `pywin32`
- `ttkbootstrap`

### 2. 启动 GUI

```bash
python run_gui.py
```

### 3. 命令行使用

```bash
python thesis_format_cli.py --input 论文.docx
python thesis_format_cli.py --input 论文.docx --output 论文_规范版.docx
python thesis_format_cli.py --input 论文.docx --config thesis_config.yaml
python thesis_format_cli.py --dump-config
```

## 单独处理模式

适合只修局部、不想大动正文时使用：

- 单独改页码：只按现有分节调整页码，不自动补分节，尽量少动正文。
- 单独改页眉：只按现有分节调整页眉，不自动补分节，尽量少动正文。
- 单独插入/更新目录、单独插入外部封面，仍按原有单独处理逻辑执行。
## 输入与依赖说明

| 输入格式 | 说明 | 额外依赖 |
|----------|------|----------|
| `.docx` | 直接进入格式化流程 | 无 |
| `.doc` | 先转 `.docx` | 需要 Microsoft Word |
| `.txt` | 预处理后经 Pandoc 转 `.docx` | 需要 Pandoc |
| `.md` | Pandoc 转 `.docx` | 需要 Pandoc |
| `.tex` | Pandoc 转 `.docx` | 需要 Pandoc |

## 原稿准备建议

### `txt` 原稿怎么准备最合适

`txt` 更适合 **纯文字为主、结构比较规整** 的论文初稿。按当前代码，最稳妥的准备方式是：

- 不要放图片。`txt` 本身不适合承载图片内容，图像类内容建议走 `Word` 原稿。
- 全部文字顶格写，不要手动打空格做首行缩进，也不要用制表符做人为排版。
- 标题尽量单独占一行，正文另起段。
- 常见标题写法都能识别，例如：`第1章`、`1.1`、`1.1.1`、`1.1.1.1`、`一、`、`（一）`、`Chapter 1`。
- 中文摘要建议单独写一行 `摘要`，关键词写成 `关键词：...`。
- 英文摘要建议写成 `Abstract:` 或单独一行 `Abstract` 后下一行接正文；英文关键词写成 `Key words: ...`。
- 如果有表格，最适合的写法是：先写表题行，再用 **Tab 分隔** 每列数据。这样工具更容易把它转成表格。
- 从 Word 表格直接复制到 `txt` 也可以识别，前提是粘贴后仍然保持为 **Tab 分列** 的文本行。
- 参考文献建议按 `[1] ...`、`[2] ...` 这种形式逐条写。

一句话理解：**`txt` 最适合“没有图片、没有复杂版面、正文和标题都很规整”的原稿。** 这种情况下，工具处理起来通常最省心。

### `Word` 原稿怎么准备更稳

`Word` 原稿的兼容性更强，适合带图片、表格、脚注和已有版面内容的论文。当前代码下，推荐程度分两档：

#### 最推荐的做法

- 先把正文标题尽量套上 `Heading 1` 到 `Heading 4`（或对应中文标题样式）。
- 让每一级标题单独成段，不要把标题和正文写在同一段里。
- 图题、表题尽量写成规范形式，例如 `图1.1 ...`、`表1.1 ...`、`续表1.1 ...`。
- 摘要、目录、参考文献、致谢这些特殊标题尽量单独成段。

这样做的好处是：**识别更稳、遗漏更少、目录和题注处理也更可靠。**

#### 没有先排版也不是完全不能用

按当前代码，`Word` 原稿即使没有先套标题样式，工具也会自动尝试识别一部分标题并补上层级。也就是说，**完全未排版的草稿不是完全不支持**。

但要注意，这种自动识别更依赖原稿本身写得规整：

- 标题最好是单独一行。
- 标题不要写成长句，越像“一个独立标题”越容易识别。
- 编号标题最好保持常见格式，例如 `第1章 绪论`、`1.1 研究背景`、`1.1.1 ...`。
- 特殊标题如 `摘要`、`参考文献`、`致谢` 单独成段更稳。

所以更准确的说法是：
**Word 原稿支持“未完整排版”的内容，但如果你能先把标题层级套好，整体成功率和完整度会更高。**

## thesis-agent 命令行（实验性 / v0.1）

`thesis-agent` 是基于规则评测 + AI 诊断的可控交付系统，跟现有 `thesis_format_cli.py` / GUI **并存、不替换**。它跑完会同时给你三件机读产物：

- `<论文>_formatted.docx`（mode=full / targeted 时输出）
- `<论文>_report.md` / `<论文>_report.json`：按 ✅ 已完成 / ⚠ 部分完成 / ❌ 未完成 / ⏭ 已跳过 四档汇报
- `<论文>_trace.jsonl`：每一步 plan / 工具调用 / 评测 / 诊断的全程审计

### 6 种运行模式

| mode | 改 docx | 跑 evaluate | 跑 diagnose（LLM） | 写 docx | 写 report |
|---|---|---|---|---|---|
| `full` | 是 | 是 | 是 | 是 | 是 |
| `fast` | 是 | 否 | 否 | 是 | 是（仅汇总） |
| `eval_only` | 否 | 是 | 否 | 否 | 是 |
| `diagnose_only` | 否 | 是 | 是 | 否 | 是 |
| `targeted` | 是（局部） | 局部 | 否 | 是 | 是 |
| `dry_run` | 否 | 是 | 是 | 否 | 是 |

### 用法

```bash
# 最常用：跑全套，无 LLM 时未识别项标 needs_human
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024 --mode full

# 只评测不动文档
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024 --mode eval_only

# 列出可用资源
python -m thesis_agent.cli list profiles
python -m thesis_agent.cli list tools
python -m thesis_agent.cli list rules scau_2024
```

### 接 LLM（OpenAI 兼容）

```bash
# OpenAI
set THESIS_AGENT_LLM_API_KEY=sk-...
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024

# DeepSeek
set THESIS_AGENT_LLM_API_KEY=sk-...
set THESIS_AGENT_LLM_BASE_URL=https://api.deepseek.com/v1
set THESIS_AGENT_LLM_MODEL=deepseek-chat
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024

# 本地 Ollama / vLLM
set THESIS_AGENT_LLM_API_KEY=ollama
set THESIS_AGENT_LLM_BASE_URL=http://localhost:11434/v1
set THESIS_AGENT_LLM_MODEL=llama3:8b
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024
```

LLM 出站请求在发出前会过 R13.3 守卫，**绝不**夹带原稿正文长串内容。telemetry 与 cost 估算写入 `report.json.meta`。

#### LLM 诊断的实际效果

发现 `body.line_spacing` 失败时，LLM 返回示例：

```json
{
  "rule_id": "body.line_spacing",
  "root_cause": "Normal style line spacing was set to 2.0",
  "fix_plan": [
    {
      "tool": "tool_format_body",
      "params": {"line_spacing": 1.5},
      "expected_effect": "Reset to 1.5x line spacing"
    }
  ],
  "confidence": 0.95,
  "needs_human": false,
  "rationale": "Numeric spacing — straightforward fix."
}
```

主循环把这个 `fix_plan` 当作下一轮 `plan` 跑（自动化 / 暂停审批 / 拒诊三档由 `--auto-apply-diagnosis` 决定）。最终 `report.json.items` 里这条规则状态会从 `failed` 变成 `done`。

每次 LLM 调用都会写入 `report.json.meta.llm_telemetry`：

```json
"llm_telemetry": {
  "model": "gpt-4o-mini",
  "calls": 5,
  "timeouts": 0,
  "errors": 0,
  "prompt_tokens": 1234,
  "completion_tokens": 567,
  "total_tokens": 1801,
  "cost_usd_estimate": 0.000532
}
```

#### Prompt 模板按规则分文件

不同 rule 类型走不同的提示模板，全部位于 `thesis_agent/diagnoser/prompts/<prefix>.md`：

```
body.md          — 正文样式相关
heading.md       — 标题样式 / 编号
caption.md       — 图表题
page.md          — 页边距 / 装订线
page_number.md   — 页码格式
table.md         — 三线表
reference.md     — 参考文献
header.md        — 页眉
front_matter.md  — 摘要 / 关键词
toc.md           — 目录
fallback.md      — 兜底
```

调换或新增模板：直接编辑 / 添加 `<prefix>.md`，运行时按 rule_id 最长前缀匹配选用，无需改代码。


### 人在回路

LLM 给出的低置信度诊断默认不自动执行：

```bash
# 跑完写 _pending.json 后等用户审 — 默认行为
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024 --mode full

# 编辑 _pending.json，把 decision 改为 accept / reject
# 再恢复
python -m thesis_agent.cli run --profile scau_2024 --resume 论文_pending.json

# CI 场景：不暂停，需要人审的全部当 failed
python -m thesis_agent.cli run --input 论文.docx --profile scau_2024 --auto-apply-diagnosis no
```

### GUI 集成

`thesis_gui.py` 主操作按钮"开始格式化"行为不变。右下角新增"AI 评测（实验性）"按钮，点击后用 `mode=eval_only` 跑一次 thesis-agent 并弹出完成度报告窗口；不动原文档。

### v0.1 限制

- LLM 诊断的真实可用性依赖你接的模型质量，confidence < 0.7 强制走人工
- 12 维度的 41 条规则中约 60% 已有完整 check，其余按 skip 处理（不会误报 fail）
- mode=full 与 mode=fast 段落级语义不一致是预期行为：mode=fast 走原 `thesis_runner.run_format`，mode=full 只跑当前注册的工具子集
- `tool_assign_heading_styles` 在原稿已有"第N章 ..."字样的 TOC 段时会误升 H1（详见 [thesis_agent/tools/heading_tools.py 文档注释](thesis_agent/tools/heading_tools.py)）

完整设计见 `docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-design.md`，需求与冻结默认值见同目录 `-requirements.md`。

## 项目结构

| 路径 | 说明 |
|------|------|
| `thesis_gui.py` | 桌面 GUI |
| `run_gui.py` | GUI 启动脚本 |
| `thesis_format_cli.py` | CLI / GUI 统一入口 |
| `thesis_runner.py` | 输入转换、格式化、后处理总流水线 |
| `thesis_config.py` | 默认配置与 YAML 加载 |
| `thesis_formatter/` | 核心排版逻辑 |
| `word_postprocess.py` | Word 后处理 |
| `defaults/scau_2024.yaml` | 默认学校配置 |
| `tests/` | 自动化测试 |

## 测试

```bash
python -m unittest discover -s tests
```

## 打包

项目内保留了 `build_exe.bat` 和 `thesis-format.spec`，可继续用于 Windows exe 打包。

## 许可证

GPL-3.0

