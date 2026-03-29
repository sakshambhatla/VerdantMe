"""Credit tracker for the TheirStack API free tier.

Persists used credits to ``theirstack_credits.json`` and auto-resets
after 30 days (TheirStack free tier resets monthly).

In Supabase (managed) mode, credits are stored in the ``theirstack_credits``
table (JSONB blob, one row per user with RLS).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jobfinder.storage.backend import StorageBackend

CREDITS_FILENAME = "theirstack_credits.json"
RESET_DAYS = 30


class CreditTracker:
    """Track TheirStack API credit usage against a budget."""

    def __init__(self, store: StorageBackend, budget: int = 200) -> None:
        self._store = store
        self._budget = budget

        data = store.read(CREDITS_FILENAME)
        if data and not self._is_expired(data):
            self._used: int = data.get("used", 0)
            self._reset_at: str = data["reset_at"]
        else:
            # Fresh start or expired → reset
            self._used = 0
            self._reset_at = (
                datetime.now(timezone.utc) + timedelta(days=RESET_DAYS)
            ).isoformat()
            self._persist()

    def _is_expired(self, data: dict) -> bool:
        reset_at = data.get("reset_at")
        if not reset_at:
            return True
        try:
            return datetime.now(timezone.utc) >= datetime.fromisoformat(reset_at)
        except (ValueError, TypeError):
            return True

    def _persist(self) -> None:
        self._store.write(
            CREDITS_FILENAME,
            {"used": self._used, "reset_at": self._reset_at, "budget": self._budget},
        )

    def can_afford(self, n: int) -> bool:
        """Return True if spending ``n`` credits stays within budget."""
        return self._used + n <= self._budget

    def spend(self, n: int) -> None:
        """Record ``n`` credits spent and persist."""
        self._used += n
        self._persist()

    @property
    def remaining(self) -> int:
        return max(0, self._budget - self._used)

    @property
    def used(self) -> int:
        return self._used
