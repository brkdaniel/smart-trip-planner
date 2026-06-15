"""
Tool abstraction (A3.4).

Each external capability the Concierge can use (flight search, hotel search) is a
``Tool`` with a uniform interface — a Command/Strategy. The planner picks a tool
by name; the Concierge formats whatever ``results`` come back.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


def ok(results: list[dict]) -> dict:
    return {"ok": True, "results": results, "error": None}


def fail(error: str) -> dict:
    return {"ok": False, "results": [], "error": error}


class Tool(ABC):
    """A named external capability returning a normalized result envelope."""

    name: str = ""

    @abstractmethod
    def run(self, params: dict) -> dict:
        """Execute the tool. Returns ``{"ok": bool, "results": [...], "error": str|None}``.

        Implementations must never raise — wrap failures with :func:`fail`.
        """
        raise NotImplementedError
