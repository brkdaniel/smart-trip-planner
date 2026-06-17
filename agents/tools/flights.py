"""
FlightSearchTool (A3.4) — real flights via the ``google-flights2`` RapidAPI listing.

Two-step flow (verified against the live API):
1. ``/api/v1/searchAirport?query={city}`` → resolve a city name to its main IATA
   code. The first match is usually a city entry (``type: "other"``) whose nested
   ``list`` holds the actual airports (e.g. "Roma" → "FCO").
2. ``/api/v1/searchFlights?departure_id=...&arrival_id=...&outbound_date=...``
   (plus ``return_date`` for round trips) → ``data.itineraries.topFlights`` /
   ``otherFlights``.

google-flights2 is a separate subscription from the hotels listing, so it uses
its own key (``RAPIDAPI_FLIGHTS_KEY``).
"""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings

from agents.tools import register
from agents.tools.base import Tool, fail, ok
from agents.tools.rapidapi import rapidapi_get

MAX_RESULTS = 5
SEARCH_TIMEOUT = 30  # flight search can be slow


def _airport_from_data(data: list) -> str | None:
    for entry in data:
        # A direct airport hit.
        if entry.get("type") == "airport" and entry.get("id"):
            return entry["id"]
        # A city entry carries its airports in `list`; take the first airport.
        for child in entry.get("list") or []:
            if child.get("type") == "airport" and child.get("id"):
                return child["id"]
    return None


def _resolve_airport(host: str, key: str, city: str) -> str | None:
    """City name → IATA airport code via ``searchAirport``, or ``None``.

    google-flights2 occasionally returns a slow/degraded 200 with no airports,
    so retry once before giving up — a transient blip shouldn't fail the search.
    """
    for _ in range(2):
        data = (rapidapi_get(host, "/api/v1/searchAirport", {"query": city}, key=key) or {}).get("data") or []
        code = _airport_from_data(data)
        if code:
            return code
    return None


def _stops_label(layovers: list, n_legs: int) -> str:
    """Romanian direct/stops label with layover cities.

    The API's ``stops`` field is unreliable (returns 0 even for multi-leg
    flights), so we derive everything from the ``layovers`` array, falling back
    to the segment count.
    """
    n_stops = len(layovers) if layovers else max(n_legs - 1, 0)
    if n_stops == 0:
        return "DIRECT"

    spots = []
    for lo in layovers:
        city = lo.get("city") or lo.get("airport_name") or lo.get("airport_code") or "?"
        code = lo.get("airport_code")
        label = f"{city} ({code})" if code and code != city else str(city)
        dur = lo.get("duration_label")
        if dur:
            label += f", {dur}"
        spots.append(label)

    word = "escală" if n_stops == 1 else "escale"
    if spots:
        return f"CU ESCALĂ — {n_stops} {word}: " + "; ".join(spots)
    return f"CU ESCALĂ — {n_stops} {word}"


def _normalize(itin: dict, currency: str, dep: str, arr: str, date: str) -> dict:
    legs = itin.get("flights") or []
    airlines = list(dict.fromkeys(f.get("airline") for f in legs if f.get("airline")))
    code_dep = (legs[0].get("departure_airport") or {}).get("airport_code") if legs else dep
    code_arr = (legs[-1].get("arrival_airport") or {}).get("airport_code") if legs else arr
    duration = (itin.get("duration") or {}).get("text") or ""

    bits = []
    if code_dep and code_arr:
        bits.append(f"{code_dep}→{code_arr}")
    dep_t, arr_t = itin.get("departure_time"), itin.get("arrival_time")
    if dep_t and arr_t:
        bits.append(f"{dep_t} → {arr_t}")
    bits.append(_stops_label(itin.get("layovers") or [], len(legs)))
    if duration:
        bits.append(duration)

    route = f"Flights from {code_dep or dep} to {code_arr or arr} on {date}"
    return {
        "title": " / ".join(airlines) or "Zbor",
        "summary": " · ".join(bits),
        "price": itin.get("price"),
        "currency": currency,
        "link": "https://www.google.com/travel/flights?q=" + quote(route),
    }


class FlightSearchTool(Tool):
    name = "flights"

    def run(self, params: dict) -> dict:
        origin = params.get("from") or params.get("origin")
        dest = params.get("to") or params.get("destination")
        date = params.get("date") or params.get("outbound_date")
        return_date = params.get("return_date")
        adults = params.get("adults") or 1
        if not (origin and dest and date):
            return fail("missing params: from/to/date")

        host = getattr(settings, "RAPIDAPI_FLIGHTS_HOST", "")
        key = getattr(settings, "RAPIDAPI_FLIGHTS_KEY", "")

        dep = _resolve_airport(host, key, origin)
        arr = _resolve_airport(host, key, dest)
        if not (dep and arr):
            return fail("airport not found")

        currency = "EUR"
        query = {
            "departure_id": dep,
            "arrival_id": arr,
            "outbound_date": date,
            "travel_class": "ECONOMY",
            "adults": str(adults),
            "currency": currency,
            "search_type": "best",
        }
        if return_date:
            query["return_date"] = return_date

        data = rapidapi_get(host, "/api/v1/searchFlights", query, key=key, timeout=SEARCH_TIMEOUT)
        itineraries = ((data or {}).get("data") or {}).get("itineraries") or {}
        flights = (itineraries.get("topFlights") or []) + (itineraries.get("otherFlights") or [])
        if not flights:
            return fail("no flights")

        return ok([_normalize(f, currency, dep, arr, date) for f in flights[:MAX_RESULTS]])


register(FlightSearchTool())
