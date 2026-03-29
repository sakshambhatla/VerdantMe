from __future__ import annotations

import time

import httpx

DEFAULT_HEADERS = {
    "User-Agent": "JobFinder/5.5.0 (career-search-tool)",
    "Accept": "application/json",
}

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds


def head_ok(url: str, timeout: int = 5) -> bool:
    """Return True if url responds with a non-error status (2xx or 3xx).
    Falls back to GET if the server returns 405 on HEAD."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.head(url)
            if r.status_code == 405:  # HEAD not allowed → try GET
                r = client.get(url)
            return r.status_code < 400
    except Exception:
        return False


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
