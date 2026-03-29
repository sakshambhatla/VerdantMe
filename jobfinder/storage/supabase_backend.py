"""Supabase storage backend — maps collection filenames to Postgres tables.

Used when ``SUPABASE_URL`` is set.  Each user's data is isolated via RLS
(the Supabase client is initialised with the user's JWT).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def _supabase_client(jwt_token: str):
    """Lazy import + client creation so the dependency is optional.

    Uses the publishable (anon) key so that Postgres RLS policies are
    enforced.  The user's JWT is injected as the Authorization header via
    ``postgrest.auth()``, making ``auth.uid()`` available to RLS expressions.
    """
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    anon_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    client = create_client(url, anon_key)
    client.postgrest.auth(jwt_token)
    return client


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

    def __init__(self, user_id: str, jwt_token: str) -> None:
        self._user_id = user_id
        self._client = _supabase_client(jwt_token)

    @property
    def user_id(self) -> str | None:
        return self._user_id

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
            "company_runs.json": {
                "read": self._read_company_runs,
                "write": self._write_company_runs,
                "exists": self._exists_company_runs,
                "delete": self._delete_company_runs,
            },
            "job_runs.json": {
                "read": self._read_job_runs,
                "write": self._write_job_runs,
                "exists": self._exists_job_runs,
                "delete": self._delete_job_runs,
            },
            "external_job_cache.json": {
                "read": self._read_ext_cache,
                "write": self._write_ext_cache,
                "exists": self._exists_ext_cache,
                "delete": self._delete_ext_cache,
            },
            "user_motivation.json": {
                "read": self._read_motivation,
                "write": self._write_motivation,
                "exists": self._exists_motivation,
                "delete": self._delete_motivation,
            },
            "pipeline_entries.json": {
                "read": self._read_pipeline_entries,
                "write": self._write_pipeline_entries,
                "exists": self._exists_pipeline_entries,
                "delete": self._delete_pipeline_entries,
            },
            "pipeline_updates.json": {
                "read": self._read_pipeline_updates,
                "write": self._write_pipeline_updates,
                "exists": self._exists_pipeline_updates,
                "delete": self._delete_pipeline_updates,
            },
            "offer_analyses.json": {
                "read": self._read_offer_analyses,
                "write": self._write_offer_analyses,
                "exists": self._exists_offer_analyses,
                "delete": self._delete_offer_analyses,
            },
            "theirstack_credits.json": {
                "read": self._read_theirstack_credits,
                "write": self._write_theirstack_credits,
                "exists": self._exists_theirstack_credits,
                "delete": self._delete_theirstack_credits,
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
        # Clear existing, then insert (multi-resume: one row per file)
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
            # Preserve the application-generated ID so API responses and DB stay in sync
            if r.get("id"):
                row["id"] = r["id"]
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
            "id": row.get("id", ""),
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
            self._client.table("companies").upsert(row, on_conflict="user_id,name").execute()

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
            self._client.table("roles").upsert(row, on_conflict="user_id,url,is_filtered").execute()

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
            self._client.table("roles").upsert(row, on_conflict="user_id,url,is_filtered").execute()

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
                "searchable": c.get("searchable") or False,
            }
            self._client.table("company_registry").upsert(row, on_conflict="user_id,name").execute()

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

    # ── Company Runs ───────────────────────────────────────────────────────────

    def _read_company_runs(self) -> list | None:
        resp = (
            self._client.table("company_runs")
            .select("*")
            .eq("user_id", self._user_id)
            .order("created_at", desc=True)
            .execute()
        )
        if not resp.data:
            return None
        return [self._row_to_company_run(r) for r in resp.data]

    def _write_company_runs(self, data: list) -> None:
        if not isinstance(data, list):
            return
        # Delete-and-reinsert to keep order and enforce limits upstream
        self._client.table("company_runs").delete().eq("user_id", self._user_id).execute()
        for run in data:
            row = {
                "id": run.get("id"),
                "user_id": self._user_id,
                "run_name": run.get("run_name", ""),
                "source_type": run.get("source_type", "resume"),
                "source_id": run.get("source_id", ""),
                "seed_companies": run.get("seed_companies"),
                "focus": run.get("focus"),
                "companies": run.get("companies", []),
                "created_at": run.get("created_at") or datetime.now(timezone.utc).isoformat(),
            }
            self._client.table("company_runs").upsert(row, on_conflict="id").execute()

    def _exists_company_runs(self) -> bool:
        resp = (
            self._client.table("company_runs")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_company_runs(self) -> None:
        self._client.table("company_runs").delete().eq("user_id", self._user_id).execute()

    @staticmethod
    def _row_to_company_run(row: dict) -> dict:
        return {
            "id": row["id"],
            "run_name": row.get("run_name", ""),
            "source_type": row.get("source_type", "resume"),
            "source_id": row.get("source_id", ""),
            "seed_companies": row.get("seed_companies"),
            "focus": row.get("focus"),
            "companies": row.get("companies", []),
            "created_at": row.get("created_at", ""),
        }

    # ── Job Runs ──────────────────────────────────────────────────────────────

    def _read_job_runs(self) -> list | None:
        resp = (
            self._client.table("job_runs")
            .select("*")
            .eq("user_id", self._user_id)
            .order("created_at", desc=True)
            .execute()
        )
        if not resp.data:
            return None
        return [self._row_to_job_run(r) for r in resp.data]

    def _write_job_runs(self, data: list) -> None:
        if not isinstance(data, list):
            return
        self._client.table("job_runs").delete().eq("user_id", self._user_id).execute()
        for run in data:
            row = {
                "id": run.get("id"),
                "user_id": self._user_id,
                "run_name": run.get("run_name", ""),
                "company_run_id": run.get("company_run_id"),
                "parent_job_run_id": run.get("parent_job_run_id"),
                "run_type": run.get("run_type", "api"),
                "status": run.get("status", "completed"),
                "companies_input": run.get("companies_input", []),
                "metrics": run.get("metrics", {}),
                "created_at": run.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "completed_at": run.get("completed_at"),
            }
            self._client.table("job_runs").upsert(row, on_conflict="id").execute()

    def _exists_job_runs(self) -> bool:
        resp = (
            self._client.table("job_runs")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_job_runs(self) -> None:
        self._client.table("job_runs").delete().eq("user_id", self._user_id).execute()

    @staticmethod
    def _row_to_job_run(row: dict) -> dict:
        return {
            "id": row["id"],
            "run_name": row.get("run_name", ""),
            "company_run_id": row.get("company_run_id"),
            "parent_job_run_id": row.get("parent_job_run_id"),
            "run_type": row.get("run_type", "api"),
            "status": row.get("status", "completed"),
            "companies_input": row.get("companies_input", []),
            "metrics": row.get("metrics", {}),
            "created_at": row.get("created_at", ""),
            "completed_at": row.get("completed_at"),
        }

    # ── External Job Cache ─────────────────────────────────────────────────

    def _read_ext_cache(self) -> dict | None:
        resp = (
            self._client.table("external_job_cache")
            .select("*")
            .eq("user_id", self._user_id)
            .execute()
        )
        if not resp.data:
            return None
        entries: dict = {}
        for row in resp.data:
            entries[row["source"]] = {
                "source": row["source"],
                "cached_at": row["cached_at"],
                "expires_at": row["expires_at"],
                "total_jobs": row.get("total_jobs", 0),
                "roles": row.get("jobs", []),
            }
        return {"version": 1, "entries": entries}

    def _write_ext_cache(self, data: dict) -> None:
        entries = data.get("entries", {})
        for _key, entry in entries.items():
            row = {
                "user_id": self._user_id,
                "source": entry["source"],
                "cached_at": entry["cached_at"],
                "expires_at": entry["expires_at"],
                "total_jobs": entry.get("total_jobs", 0),
                "jobs": entry.get("roles", []),
            }
            (
                self._client.table("external_job_cache")
                .upsert(row, on_conflict="user_id,source")
                .execute()
            )

    def _exists_ext_cache(self) -> bool:
        resp = (
            self._client.table("external_job_cache")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_ext_cache(self) -> None:
        self._client.table("external_job_cache").delete().eq("user_id", self._user_id).execute()

    # ── User Motivation ───────────────────────────────────────────────────────

    def _read_motivation(self) -> dict | None:
        resp = (
            self._client.table("user_motivations")
            .select("*")
            .eq("user_id", self._user_id)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        return {
            "resume_id": row.get("resume_id"),
            "chat_history": row.get("chat_history", []),
            "summary": row.get("summary", ""),
            "status": row.get("status", "in_progress"),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }

    def _write_motivation(self, data: dict) -> None:
        row = {
            "user_id": self._user_id,
            "resume_id": data.get("resume_id"),
            "chat_history": data.get("chat_history", []),
            "summary": data.get("summary", ""),
            "status": data.get("status", "in_progress"),
            "updated_at": data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        }
        self._client.table("user_motivations").upsert(
            row, on_conflict="user_id"
        ).execute()

    def _exists_motivation(self) -> bool:
        resp = (
            self._client.table("user_motivations")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_motivation(self) -> None:
        self._client.table("user_motivations").delete().eq("user_id", self._user_id).execute()

    # ── Pipeline Entries ───────────────────────────────────────────────────────

    def _read_pipeline_entries(self) -> list | None:
        resp = (
            self._client.table("pipeline_entries")
            .select("*")
            .eq("user_id", self._user_id)
            .order("sort_order")
            .execute()
        )
        if not resp.data:
            return None
        return [self._row_to_pipeline_entry(r) for r in resp.data]

    def _write_pipeline_entries(self, data: list) -> None:
        if not isinstance(data, list):
            return
        for entry in data:
            row = {
                "id": entry.get("id"),
                "user_id": self._user_id,
                "company_name": entry.get("company_name", ""),
                "role_title": entry.get("role_title"),
                "stage": entry.get("stage", "not_started"),
                "note": entry.get("note", ""),
                "next_action": entry.get("next_action"),
                "badge": entry.get("badge"),
                "tags": entry.get("tags", []),
                "sort_order": entry.get("sort_order", 0),
                "source": entry.get("source"),
                "created_at": entry.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._client.table("pipeline_entries").upsert(row, on_conflict="id").execute()

    def _exists_pipeline_entries(self) -> bool:
        resp = (
            self._client.table("pipeline_entries")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_pipeline_entries(self) -> None:
        self._client.table("pipeline_entries").delete().eq("user_id", self._user_id).execute()

    @staticmethod
    def _row_to_pipeline_entry(row: dict) -> dict:
        return {
            "id": row["id"],
            "company_name": row.get("company_name", ""),
            "role_title": row.get("role_title"),
            "stage": row.get("stage", "not_started"),
            "note": row.get("note", ""),
            "next_action": row.get("next_action"),
            "badge": row.get("badge"),
            "tags": row.get("tags", []),
            "sort_order": row.get("sort_order", 0),
            "source": row.get("source"),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }

    # ── Pipeline Updates ──────────────────────────────────────────────────────

    def _read_pipeline_updates(self) -> list | None:
        resp = (
            self._client.table("pipeline_updates")
            .select("*")
            .eq("user_id", self._user_id)
            .order("created_at", desc=True)
            .execute()
        )
        if not resp.data:
            return None
        return [self._row_to_pipeline_update(r) for r in resp.data]

    def _write_pipeline_updates(self, data: list) -> None:
        if not isinstance(data, list):
            return
        for update in data:
            row = {
                "id": update.get("id"),
                "user_id": self._user_id,
                "entry_id": update.get("entry_id"),
                "update_type": update.get("update_type", "note"),
                "from_stage": update.get("from_stage"),
                "to_stage": update.get("to_stage"),
                "message": update.get("message", ""),
                "created_at": update.get("created_at") or datetime.now(timezone.utc).isoformat(),
            }
            self._client.table("pipeline_updates").upsert(row, on_conflict="id").execute()

    def _exists_pipeline_updates(self) -> bool:
        resp = (
            self._client.table("pipeline_updates")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_pipeline_updates(self) -> None:
        self._client.table("pipeline_updates").delete().eq("user_id", self._user_id).execute()

    @staticmethod
    def _row_to_pipeline_update(row: dict) -> dict:
        return {
            "id": row["id"],
            "entry_id": row.get("entry_id", ""),
            "update_type": row.get("update_type", "note"),
            "from_stage": row.get("from_stage"),
            "to_stage": row.get("to_stage"),
            "message": row.get("message", ""),
            "created_at": row.get("created_at", ""),
        }

    # ── Offer Analyses ─────────────────────────────────────────────────────────

    def _read_offer_analyses(self) -> list | None:
        resp = (
            self._client.table("offer_analyses")
            .select("*")
            .eq("user_id", self._user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        if not resp.data:
            return None
        return [self._row_to_offer_analysis(r) for r in resp.data]

    _DEFAULT_FLAGS = {"red": 0, "yellow": 0, "green": 0}

    def _write_offer_analyses(self, data: list) -> None:
        if not isinstance(data, list):
            return
        for analysis in data:
            row = {
                "id": analysis.get("id"),
                "user_id": self._user_id,
                "company_name": analysis.get("company_name", ""),
                "personal_context": analysis.get("personal_context", ""),
                "dimensions": analysis.get("dimensions", []),
                "weighted_score": analysis.get("weighted_score"),
                "raw_average": analysis.get("raw_average"),
                "verdict": analysis.get("verdict"),
                "key_question": analysis.get("key_question"),
                "flags": analysis.get("flags", self._DEFAULT_FLAGS),
                "model_provider": analysis.get("model_provider"),
                "model_name": analysis.get("model_name"),
                "created_at": analysis.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._client.table("offer_analyses").upsert(row, on_conflict="id").execute()

    def _exists_offer_analyses(self) -> bool:
        resp = (
            self._client.table("offer_analyses")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_offer_analyses(self) -> None:
        self._client.table("offer_analyses").delete().eq("user_id", self._user_id).execute()

    @staticmethod
    def _row_to_offer_analysis(row: dict) -> dict:
        return {
            "id": row["id"],
            "company_name": row.get("company_name", ""),
            "personal_context": row.get("personal_context", ""),
            "dimensions": row.get("dimensions", []),
            "weighted_score": float(row["weighted_score"]) if row.get("weighted_score") is not None else None,
            "raw_average": float(row["raw_average"]) if row.get("raw_average") is not None else None,
            "verdict": row.get("verdict"),
            "key_question": row.get("key_question"),
            "flags": row.get("flags") or self._DEFAULT_FLAGS,
            "model_provider": row.get("model_provider"),
            "model_name": row.get("model_name"),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }

    # ── TheirStack Credits (JSONB blob) ───────────────────────────────────────

    def _read_theirstack_credits(self) -> dict | None:
        resp = (
            self._client.table("theirstack_credits")
            .select("data")
            .eq("user_id", self._user_id)
            .execute()
        )
        if not resp.data:
            return None
        return resp.data[0].get("data")

    def _write_theirstack_credits(self, data: dict | list) -> None:
        row = {
            "user_id": self._user_id,
            "data": data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._client.table("theirstack_credits").upsert(row, on_conflict="user_id").execute()

    def _exists_theirstack_credits(self) -> bool:
        resp = (
            self._client.table("theirstack_credits")
            .select("id", count="exact")
            .eq("user_id", self._user_id)
            .execute()
        )
        return (resp.count or 0) > 0

    def _delete_theirstack_credits(self) -> None:
        self._client.table("theirstack_credits").delete().eq("user_id", self._user_id).execute()
