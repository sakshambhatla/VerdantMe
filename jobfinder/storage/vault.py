"""Supabase Vault helpers for per-user encrypted API key storage.

All operations go through SECURITY DEFINER SQL functions defined in
``supabase/migrations/003_vault_api_keys.sql``.  The Supabase client is
created with the service_role key so it can call these privileged functions.
"""

from __future__ import annotations

import os
from typing import Any


def _supabase_client():
    """Lazy import + client creation (mirrors supabase_backend.py)."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SECRET_KEY"]
    return create_client(url, key)


def _is_vault_missing(exc: Exception) -> bool:
    """Return True if the exception indicates the vault SQL functions don't exist yet."""
    msg = str(exc).lower()
    return "could not find the function" in msg or "does not exist" in msg


def store_api_key(user_id: str, provider: str, api_key: str) -> None:
    """Encrypt and store an LLM API key for *user_id* / *provider*."""
    client = _supabase_client()
    try:
        client.rpc(
            "store_user_api_key",
            {"p_user_id": user_id, "p_provider": provider, "p_api_key": api_key},
        ).execute()
    except Exception as exc:
        if _is_vault_missing(exc):
            raise RuntimeError(
                "Vault SQL functions are not installed. "
                "Run: python scripts/apply_vault_migration.py"
            ) from exc
        raise


def get_api_key(user_id: str, provider: str) -> str | None:
    """Return the decrypted API key, or ``None`` if not stored."""
    client = _supabase_client()
    try:
        resp = client.rpc(
            "get_user_api_key",
            {"p_user_id": user_id, "p_provider": provider},
        ).execute()
        return resp.data if resp.data else None
    except Exception as exc:
        if _is_vault_missing(exc):
            return None
        raise


def delete_api_key(user_id: str, provider: str) -> None:
    """Remove a stored API key for *user_id* / *provider*."""
    client = _supabase_client()
    try:
        client.rpc(
            "delete_user_api_key",
            {"p_user_id": user_id, "p_provider": provider},
        ).execute()
    except Exception as exc:
        if _is_vault_missing(exc):
            return  # no-op — nothing to delete if vault isn't set up
        raise


# ── Google OAuth tokens ────────────────────────────────────────────────────


def store_google_tokens(user_id: str, access_token: str, refresh_token: str) -> None:
    """Encrypt and store Google OAuth tokens for *user_id*."""
    client = _supabase_client()
    try:
        client.rpc(
            "store_google_tokens",
            {"p_user_id": user_id, "p_access_token": access_token, "p_refresh_token": refresh_token},
        ).execute()
    except Exception as exc:
        if _is_vault_missing(exc):
            raise RuntimeError(
                "Google token vault functions are not installed. "
                "Run: python scripts/apply_vault_migration.py supabase/migrations/20240101000013_google_tokens.sql"
            ) from exc
        raise


def get_google_tokens(user_id: str) -> dict[str, str] | None:
    """Return ``{"access_token": ..., "refresh_token": ...}`` or ``None``."""
    client = _supabase_client()
    try:
        resp = client.rpc(
            "get_google_tokens",
            {"p_user_id": user_id},
        ).execute()
        return resp.data if isinstance(resp.data, dict) else None
    except Exception as exc:
        if _is_vault_missing(exc):
            return None
        raise


def delete_google_tokens(user_id: str) -> None:
    """Remove stored Google OAuth tokens for *user_id*."""
    client = _supabase_client()
    try:
        client.rpc(
            "delete_google_tokens",
            {"p_user_id": user_id},
        ).execute()
    except Exception as exc:
        if _is_vault_missing(exc):
            return
        raise


def has_google_tokens(user_id: str) -> bool:
    """Return True if the user has stored Google OAuth tokens."""
    client = _supabase_client()
    try:
        resp = client.rpc(
            "has_google_tokens",
            {"p_user_id": user_id},
        ).execute()
        return bool(resp.data)
    except Exception as exc:
        if _is_vault_missing(exc):
            return False
        raise


def has_api_keys(user_id: str) -> dict[str, bool]:
    """Return ``{"anthropic": bool, "gemini": bool}`` without decrypting."""
    client = _supabase_client()
    try:
        resp = client.rpc(
            "has_user_api_keys",
            {"p_user_id": user_id},
        ).execute()
        if isinstance(resp.data, dict):
            return resp.data
        # Fallback if RPC returns unexpected shape.
        return {"anthropic": False, "gemini": False}
    except Exception as exc:
        if _is_vault_missing(exc):
            import warnings
            warnings.warn(
                "Vault SQL functions not found — returning empty key status. "
                "Run: python scripts/apply_vault_migration.py",
                RuntimeWarning,
                stacklevel=2,
            )
            return {"anthropic": False, "gemini": False}
        raise
