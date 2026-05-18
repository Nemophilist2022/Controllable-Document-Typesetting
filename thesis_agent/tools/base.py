"""Tool protocol, ToolResult, and ToolContext (R3.1, R3.2).

Every Tool is a thin wrapper around an existing ``thesis_formatter/*``
operator. The protocol is enforced both via :class:`Tool` (a structural
``typing.Protocol``) and a runtime helper :func:`is_tool` that the tool
registry uses on auto-discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

# The five static attributes a Tool implementation must expose.
# Keeping this in one place lets the registry validate auto-loaded
# modules without duplicating the list.
REQUIRED_TOOL_ATTRS: tuple[str, ...] = (
    "name",
    "description",
    "input_schema",
    "requires",
    "idempotent",
)


@dataclass
class ToolResult:
    """Uniform return type for every Tool invocation.

    ``ok=False`` does not raise; it always carries a ``message``. The
    ``rollback_token`` is supplied by the snapshot manager and lets the
    orchestrator step-roll-back per R6.4.
    """

    ok: bool
    message: str = ""
    changed_paragraphs: list[dict[str, Any]] = field(default_factory=list)
    changed_styles: list[str] = field(default_factory=list)
    changed_sections: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rollback_token: Optional[str] = None


@dataclass
class ToolContext:
    """What every Tool gets at run time.

    The orchestrator constructs this and passes it in. Tools must not
    fabricate a ``ToolContext`` themselves; that would defeat snapshot
    accounting.
    """

    trace: Any                   # delivery.trace.Trace; loosely typed to avoid circular imports
    snapshot_mgr: Any            # orchestrator.snapshot.SnapshotManager
    config: dict[str, Any]
    runtime: dict[str, Any]


@runtime_checkable
class Tool(Protocol):
    """Structural protocol every Tool must satisfy."""

    name: str
    description: str
    input_schema: dict[str, Any]
    requires: list[str]
    idempotent: bool

    def run(self, doc: Any, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ...


def is_tool(obj: Any) -> bool:
    """Return True if *obj* exposes all five static attributes and ``run``.

    ``isinstance(obj, Tool)`` would also work via :func:`runtime_checkable`,
    but it accepts any class with a ``run`` method regardless of the
    static attributes. We want the stricter contract for the registry.
    """
    if not callable(getattr(obj, "run", None)):
        return False
    for attr in REQUIRED_TOOL_ATTRS:
        if not hasattr(obj, attr):
            return False
    return True
