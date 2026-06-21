"""
HotelSearchTool (A3.4) — real hotels via the ``booking-com18`` RapidAPI listing.

Flow (verified against the live API):
1. ``/stays/auto-complete?query={city}`` → ``data[0].id`` (an opaque location token)
2. ``/stays/search?locationId=...&checkinDate=...&checkoutDate=...&adults=...``
   → ``data`` list of hotels.
3. ``/stays/detail?hotelId=...`` per shown hotel → the **real** Booking page URL
   (``/hotel/<cc>/<slug>.html``). Fetched in parallel; falls back to a dated
   search link if unavailable, so a link always works (never a 404).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

from django.conf import settings

from agents.tools import register
from agents.tools.base import Tool, fail, ok
from agents.tools.rapidapi import RateLimited, rapidapi_get

MAX_RESULTS = 5
SEARCH_TIMEOUT = 40   # Booking search is slow
DETAIL_TIMEOUT = 12

_HOTEL_URL_RE = re.compile(r'https://www\.booking\.com/hotel/[^"\\ ]+\.html')


def _search_link(name: str, checkin: str, checkout: str, adults) -> str:
    """Robust fallback: a dated Booking search that always resolves to the hotel."""
    return "https://www.booking.com/searchresults.html?" + urlencode({
        "ss": name,
        "checkin": checkin,
        "checkout": checkout,
        "group_adults": adults,
    })


def _real_url(host: str, hotel_id, checkin: str, checkout: str, adults) -> str | None:
    """The hotel's real Booking page URL via /stays/detail, or None on failure.

    A 429 here is non-fatal (the search already succeeded) — return None so the
    caller falls back to the dated search link.
    """
    if not hotel_id:
        return None
    try:
        data = rapidapi_get(
            host, "/stays/detail",
            {"hotelId": str(hotel_id), "checkinDate": checkin,
             "checkoutDate": checkout, "adults": str(adults), "currency_code": "EUR"},
            timeout=DETAIL_TIMEOUT,
        )
    except RateLimited:
        return None
    if not data:
        return None
    match = _HOTEL_URL_RE.search(json.dumps(data))
    return match.group(0) if match else None


def _normalize(hotel: dict, link: str) -> dict:
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

    value = gross.get("value")
    return {
        "title": hotel.get("name") or "Hotel",
        "summary": " · ".join(bits),
        "price": round(value) if value else None,
        "currency": gross.get("currency", ""),
        "link": link,
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

        try:
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
        except RateLimited:
            return fail("rate_limited")
        hotels = (data or {}).get("data") or []
        if not hotels:
            return fail("no hotels")
        hotels = hotels[:MAX_RESULTS]

        # Fetch each hotel's real Booking page URL in parallel (I/O-bound), with a
        # dated-search fallback so every result still gets a working link.
        def link_for(h):
            return (_real_url(host, h.get("id"), checkin, checkout, adults)
                    or _search_link(h.get("name") or "", checkin, checkout, adults))

        with ThreadPoolExecutor(max_workers=len(hotels)) as pool:
            links = list(pool.map(link_for, hotels))

        return ok([_normalize(h, link) for h, link in zip(hotels, links)])


register(HotelSearchTool())
