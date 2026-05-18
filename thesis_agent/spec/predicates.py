"""Predicate registry used by the rule compiler and the evaluator runner.

Each predicate is a callable ``(actual, expected) -> bool``. New
predicates are registered by name; the compiler refuses unknown names so
typos in YAML fail fast.
"""

from __future__ import annotations

import re
from typing import Any, Callable


class UnknownPredicateError(Exception):
    """Raised when a rule references a predicate that isn't registered."""


# ---------------------------------------------------------------------------
# Predicate implementations
# ---------------------------------------------------------------------------

def _equals(actual: Any, expected: Any) -> bool:
    return actual == expected


def _one_of(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, (list, tuple, set)):
        raise ValueError(
            "one_of expects a list/tuple/set of allowed values; "
            f"got {type(expected).__name__}"
        )
    return actual in expected


def _regex(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, str):
        raise ValueError("regex expects a pattern string")
    if actual is None:
        return False
    return re.search(expected, str(actual)) is not None


def _range(actual: Any, expected: Any) -> bool:
    if not (isinstance(expected, (list, tuple)) and len(expected) == 2):
        raise ValueError("range expects [low, high]")
    low, high = expected
    return low <= actual <= high


def _exists(actual: Any, expected: Any) -> bool:
    """``expected=True`` → target must be present (non-None).
    ``expected=False`` → target must be absent (None)."""
    present = actual is not None
    return present if expected else not present


_REGISTRY: dict[str, Callable[[Any, Any], bool]] = {
    "equals": _equals,
    "one_of": _one_of,
    "regex": _regex,
    "range": _range,
    "exists": _exists,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(name: str, actual: Any, expected: Any) -> bool:
    try:
        fn = _REGISTRY[name]
    except KeyError as exc:
        raise UnknownPredicateError(name) from exc
    return fn(actual, expected)


def known_predicates() -> tuple[str, ...]:
    return tuple(_REGISTRY)
