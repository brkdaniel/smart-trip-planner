"""
Thin RapidAPI HTTP helper (A3.4).

One place that knows how to authenticate against RapidAPI and make a GET request.
Never raises to callers — returns the parsed JSON on success or ``None`` on any
failure — and logs every call (host, latency, ok/fail) reusing the A3.3 logging
setup (see LOGGING in settings.py).
"""

from __future__ import annotations

import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger("agents.tools")

DEFAULT_TIMEOUT = 12  # seconds


class RateLimited(Exception):
    """Raised when a RapidAPI listing returns HTTP 429 (quota/rate exceeded).

    Distinct from a generic failure (which returns ``None``) so callers can tell
    the user the search is temporarily over its limit instead of pretending there
    are no results.
    """


def rapidapi_get(
    host: str,
    path: str,
    params: dict,
    timeout: int = DEFAULT_TIMEOUT,
    key: str | None = None,
) -> dict | None:
    """GET ``https://{host}{path}?{params}`` with RapidAPI auth headers.

    Returns the decoded JSON dict/list on HTTP 200, else ``None``. Logs the call.
    Some endpoints (hotel search) are slow — pass a larger ``timeout``.

    ``key`` overrides the default ``RAPIDAPI_KEY`` for listings on a separate
    subscription (e.g. flights via google-flights2).
    """
    if key is None:
        key = getattr(settings, "RAPIDAPI_KEY", "")
    if not key or not host or not path:
        logger.warning("tool=rapidapi host=%s ok=0 error=not-configured", host or "-")
        return None

    url = f"https://{host}{path}"
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": host}
    started = time.perf_counter()
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code == 429:
            logger.warning(
                "tool=rapidapi host=%s path=%s latency_ms=%d ok=0 error=429-rate-limited",
                host, path, latency_ms,
            )
            raise RateLimited(host)
        response.raise_for_status()
        logger.info("tool=rapidapi host=%s path=%s latency_ms=%d ok=1", host, path, latency_ms)
        return response.json()
    except RateLimited:
        raise  # propagate so callers can surface a clear "over limit" message
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "tool=rapidapi host=%s path=%s latency_ms=%d ok=0 error=%s",
            host, path, latency_ms, exc,
        )
        return None
