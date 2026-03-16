from __future__ import annotations

from datetime import datetime, timezone

from jobfinder.storage.backend import StorageBackend
from jobfinder.storage.schemas import DiscoveredCompany

REGISTRY_FILENAME = "company_registry.json"


def load_or_bootstrap_registry(store: StorageBackend) -> list[dict]:
    """Return registry entries, seeding from companies.json on first run."""
    if store.exists(REGISTRY_FILENAME):
        return (store.read(REGISTRY_FILENAME) or {}).get("companies", [])
    # First-run bootstrap: seed from the last discover-companies result
    data = store.read("companies.json") or {}
    entries = [
        {
            "name": c["name"],
            "ats_type": c.get("ats_type", "unknown"),
            "ats_board_token": c.get("ats_board_token"),
            "career_page_url": c.get("career_page_url", ""),
        }
        for c in data.get("companies", [])
    ]
    store.write(
        REGISTRY_FILENAME,
        {"updated_at": datetime.now(timezone.utc).isoformat(), "companies": entries},
    )
    return entries


def update_registry_searchable(
    store: StorageBackend, company_name: str, searchable: bool
) -> None:
    """Update the searchable field for a specific company after a career page fetch attempt."""
    data = store.read(REGISTRY_FILENAME) or {"companies": []}
    for entry in data.get("companies", []):
        if entry["name"].lower() == company_name.lower():
            entry["searchable"] = searchable
            break
    store.write(
        REGISTRY_FILENAME,
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "companies": data.get("companies", []),
        },
    )


def upsert_registry(store: StorageBackend, new_companies: list[DiscoveredCompany]) -> None:
    """Merge *new_companies* into the registry (new entry wins; registry never shrinks)."""
    existing = (store.read(REGISTRY_FILENAME) or {}).get("companies", [])
    seen: dict[str, dict] = {e["name"].lower(): e for e in existing}
    for c in new_companies:
        key = c.name.lower()
        existing_searchable = seen.get(key, {}).get("searchable")  # preserve if already set
        seen[key] = {
            "name": c.name,
            "ats_type": c.ats_type,
            "ats_board_token": c.ats_board_token,
            "career_page_url": c.career_page_url,
            "searchable": existing_searchable,  # None for new companies
        }
    store.write(
        REGISTRY_FILENAME,
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "companies": list(seen.values()),
        },
    )
