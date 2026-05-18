"""Tools layer.

Each Tool is a thin, idempotent, snapshot-aware wrapper around an existing
``thesis_formatter/*`` operator. Tools must not call other Tools — any
composition is the orchestrator's job.
"""
