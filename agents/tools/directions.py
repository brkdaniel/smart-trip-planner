"""
DirectionsTool — how to get from A to B (airport → hotel, anywhere → anywhere).

Two layers, so it is useful immediately and gets richer once the key is added:

1. **Always**: builds a deterministic Google Maps directions deep-link
   (``/maps/dir/?...&travelmode=transit``). Opening it shows the real, live route
   (public transport / traffic) in Google Maps — no API key, no cost.
2. **When ``GOOGLE_MAPS_API_KEY`` is set**: also calls the official Google Maps
   **Directions API** and narrates the route *in chat* — duration (with live
   traffic for driving / live schedules for transit), distance and the main steps
   (transit lines, transfers).

Google geocodes free-text places ("Hotel Schulz", "Aeroportul Otopeni", "centru")
itself, so no separate geocoding step is needed.

To enable narration: set ``GOOGLE_MAPS_API_KEY`` in ``.env`` (a Maps Platform key
with the *Directions API* enabled and billing on). Nothing else to change.
"""

from __future__ import annotations

import html
import logging
import re
import time
from urllib.parse import urlencode

import requests
from django.conf import settings

from agents.tools import register
from agents.tools.base import Tool, fail, ok

logger = logging.getLogger("agents.tools")

# Google Maps travel modes (what the deep-link + the Directions API accept).
TRAVEL_MODES = {"transit", "driving", "walking", "bicycling"}
DEFAULT_MODE = "transit"  # airport → hotel is usually public transport
DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
SEARCH_TIMEOUT = 15
MAX_STEPS = 8

_TAG_RE = re.compile(r"<[^>]+>")

_MODE_RO = {
    "transit": "transport public",
    "driving": "cu mașina",
    "walking": "pe jos",
    "bicycling": "cu bicicleta",
}


def _maps_link(origin: str, destination: str, mode: str) -> str:
    """A Google Maps directions deep-link (live route when opened)."""
    return "https://www.google.com/maps/dir/?" + urlencode({
        "api": 1,
        "origin": origin,
        "destination": destination,
        "travelmode": mode,
    })


def _clean(text: str) -> str:
    """Strip the HTML tags/entities that Google step instructions carry."""
    return html.unescape(_TAG_RE.sub(" ", text or "")).strip()


def _directions_api(origin: str, destination: str, mode: str, key: str) -> dict | None:
    """Call the Google Maps Directions API. Returns the JSON on success, else None.

    Never raises — logs and returns None on any error/non-OK status so the tool
    degrades to the link-only answer.
    """
    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "language": "ro",
        "units": "metric",
        "key": key,
    }
    # Real-time: transit needs a departure time; driving uses it for live traffic.
    if mode in ("transit", "driving"):
        params["departure_time"] = "now"

    started = time.perf_counter()
    try:
        resp = requests.get(DIRECTIONS_URL, params=params, timeout=SEARCH_TIMEOUT)
        latency_ms = int((time.perf_counter() - started) * 1000)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status != "OK":
            logger.warning(
                "tool=directions mode=%s latency_ms=%d ok=0 status=%s error=%s",
                mode, latency_ms, status, data.get("error_message", "-"),
            )
            return None
        logger.info("tool=directions mode=%s latency_ms=%d ok=1", mode, latency_ms)
        return data
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("tool=directions mode=%s latency_ms=%d ok=0 error=%s", mode, latency_ms, exc)
        return None


def _summarize(data: dict) -> str:
    """Render a Google Directions response into a short text route, or ''.

    Defensive: any missing/odd field just yields a shorter summary (never raises).
    """
    routes = (data or {}).get("routes") or []
    if not routes:
        return ""
    legs = (routes[0] or {}).get("legs") or []
    if not legs:
        return ""
    leg = legs[0] or {}

    head_bits = []
    # Prefer live, traffic-aware duration when present (driving mode).
    dur = (leg.get("duration_in_traffic") or leg.get("duration") or {}).get("text")
    dist = (leg.get("distance") or {}).get("text")
    if dur:
        head_bits.append(f"durată ~{dur}")
    if dist:
        head_bits.append(dist)

    steps_out = []
    for step in (leg.get("steps") or [])[:MAX_STEPS]:
        transit = step.get("transit_details") or {}
        line = transit.get("line") or {}
        line_name = line.get("short_name") or line.get("name")
        if line_name:
            dep = (transit.get("departure_stop") or {}).get("name") or ""
            arr = (transit.get("arrival_stop") or {}).get("name") or ""
            piece = str(line_name)
            if dep and arr:
                piece += f" ({dep} → {arr})"
            steps_out.append(piece)
        else:
            instr = _clean(step.get("html_instructions") or step.get("instruction") or "")
            if instr:
                steps_out.append(instr)

    parts = []
    if head_bits:
        parts.append(" · ".join(head_bits))
    if steps_out:
        parts.append(" → ".join(steps_out))
    return " | ".join(parts)


class DirectionsTool(Tool):
    name = "directions"

    def run(self, params: dict) -> dict:
        origin = params.get("from") or params.get("origin")
        destination = params.get("to") or params.get("destination")
        mode = (params.get("mode") or DEFAULT_MODE).strip().lower()
        if mode not in TRAVEL_MODES:
            mode = DEFAULT_MODE
        if not (origin and destination):
            return fail("missing params: from/to")

        # Layer 1 — always available: a live Google Maps link.
        result = {
            "title": f"{origin} → {destination} ({_MODE_RO[mode]})",
            "summary": "",
            "link": _maps_link(origin, destination, mode),
        }

        # Layer 2 — narrate in chat if the Directions API key is configured.
        key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
        if key:
            summary = _summarize(_directions_api(origin, destination, mode, key) or {})
            if summary:
                result["summary"] = summary

        return ok([result])


register(DirectionsTool())
