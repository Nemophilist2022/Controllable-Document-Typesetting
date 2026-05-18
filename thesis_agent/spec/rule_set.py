"""Rule and RuleSet data contracts (R1.1, R1.6).

A ``Rule`` describes a single format requirement; a ``RuleSet`` bundles
all rules for a profile. These shapes are referenced by every other
agent layer, so changes here must be coordinated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# Allowed values for the ``severity`` field. Kept as a tuple so it works
# both as an iterable and as a runtime check target.
SEVERITY_VALUES: tuple[str, ...] = ("must", "should", "info")
SCOPE_VALUES: tuple[str, ...] = (
    "doc",
    "section",
    "paragraph",
    "run",
    "table",
    "style",
)


@dataclass(frozen=True)
class Rule:
    """A single format rule.

    Attributes:
        id: Stable identifier, e.g. ``"body.font.east_asia"``.
        scope: Where this rule applies. One of :data:`SCOPE_VALUES`.
        locator: How to find the target element(s), e.g.
            ``{"style_name": "Normal"}`` or ``{"heading_level": 1}``.
        predicate: Name of the predicate, e.g. ``equals`` / ``one_of`` /
            ``regex`` / ``range`` / ``exists``. Resolved by the
            evaluator's predicate registry.
        expected: Expected value compared against the document's actual
            value via the predicate.
        severity: ``must`` / ``should`` / ``info``. Validated at init.
        fix_tool: Optional name of a Tool that can repair this rule.
        fix_params_template: Parameter template for the fix Tool. May
            contain ``{expected}``-style placeholders to be filled by
            the diagnoser/planner.
    """

    id: str
    scope: Literal["doc", "section", "paragraph", "run", "table", "style"]
    locator: dict[str, Any]
    predicate: str
    expected: Any
    severity: Literal["must", "should", "info"]
    fix_tool: Optional[str] = None
    fix_params_template: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_VALUES:
            raise ValueError(
                f"invalid severity {self.severity!r}; "
                f"must be one of {SEVERITY_VALUES}"
            )
        if self.scope not in SCOPE_VALUES:
            raise ValueError(
                f"invalid scope {self.scope!r}; "
                f"must be one of {SCOPE_VALUES}"
            )


@dataclass
class RuleSet:
    """A named collection of rules compiled from a template.

    ``metadata`` carries non-rule information from the compiler such as
    ``unknown_keys`` (R1.4) and version provenance.
    """

    profile: str
    version: str
    rules: list[Rule]
    metadata: dict[str, Any] = field(default_factory=dict)
