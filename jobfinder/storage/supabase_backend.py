"""Supabase storage backend — maps collection filenames to Postgres tables.

Used when ``SUPABASE_URL`` is set.  Each user's data is isolated via RLS
(the Supabase client is initialised with the user's JWT).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def _supabase_client():
    """Lazy import + client creation so the dependency is optional."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SECRET_KEY"]
    return create_client(url, key)


class SupabaseStorageBackend:
    """Implements the :class:`StorageBackend` protocol using Supabase Postgres.

    Each ``read``/``write`` call maps a *collection* filename (e.g.
    ``"roles.json"``) to the appropriate table operations.

    Collections that map to structured tables:
      - ``resumes.json``           → ``resumes``
      - ``companies.json``         → ``companies``
      - ``roles.json``             → ``roles`` (is_filtered = true)
      - ``roles_unfiltered.json``  → ``roles`` (is_filtered = false)
      - ``company_registry.json``  → ``company_registry``
      - ``api_profiles.json``      → ``api_profiles``

    Collections stored as JSONB blobs:
      - ``roles_cache.json``       → ``roles_cache``
      - ``roles_checkpoint.json``  → ``checkpoints``
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self._client = _supabase_client()

    # ── StorageBackend protocol ────────────────────────────────────────────────

    def read(self, collection: str) -> dict | list | None:
        handler = self._handler_for(collection)
        if handler is None:
            return None
        return handler["read"]()

    def write(self, collection: str, data: dict | list) -> None:
        handler = self._handler_for(collection)
        if handler is None:
            return
        handler["write"](data)

    def exists(self, collection: str) -> bool:
        handler = self._handler_for(collection)
        if handler is None:
            return False
        return handler["exists"]()

    def delete(self, collection: str) -> None:
        handler = self._handler_for(collection)
        if handler is None:
            return
        handler["delete"]()

    # ── Collection router ──────────────────────────────────────────────────────

    def _handler_for(self, collection: str) -> dict[str, Any] | None:
        """Return a dict of read/write/exists/delete callables for *collection*."""
        handlers: dict[str, dict[str, Any]] = {
            "resumes.json": {
                "read": self._read_resumes,
                "write": self._write_resumes,
                "exists": self._exists_resumes,
                "delete": self._delete_resumes,
            },
            "companies.json": {
                "read": self._read_companies,
                "write": self._write_companies,
                "exists": self._exists_companies,
                "delete": self._delete_companies,
            },
            "roles.json": {
                "read": self._read_roles,
                "write": self._write_roles,
                "exists": self._exists_roles,
                "delete": self._delete_roles,
            },
            "roles_unfiltered.json": {
                "read": self._read_roles_unfiltered,
                "write": self._write_roles_unfiltered,
                "exists": self._exists_roles_unfiltered,
                "delete": self._delete_roles_unfiltered,
            },
            "company_registry.json": {
                "read": self._read_registry,
                "write": self._write_registry,
                "exists": self._exists_registry,
                "delete": self._delete_registry,
            },
            "roles_cache.json": {
                "read": self._read_cache,
                "write": self._write_cache,
                "exists": self._exists_cache,
                "delete": self._delete_cache,
            },
            "roles_checkpoint.json": {
                "read": self._read_checkpoint,
                "write": self._write_checkpoint,
                "exists": self._exists_checkpoint,
                "delete": self._delete_checkpoint,
            },
            "api_profiles.json": {
                "read": self._read_api_profiles,
                "write": self._write_api_profiles,
                "exists": self._exists_api_profiles,
                "delete": self._delete_api_profiles,
            },
        }
        return handlers.get(collection)

    # ── Resumes ────────────────────────────────────────────────────────────────

    def _read_resumes(self) -> list | None:
        resp = (
            self._client.table("resumes")
            .select("*")
            .eq("user_id", self._user_id)
            .execute()
        )
        if not resp.data:
            return None
        return [self._row_to_resume(r) for r in resp.data]

    def _write_resumes(self, data: list | dict) -> None:
        # Accept both raw list and wrapped dict
        resumes = data if isinstance(data, list) else data.get("resumes", data)
        if not isinstance(resumes, list):
            return
        # Clear existing, then insert
        self._client.table("resumes").delete().eq("user_id", self._user_id).execute()
        for r in resumes:
            row = {
                "user_id": self._user_id,
                "filename": r.get("filename", ""),
                "full_text": r.get("full_text", ""),
                "skills": r.get("skills", []),
                "job_titles": r.get("job_titles", []),
                "parsed_at": r.get("parsed_at", datetime.now(timezone.utc).isoformat()),
            }
            self._client.table("resumes").upsert(row, on_conflict="user_id").execute()

    def _exists_resumes(self) -> bool:
        resp = (
            self._client.table("resumes")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_resumes(self) -> None:
        self._client.table("resumes").delete().eq("user_id", self._user_id).execute()

    @staticmethod
    def _row_to_resume(row: dict) -> dict:
        return {
            "filename": row["filename"],
            "full_text": row.get("full_text", ""),
            "sections": {},
            "skills": row.get("skills", []),
            "job_titles": row.get("job_titles", []),
            "companies_worked_at": [],
            "education": [],
            "years_of_experience": None,
            "parsed_at": row.get("parsed_at", ""),
        }

    # ── Companies ──────────────────────────────────────────────────────────────

    def _read_companies(self) -> dict | None:
        resp = (
            self._client.table("companies")
            .select("*")
            .eq("user_id", self._user_id)
            .execute()
        )
        if not resp.data:
            return None
        companies = [self._row_to_company(r) for r in resp.data]
        return {"companies": companies}

    def _write_companies(self, data: dict) -> None:
        companies = data.get("companies", [])
        self._client.table("companies").delete().eq("user_id", self._user_id).execute()
        for c in companies:
            row = {
                "user_id": self._user_id,
                "name": c["name"],
                "career_page_url": c.get("career_page_url", ""),
                "ats_type": c.get("ats_type", "unknown"),
                "ats_board_token": c.get("ats_board_token"),
                "reason": c.get("reason", ""),
                "discovered_at": c.get("discovered_at") or datetime.now(timezone.utc).isoformat(),
            }
            self._client.table("companies").insert(row).execute()

    def _exists_companies(self) -> bool:
        resp = (
            self._client.table("companies")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_companies(self) -> None:
        self._client.table("companies").delete().eq("user_id", self._user_id).execute()

    @staticmethod
    def _row_to_company(row: dict) -> dict:
        return {
            "name": row["name"],
            "reason": row.get("reason", ""),
            "career_page_url": row.get("career_page_url", ""),
            "ats_type": row.get("ats_type", "unknown"),
            "ats_board_token": row.get("ats_board_token"),
            "discovered_at": row.get("discovered_at", ""),
            "roles_fetched": False,
        }

    # ── Roles (filtered = True) ────────────────────────────────────────────────

    def _read_roles(self) -> dict | None:
        resp = (
            self._client.table("roles")
            .select("*")
            .eq("user_id", self._user_id)
            .eq("is_filtered", True)
            .execute()
        )
        if not resp.data:
            return None
        roles = [self._row_to_role(r) for r in resp.data]
        return {"roles": roles}

    def _write_roles(self, data: dict) -> None:
        roles = data.get("roles", [])
        # Delete only filtered roles, then insert
        (
            self._client.table("roles")
            .delete()
            .eq("user_id", self._user_id)
            .eq("is_filtered", True)
            .execute()
        )
        for r in roles:
            row = self._role_to_row(r, is_filtered=True)
            self._client.table("roles").upsert(row, on_conflict="user_id,url").execute()

    def _exists_roles(self) -> bool:
        resp = (
            self._client.table("roles")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .eq("is_filtered", True)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_roles(self) -> None:
        (
            self._client.table("roles")
            .delete()
            .eq("user_id", self._user_id)
            .eq("is_filtered", True)
            .execute()
        )

    # ── Roles (unfiltered) ─────────────────────────────────────────────────────

    def _read_roles_unfiltered(self) -> dict | None:
        resp = (
            self._client.table("roles")
            .select("*")
            .eq("user_id", self._user_id)
            .eq("is_filtered", False)
            .execute()
        )
        if not resp.data:
            return None
        roles = [self._row_to_role(r) for r in resp.data]
        return {"roles": roles, "total_roles": len(roles), "in_progress": False}

    def _write_roles_unfiltered(self, data: dict) -> None:
        roles = data.get("roles", [])
        (
            self._client.table("roles")
            .delete()
            .eq("user_id", self._user_id)
            .eq("is_filtered", False)
            .execute()
        )
        for r in roles:
            row = self._role_to_row(r, is_filtered=False)
            self._client.table("roles").upsert(row, on_conflict="user_id,url").execute()

    def _exists_roles_unfiltered(self) -> bool:
        resp = (
            self._client.table("roles")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .eq("is_filtered", False)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_roles_unfiltered(self) -> None:
        (
            self._client.table("roles")
            .delete()
            .eq("user_id", self._user_id)
            .eq("is_filtered", False)
            .execute()
        )

    def _role_to_row(self, r: dict, *, is_filtered: bool) -> dict:
        return {
            "user_id": self._user_id,
            "company_name": r.get("company_name", ""),
            "title": r.get("title", ""),
            "location": r.get("location", "Unknown"),
            "url": r.get("url", ""),
            "department": r.get("department"),
            "ats_type": r.get("ats_type", ""),
            "relevance_score": r.get("relevance_score"),
            "summary": r.get("summary"),
            "is_filtered": is_filtered,
            "fetched_at": r.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _row_to_role(row: dict) -> dict:
        return {
            "company_name": row["company_name"],
            "title": row["title"],
            "location": row.get("location", "Unknown"),
            "url": row.get("url", ""),
            "ats_type": row.get("ats_type", ""),
            "department": row.get("department"),
            "relevance_score": row.get("relevance_score"),
            "summary": row.get("summary"),
            "fetched_at": row.get("fetched_at", ""),
        }

    # ── Company Registry ───────────────────────────────────────────────────────

    def _read_registry(self) -> dict | None:
        resp = (
            self._client.table("company_registry")
            .select("*")
            .eq("user_id", self._user_id)
            .execute()
        )
        if not resp.data:
            return None
        companies = [
            {
                "name": r["name"],
                "ats_type": r.get("ats_type", "unknown"),
                "ats_board_token": r.get("ats_board_token"),
                "career_page_url": r.get("career_page_url", ""),
                "searchable": r.get("searchable"),
            }
            for r in resp.data
        ]
        return {"companies": companies}

    def _write_registry(self, data: dict) -> None:
        companies = data.get("companies", [])
        self._client.table("company_registry").delete().eq("user_id", self._user_id).execute()
        for c in companies:
            row = {
                "user_id": self._user_id,
                "name": c["name"],
                "ats_type": c.get("ats_type", "unknown"),
                "ats_board_token": c.get("ats_board_token"),
                "career_page_url": c.get("career_page_url", ""),
                "searchable": c.get("searchable"),
            }
            self._client.table("company_registry").insert(row).execute()

    def _exists_registry(self) -> bool:
        resp = (
            self._client.table("company_registry")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_registry(self) -> None:
        self._client.table("company_registry").delete().eq("user_id", self._user_id).execute()

    # ── Roles Cache (JSONB blob) ───────────────────────────────────────────────

    def _read_cache(self) -> dict | None:
        resp = (
            self._client.table("roles_cache")
            .select("*")
            .eq("user_id", self._user_id)
            .execute()
        )
        if not resp.data:
            return None
        # Reconstruct the {"version": 1, "entries": {...}} shape
        entries: dict = {}
        for row in resp.data:
            key = f"{row['company_name'].lower()}|{row['ats_type']}"
            entries[key] = {
                "company_name": row["company_name"],
                "ats_type": row["ats_type"],
                "cached_at": row["cached_at"],
                "roles": row.get("roles", []),
            }
        return {"version": 1, "entries": entries}

    def _write_cache(self, data: dict) -> None:
        entries = data.get("entries", {})
        for _key, entry in entries.items():
            row = {
                "user_id": self._user_id,
                "company_name": entry["company_name"],
                "ats_type": entry["ats_type"],
                "cached_at": entry["cached_at"],
                "roles": entry.get("roles", []),
            }
            (
                self._client.table("roles_cache")
                .upsert(row, on_conflict="user_id,company_name,ats_type")
                .execute()
            )

    def _exists_cache(self) -> bool:
        resp = (
            self._client.table("roles_cache")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_cache(self) -> None:
        self._client.table("roles_cache").delete().eq("user_id", self._user_id).execute()

    # ── Checkpoint (JSONB blob) ────────────────────────────────────────────────

    def _read_checkpoint(self) -> dict | None:
        resp = (
            self._client.table("checkpoints")
            .select("data")
            .eq("user_id", self._user_id)
            .execute()
        )
        if not resp.data:
            return None
        return resp.data[0].get("data")

    def _write_checkpoint(self, data: dict | list) -> None:
        row = {
            "user_id": self._user_id,
            "data": data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._client.table("checkpoints").upsert(row, on_conflict="user_id").execute()

    def _exists_checkpoint(self) -> bool:
        resp = (
            self._client.table("checkpoints")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_checkpoint(self) -> None:
        self._client.table("checkpoints").delete().eq("user_id", self._user_id).execute()

    # ── API Profiles (shared — no user_id scoping) ─────────────────────────────

    def _read_api_profiles(self) -> dict | None:
        resp = self._client.table("api_profiles").select("*").execute()
        if not resp.data:
            return None
        return {row["domain"]: row.get("endpoints", {}) for row in resp.data}

    def _write_api_profiles(self, data: dict) -> None:
        for domain, endpoints in data.items():
            row = {"domain": domain, "endpoints": endpoints}
            self._client.table("api_profiles").upsert(row, on_conflict="domain").execute()

    def _exists_api_profiles(self) -> bool:
        resp = (
            self._client.table("api_profiles")
            .select("id", count="exact")
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_api_profiles(self) -> None:
        # Shared table — delete all (admin only, rarely used)
        self._client.table("api_profiles").delete().neq("id", "").execute()
