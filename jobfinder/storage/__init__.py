"""Storage package — swappable backends for JSON files or Supabase Postgres."""

from __future__ import annotations

import os

from jobfinder.storage.backend import StorageBackend


def get_storage_backend(user_id: str | None = None) -> StorageBackend:
    """Return the appropriate storage backend.

    - If ``SUPABASE_URL`` is set **and** a ``user_id`` is provided, returns a
      :class:`SupabaseStorageBackend` backed by Postgres.
    - Otherwise returns a :class:`JsonStorageBackend` using local JSON files.
    """
    if os.environ.get("SUPABASE_URL") and user_id:
        from jobfinder.storage.supabase_backend import SupabaseStorageBackend

        return SupabaseStorageBackend(user_id=user_id)

    from jobfinder.config import load_config
    from jobfinder.storage.store import JsonStorageBackend

    return JsonStorageBackend(load_config().data_dir)
