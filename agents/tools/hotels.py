"""
HotelSearchTool (A3.4) — real hotels via the ``booking-com18`` RapidAPI listing.

Two-step flow (verified against the live API):
1. ``/stays/auto-complete?query={city}`` → ``data[0].id`` (an opaque location token)
2. ``/stays/search?locationId=...&checkinDate=...&checkoutDate=...&adults=...``
   → ``data`` list of hotels.
"""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings

from agents.tools import register
from agents.tools.base import Tool, fail, ok
from agents.tools.rapidapi import rapidapi_get

MAX_RESULTS = 5
SEARCH_TIMEOUT = 40  # Booking search is slow


def _normalize(hotel: dict) -> dict:
    gross = (hotel.get("priceBreakdown") or {}).get("grossPrice") or {}
    stars = hotel.get("accuratePropertyClass") or hotel.get("propertyClass") or 0
    score = hotel.get("reviewScore")
    word = hotel.get("reviewScoreWord") or ""
    area = hotel.get("wishlistName") or ""

    bits = []
    if stars:
        bits.append(f"{stars}★")
    if score:
        bits.append(f"{score}/10 {word}".strip())
    if area:
        bits.append(area)

    name = hotel.get("name") or "Hotel"
    value = gross.get("value")
    return {
        "title": name,
        "summary": " · ".join(bits),
        "price": round(value) if value else None,
        "currency": gross.get("currency", ""),
        "link": "https://www.booking.com/searchresults.html?ss=" + quote(name),
    }


class HotelSearchTool(Tool):
    name = "hotels"

    def run(self, params: dict) -> dict:
        city = params.get("city") or params.get("location")
        checkin = params.get("checkin")
        checkout = params.get("checkout")
        adults = params.get("adults") or 1
        if not (city and checkin and checkout):
            return fail("missing params: city/checkin/checkout")

        host = getattr(settings, "RAPIDAPI_HOTELS_HOST", "")

        ac = rapidapi_get(host, "/stays/auto-complete", {"query": city})
        location = (ac or {}).get("data") or []
        if not location:
            return fail("location not found")
        loc_id = location[0].get("id")
        if not loc_id:
            return fail("location id missing")

        data = rapidapi_get(
            host,
            "/stays/search",
            {
                "locationId": loc_id,
                "checkinDate": checkin,
                "checkoutDate": checkout,
                "adults": str(adults),
                "currency_code": "EUR",
            },
            timeout=SEARCH_TIMEOUT,
        )
        hotels = (data or {}).get("data") or []
        if not hotels:
            return fail("no hotels")

        return ok([_normalize(h) for h in hotels[:MAX_RESULTS]])


register(HotelSearchTool())
