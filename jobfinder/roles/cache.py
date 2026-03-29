from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jobfinder.storage.backend import StorageBackend
from jobfinder.storage.schemas import DiscoveredRole, RolesCacheEntry

CACHE_FILENAME = "roles_cache.json"
CACHE_TTL_DAYS = 2

# Per-ats_type TTL overrides (days).  TheirStack results cost credits to
# refresh, so we cache them longer than free ATS results.
_TTL_OVERRIDES: dict[str, int] = {
    "theirstack": 3,
}


class RolesCache:
    """Per-company, per-ATS cache for raw role fetch results.

    Cache key = ``company_name.lower() + "|" + ats_type``.
    TTL is 2 days.  Expired entries stay in the file; ``get()`` ignores them.
    ``put()`` always writes after a fresh fetch so the cache is ready for
    future runs.
    """

    def __init__(self, store: StorageBackend) -> None:
        self._store = store
        data = store.read(CACHE_FILENAME) or {"version": 1, "entries": {}}
        self._entries: dict[str, dict] = data.get("entries", {})

    def _key(self, company_name: str, ats_type: str) -> str:
        return f"{company_name.lower()}|{ats_type}"

    def get(self, company_name: str, ats_type: str) -> list[DiscoveredRole] | None:
        """Return cached roles if present and within TTL, else None."""
        entry = self._entries.get(self._key(company_name, ats_type))
        if entry is None:
            return None

        cached_at = datetime.fromisoformat(entry["cached_at"])
        ttl = _TTL_OVERRIDES.get(ats_type, CACHE_TTL_DAYS)
        if datetime.now(timezone.utc) - cached_at > timedelta(days=ttl):
            return None  # expired

        return [DiscoveredRole.model_validate(r) for r in entry["roles"]]

    def put(self, company_name: str, ats_type: str, roles: list[DiscoveredRole]) -> None:
        """Write (or overwrite) a cache entry.  Called after every fresh fetch."""
        key = self._key(company_name, ats_type)
        entry = RolesCacheEntry(
            company_name=company_name,
            ats_type=ats_type,
            cached_at=datetime.now(timezone.utc).isoformat(),
            roles=roles,
        )
        self._entries[key] = entry.model_dump()
        self._store.write(CACHE_FILENAME, {"version": 1, "entries": self._entries})

    def age_hours(self, company_name: str, ats_type: str) -> float | None:
        """Return hours since cached, or None if no entry exists."""
        entry = self._entries.get(self._key(company_name, ats_type))
        if entry is None:
            return None
        cached_at = datetime.fromisoformat(entry["cached_at"])
        return (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
