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

import base64

from django.conf import settings

from agents.tools import register
from agents.tools.base import Tool, fail, ok
from agents.tools.rapidapi import RateLimited, rapidapi_get

MAX_RESULTS = 5
SEARCH_TIMEOUT = 30  # flight search can be slow


def _place_from_data(data: list) -> tuple[str | None, str | None]:
    """Extract (IATA code, Google entity id) from a searchAirport response.

    The IATA code feeds the searchFlights API; the entity id (``/m/...``) feeds
    the Google Flights ``tfs`` deep-link. A city entry (``type: other``) carries
    its entity id at the top level and its airports in ``list``.
    """
    for entry in data:
        # A direct airport hit: code == entity (the IATA code works in both).
        if entry.get("type") == "airport" and entry.get("id"):
            return entry["id"], entry["id"]
        # A city entry: entity id at top level, IATA from the first airport child.
        entity = entry.get("id")
        for child in entry.get("list") or []:
            if child.get("type") == "airport" and child.get("id"):
                return child["id"], (entity or child["id"])
    return None, None


def _resolve_place(host: str, key: str, city: str) -> tuple[str | None, str | None]:
    """City name → (IATA code, entity id) via ``searchAirport``, or (None, None).

    google-flights2 occasionally returns a slow/degraded 200 with no airports,
    so retry once before giving up — a transient blip shouldn't fail the search.
    """
    for _ in range(2):
        data = (rapidapi_get(host, "/api/v1/searchAirport", {"query": city}, key=key) or {}).get("data") or []
        code, entity = _place_from_data(data)
        if code:
            return code, entity
    return None, None


# --- Google Flights deep-link (tfs protobuf) --------------------------------
# A ``?q=...`` text search lands on the Flights homepage; the real results page
# needs the ``tfs`` parameter — a base64url protobuf encoding the route + date
# with Google entity ids. Structure reverse-engineered from a live URL.
def _pb_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _pb_vfield(f: int, n: int) -> bytes:
    return _pb_varint(f << 3) + _pb_varint(n)


def _pb_sfield(f: int, s: str) -> bytes:
    b = s.encode()
    return _pb_varint(f << 3 | 2) + _pb_varint(len(b)) + b


def _pb_mfield(f: int, body: bytes) -> bytes:
    return _pb_varint(f << 3 | 2) + _pb_varint(len(body)) + body


def _flights_link(dep_entity: str, arr_entity: str, date: str) -> str:
    """Build a Google Flights results URL (one-way) for the given route + date."""
    leg = (_pb_sfield(2, date)
           + _pb_mfield(13, _pb_vfield(1, 2) + _pb_sfield(2, dep_entity))
           + _pb_mfield(14, _pb_vfield(1, 3) + _pb_sfield(2, arr_entity)))
    body = (_pb_vfield(1, 28) + _pb_vfield(2, 2) + _pb_mfield(3, leg)
            + _pb_vfield(8, 1) + _pb_vfield(9, 1) + _pb_vfield(14, 1)
            + _pb_mfield(16, _pb_vfield(1, (1 << 64) - 1)) + _pb_vfield(19, 2))
    tfs = base64.urlsafe_b64encode(body).decode().rstrip("=")
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&hl=en&gl=RO"


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


def _normalize(itin: dict, currency: str, link: str) -> dict:
    legs = itin.get("flights") or []
    airlines = list(dict.fromkeys(f.get("airline") for f in legs if f.get("airline")))
    code_dep = (legs[0].get("departure_airport") or {}).get("airport_code") if legs else ""
    code_arr = (legs[-1].get("arrival_airport") or {}).get("airport_code") if legs else ""
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

    return {
        "title": " / ".join(airlines) or "Zbor",
        "summary": " · ".join(bits),
        "price": itin.get("price"),
        "currency": currency,
        "link": link,
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

        try:
            dep_code, dep_entity = _resolve_place(host, key, origin)
            arr_code, arr_entity = _resolve_place(host, key, dest)
            if not (dep_code and arr_code):
                return fail("airport not found")

            currency = "EUR"
            query = {
                "departure_id": dep_code,
                "arrival_id": arr_code,
                "outbound_date": date,
                "travel_class": "ECONOMY",
                "adults": str(adults),
                "currency": currency,
                "search_type": "best",
            }
            if return_date:
                query["return_date"] = return_date

            # searchFlights occasionally returns an empty 200, so retry once.
            flights = []
            for _ in range(2):
                data = rapidapi_get(host, "/api/v1/searchFlights", query, key=key, timeout=SEARCH_TIMEOUT)
                itineraries = ((data or {}).get("data") or {}).get("itineraries") or {}
                flights = (itineraries.get("topFlights") or []) + (itineraries.get("otherFlights") or [])
                if flights:
                    break
        except RateLimited:
            return fail("rate_limited")
        if not flights:
            return fail("no flights")

        # One results-page link for this route+date (Google Flights tfs deep-link).
        link = _flights_link(dep_entity, arr_entity, date)
        return ok([_normalize(f, currency, link) for f in flights[:MAX_RESULTS]])


register(FlightSearchTool())
