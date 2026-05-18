# Agent Check Coverage v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert thesis-agent check coverage from experimental/skip-heavy reporting into a practical 41-rule evaluator where every skip is explicitly classified as applicable, unmeasurable, or unsupported.

**Architecture:** Keep the existing RuleSet and predicate dispatcher. Add metadata reason codes to CheckResult outputs from evaluator checks, add a focused coverage guard test that forbids "unimplemented" skip reasons for `scau_2024`, and update README to accurately describe implemented work and limits.

**Tech Stack:** Python 3, unittest, python-docx, existing thesis_agent evaluator modules.

---

### Task 1: Coverage guard test

**Files:**
- Create: `tests/agent/test_check_coverage_guard.py`

- [ ] Write a test that builds representative pass/NA docs, runs all 41 `scau_2024` rules, and fails when any result has an unclassified skip or unsupported handler reason.
- [ ] Run the test and confirm it fails on current skip metadata absence.

### Task 2: Classify skip reasons and strengthen checks

**Files:**
- Modify: `thesis_agent/evaluators/checks/*.py`

- [ ] Add metadata reason codes to every skip path in currently used checks.
- [ ] Convert "unsupported handler" fallthroughs to error metadata where reachable.
- [ ] Keep legitimate N/A skips for missing optional document objects.
- [ ] Run focused tests until green.

### Task 3: README current-state documentation

**Files:**
- Modify: `README.md`

- [ ] Replace v0.1 limitation language with v0.2 practical coverage status.
- [ ] Detail implemented agent loop: compile rules, evaluate, fix, re-evaluate, diagnose, HITL, reports.
- [ ] Explain remaining skip semantics and reliable/unreliable areas.

### Task 4: Verification and merge

- [ ] Run focused tests.
- [ ] Run full unittest suite.
- [ ] Fast-forward/merge branch back to main workspace if clean.
