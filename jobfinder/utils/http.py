from __future__ import annotations

import time

import httpx

DEFAULT_HEADERS = {
    "User-Agent": "JobFinder/0.1.0 (career-search-tool)",
    "Accept": "application/json",
}

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds


def get_json(
    url: str, timeout: int = 30, params: dict | None = None
) -> dict | list:
    """GET a URL and return parsed JSON. Retries on 5xx/network errors."""
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_error = exc
            # Only retry on 5xx or network errors
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE ** attempt)

    raise last_error  # type: ignore[misc]
