"""Diagnoser layer.

LLM-driven root-cause analysis and fix planning. Output is always a
structured ``Diagnosis(fix_plan=[ToolCall(...)])`` — the LLM is never
allowed to write OOXML directly (R5.4).
"""
