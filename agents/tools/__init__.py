"""
Tool registry (A3.4) — small factory mapping a tool name to a Tool instance.

Concrete tools register themselves here on import. The Concierge looks tools up
by the name the planner returns ("flights" / "hotels").
"""

from __future__ import annotations

from agents.tools.base import Tool

_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def available() -> list[str]:
    return list(_REGISTRY)


# Concrete tools register themselves on import. Each is imported independently
# (and defensively) so a missing/broken one never blocks the others.
from importlib import import_module

for _mod in ("flights", "hotels", "directions"):
    try:
        import_module(f"agents.tools.{_mod}")
    except Exception:  # pragma: no cover - optional/not-yet-built tool
        pass
