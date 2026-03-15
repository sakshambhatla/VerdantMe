from __future__ import annotations

import math
import time
from collections import deque


class RateLimiter:
    """Sliding-window rate limiter — shared across all LLM callers in the process."""

    def __init__(self, rpm: int) -> None:
        self.rpm = rpm
        self._timestamps: deque[float] = deque()

    def wait(self) -> None:
        """Block until a request slot is available within the RPM limit."""
        if self.rpm <= 0:
            return

        window = 60.0
        now = time.monotonic()

        # Evict timestamps outside the rolling window
        while self._timestamps and now - self._timestamps[0] >= window:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.rpm:
            wait_secs = (self._timestamps[0] + window) - now
            if wait_secs > 0:
                from jobfinder.utils.log_stream import log
                log(
                    f"  [yellow]Rate limit ({self.rpm} RPM): "
                    f"waiting {math.ceil(wait_secs)}s...[/yellow]",
                    level="warning",
                )
                time.sleep(wait_secs)
            # Evict again after sleeping
            now = time.monotonic()
            while self._timestamps and now - self._timestamps[0] >= window:
                self._timestamps.popleft()

        self._timestamps.append(time.monotonic())


_limiter: RateLimiter | None = None


def get_limiter(rpm: int) -> RateLimiter:
    """Return the shared process-level rate limiter, creating or updating it as needed."""
    global _limiter
    if _limiter is None or _limiter.rpm != rpm:
        _limiter = RateLimiter(rpm)
    return _limiter
