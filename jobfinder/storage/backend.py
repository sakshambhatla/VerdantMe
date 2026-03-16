from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Abstract storage interface.

    Implemented by ``JsonStorageBackend`` (local JSON files) and
    ``SupabaseStorageBackend`` (Supabase Postgres).  The *collection*
    parameter corresponds to a JSON filename in the local backend
    (e.g. ``"resumes.json"``) and to a table/row in the Supabase backend.
    """

    def read(self, collection: str) -> dict | list | None:
        """Read an entire collection. Returns ``None`` if not found."""
        ...

    def write(self, collection: str, data: dict | list) -> None:
        """Atomically write/replace an entire collection."""
        ...

    def exists(self, collection: str) -> bool:
        """Check whether a collection exists."""
        ...

    def delete(self, collection: str) -> None:
        """Delete a collection. No-op if it does not exist."""
        ...
