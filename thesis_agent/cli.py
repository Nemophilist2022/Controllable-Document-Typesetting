"""thesis-agent CLI (R8.1, R12.4).

Subcommands:
    run --input X --profile Y [--output Z] [--mode full|fast|...]
        [--output-dir D] [--log-level INFO|DEBUG|...]

    list profiles
    list tools
    list rules <profile>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional, Sequence


def _encode_safe(text: str, stream=None) -> str:
    """Return text that can be written to the target stream.

    Windows consoles are often GBK/CP936. Direct emoji output can raise
    UnicodeEncodeError and abort an otherwise successful run, so CLI
    status lines must be defensively encoded.
    """
    stream = stream or sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    replacements = {
        "⚠️": "[WARN]",
        "⚠": "[WARN]",
        "✅": "[DONE]",
        "❌": "[FAIL]",
        "⏭": "[SKIP]",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        return text.encode(encoding, errors="replace").decode(encoding)


def _print_line(text: str = "", *, file=None) -> None:
    stream = file or sys.stdout
    print(_encode_safe(str(text), stream), file=stream)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def _cmd_run(args) -> int:
    from .ingest.template_loader import InvalidTemplateError
    from .orchestrator.harness import (
        InvalidModeError, OverwriteInputError, RunOptions, run,
    )

    if not args.input and not args.resume:
        _print_line("thesis-agent: --input or --resume is required", file=sys.stderr)
        return 2

    profile = _resolve_run_profile(args.profile, args.config)

    options = RunOptions(
        output_path=args.output,
        output_dir=args.output_dir,
        llm_api_key=args.llm_api_key,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        llm_disabled=args.no_llm,
        auto_apply_diagnosis=args.auto_apply_diagnosis,
        resume_path=args.resume,
        config_path=args.config,
    )
    if args.log_level:
        os.environ["THESIS_AGENT_LOG"] = args.log_level.upper()

    try:
        result = run(
            input_path=args.input or "",
            profile=profile,
            mode=args.mode,
            options=options,
        )
    except InvalidModeError as exc:
        _print_line(f"thesis-agent: {exc}", file=sys.stderr)
        return 2
    except OverwriteInputError as exc:
        _print_line(f"thesis-agent: {exc}", file=sys.stderr)
        return 3
    except (FileNotFoundError, InvalidTemplateError, RuntimeError) as exc:
        _print_line(f"thesis-agent: template/config error: {exc}", file=sys.stderr)
        return 2

    _print_line(f"汇总: {result.summary}")
    _print_line(f"报告 (md):   {result.report_md_path}")
    _print_line(f"报告 (json): {result.report_json_path}")
    _print_line(f"trace:       {result.trace_path}")
    if result.docx_path:
        _print_line(f"输出 docx:    {result.docx_path}")
    if result.pending_path:
        _print_line(f"?? ?? pending: {result.pending_path}")
        _print_line(f"   ????:    {result.exit_reason}")
        resume_cmd = f"thesis-agent run --profile {profile} --resume {result.pending_path}"
        if args.config:
            resume_cmd += f" --config {args.config}"
        _print_line(f"   ????:    {resume_cmd}")
    return 0 if result.ok else 1


def _resolve_run_profile(profile: Optional[str], config_path: Optional[str]) -> str:
    if profile:
        return profile
    if config_path:
        return os.path.splitext(os.path.basename(config_path))[0]
    return "scau_2024"


def _cmd_list_profiles(_args) -> int:
    from .spec.profiles import available_profiles

    for name in available_profiles():
        _print_line(name)
    return 0


def _cmd_list_tools(_args) -> int:
    from .tools import registry

    registry.clear()
    registry.autoload()
    for tool in registry.all_tools():
        _print_line(f"{tool.name:40s} requires={tool.requires}")
    return 0


def _cmd_list_rules(args) -> int:
    if args.config:
        from .ingest.template_loader import from_yaml
        from .spec.compiler import compile as compile_rule_set

        profile = _resolve_run_profile(args.profile, args.config)
        rs = compile_rule_set(from_yaml(args.config), profile=profile, version="custom")
    else:
        if not args.profile:
            _print_line("thesis-agent: list rules requires <profile> or --config",
                        file=sys.stderr)
            return 2
        from .spec.profiles import load_profile

        rs = load_profile(args.profile)

    for rule in rs.rules:
        _print_line(f"{rule.id:40s} severity={rule.severity:6s} "
                    f"predicate={rule.predicate} fix_tool={rule.fix_tool}")
    return 0


def _cmd_extract_template(args) -> int:
    from .ingest.template_loader import from_docx_template, from_natural_language

    try:
        if args.text is not None:
            result = from_natural_language(args.text, output_path=args.output)
        elif args.docx is not None:
            result = from_docx_template(args.docx, output_path=args.output)
        else:
            _print_line("thesis-agent: --text or --docx is required", file=sys.stderr)
            return 2
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        _print_line(f"thesis-agent: template extraction error: {exc}",
                    file=sys.stderr)
        return 2

    status = "pending_review" if result.pending_human_review else "ready"
    _print_line(
        f"模板提取完成: {result.yaml_path} "
        f"status={status} fields={len(result.extracted_fields)}"
    )
    if result.extracted_fields:
        _print_line("提取字段: " + ", ".join(result.extracted_fields))
    return 0


# ---------------------------------------------------------------------------
# argparse plumbing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thesis-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="格式化论文")
    p_run.add_argument("--input", required=False,
                       help="输入论文路径；--resume 模式下可省略")
    p_run.add_argument("--profile", default=None,
                       help="内置 profile 名称；未提供 --config 时默认 scau_2024")
    p_run.add_argument("--config", default=None,
                       help="用户 YAML 模板/配置文件；提供后直接编译为规则集")
    p_run.add_argument("--mode", default="full",
                       choices=["full", "fast", "eval_only", "diagnose_only",
                                "targeted", "dry_run"])
    p_run.add_argument("--output")
    p_run.add_argument("--output-dir")
    p_run.add_argument("--log-level", default=None)
    p_run.add_argument("--llm-api-key", default=None,
                       help="覆盖环境变量 THESIS_AGENT_LLM_API_KEY")
    p_run.add_argument("--llm-base-url", default=None,
                       help="覆盖环境变量 THESIS_AGENT_LLM_BASE_URL")
    p_run.add_argument("--llm-model", default=None,
                       help="覆盖环境变量 THESIS_AGENT_LLM_MODEL")
    p_run.add_argument("--no-llm", action="store_true",
                       help="禁用 LLM 诊断（即使配置了凭据）")
    p_run.add_argument("--auto-apply-diagnosis", default="confirm",
                       choices=["yes", "confirm", "no"],
                       help="LLM 诊断自动执行策略：yes=全自动，confirm=暂停等审，"
                            "no=不执行 needs_human 项")
    p_run.add_argument("--resume", default=None,
                       help="从 <stem>_pending.json 恢复运行；与 --input 二选一")
    p_run.set_defaults(func=_cmd_run)

    p_list = sub.add_parser("list", help="列出可用资源")
    list_sub = p_list.add_subparsers(dest="list_cmd", required=True)

    p_list_profiles = list_sub.add_parser("profiles")
    p_list_profiles.set_defaults(func=_cmd_list_profiles)

    p_list_tools = list_sub.add_parser("tools")
    p_list_tools.set_defaults(func=_cmd_list_tools)

    p_list_rules = list_sub.add_parser("rules")
    p_list_rules.add_argument("profile", nargs="?")
    p_list_rules.add_argument("--config", default=None,
                              help="用户 YAML 模板/配置文件；列出其编译规则")
    p_list_rules.set_defaults(func=_cmd_list_rules)

    p_extract = sub.add_parser(
        "extract-template",
        help="?????? Word ???? YAML ??",
    )
    src = p_extract.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", default=None, help="????????")
    src.add_argument("--docx", default=None, help="Word ?? .docx ??")
    p_extract.add_argument("--output", required=True, help="?? YAML ??")
    p_extract.set_defaults(func=_cmd_extract_template)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
