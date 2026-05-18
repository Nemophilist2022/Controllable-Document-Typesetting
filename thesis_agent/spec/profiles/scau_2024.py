"""SCAU 2024 default profile.

Just delegates to ``defaults/scau_2024.yaml`` via the standard ingest
pipeline. New schools should follow the same shape.
"""

from __future__ import annotations

import os

from ...ingest.template_loader import from_yaml
from ..compiler import compile
from ..rule_set import RuleSet

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_YAML_PATH = os.path.join(_PROJECT_ROOT, "defaults", "scau_2024.yaml")


def load() -> RuleSet:
    cfg = from_yaml(_YAML_PATH)
    return compile(cfg, profile="scau_2024", version="1")
