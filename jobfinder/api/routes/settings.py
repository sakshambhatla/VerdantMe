from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jobfinder.api.auth import get_current_user

router = APIRouter()


class StoreApiKeyRequest(BaseModel):
    provider: str  # "anthropic" | "gemini"
    api_key: str


class StoreGoogleTokensRequest(BaseModel):
    access_token: str
    refresh_token: str


@router.get("/settings/api-keys")
async def get_api_key_status(
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Return which LLM API keys the user has stored (never the values)."""
    user_id = _auth[0] if _auth else None
    if not user_id or not os.environ.get("SUPABASE_URL"):
        return {"anthropic": False, "gemini": False}

    from jobfinder.storage.vault import has_api_keys

    return has_api_keys(user_id)


@router.post("/settings/api-keys")
async def store_api_key_endpoint(
    req: StoreApiKeyRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Store (or replace) an LLM API key for the authenticated user."""
    user_id = _auth[0] if _auth else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not os.environ.get("SUPABASE_URL"):
        raise HTTPException(
            status_code=400,
            detail="Key storage requires managed mode (Supabase).",
        )
    if req.provider not in ("anthropic", "gemini"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{req.provider}'. Use 'anthropic' or 'gemini'.",
        )
    if not req.api_key.strip():
        raise HTTPException(status_code=400, detail="API key must not be empty.")

    # Lightweight validation: try a cheap API call to catch typos.
    await _validate_key(req.provider, req.api_key.strip())

    from jobfinder.storage.vault import store_api_key

    store_api_key(user_id, req.provider, req.api_key.strip())
    return {"status": "stored", "provider": req.provider}


@router.post("/settings/api-keys/{provider}/validate")
async def validate_stored_api_key(
    provider: str,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Re-validate a previously stored LLM API key against the provider."""
    user_id = _auth[0] if _auth else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not os.environ.get("SUPABASE_URL"):
        raise HTTPException(status_code=400, detail="Key storage requires managed mode (Supabase).")
    if provider not in ("anthropic", "gemini"):
        raise HTTPException(status_code=400, detail=f"Unsupported provider '{provider}'.")

    from jobfinder.storage.vault import get_api_key

    key = get_api_key(user_id, provider)
    if not key:
        raise HTTPException(status_code=404, detail=f"No {provider} API key stored.")

    await _validate_key(provider, key)
    return {"valid": True, "provider": provider}


@router.delete("/settings/api-keys/{provider}")
async def delete_api_key_endpoint(
    provider: str,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Remove a stored LLM API key for the authenticated user."""
    user_id = _auth[0] if _auth else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not os.environ.get("SUPABASE_URL"):
        raise HTTPException(
            status_code=400,
            detail="Key storage requires managed mode (Supabase).",
        )
    if provider not in ("anthropic", "gemini"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{provider}'.",
        )

    from jobfinder.storage.vault import delete_api_key

    delete_api_key(user_id, provider)
    return {"status": "deleted", "provider": provider}


# ── Google OAuth tokens ────────────────────────────────────────────────────


@router.get("/settings/google-tokens")
async def get_google_token_status(
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Return whether the user has stored Google OAuth tokens (never values)."""
    user_id = _auth[0] if _auth else None
    if not user_id or not os.environ.get("SUPABASE_URL"):
        return {"connected": False}

    from jobfinder.storage.vault import has_google_tokens

    return {"connected": has_google_tokens(user_id)}


@router.post("/settings/google-tokens")
async def store_google_tokens_endpoint(
    req: StoreGoogleTokensRequest,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Store Google OAuth tokens (access + refresh) in encrypted Vault."""
    user_id = _auth[0] if _auth else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not os.environ.get("SUPABASE_URL"):
        raise HTTPException(status_code=400, detail="Token storage requires managed mode (Supabase).")
    if not req.access_token.strip() or not req.refresh_token.strip():
        raise HTTPException(status_code=400, detail="Both access_token and refresh_token are required.")

    from jobfinder.storage.vault import store_google_tokens

    store_google_tokens(user_id, req.access_token.strip(), req.refresh_token.strip())
    return {"status": "stored"}


@router.delete("/settings/google-tokens")
async def delete_google_tokens_endpoint(
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Remove stored Google OAuth tokens."""
    user_id = _auth[0] if _auth else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not os.environ.get("SUPABASE_URL"):
        raise HTTPException(status_code=400, detail="Token storage requires managed mode (Supabase).")

    from jobfinder.storage.vault import delete_google_tokens

    delete_google_tokens(user_id)
    return {"status": "deleted"}


async def _validate_key(provider: str, api_key: str) -> None:
    """Make a lightweight API call to verify the key works.

    Raises HTTPException(400) on invalid keys so the user gets immediate
    feedback rather than a cryptic error during discovery.
    """
    import asyncio

    try:
        if provider == "anthropic":
            await asyncio.to_thread(_validate_anthropic_key, api_key)
        else:
            await asyncio.to_thread(_validate_gemini_key, api_key)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"API key validation failed: {exc}",
        ) from exc


def _validate_anthropic_key(api_key: str) -> None:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    try:
        # Cheapest possible call: count tokens on a tiny string.
        client.messages.count_tokens(
            model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hi"}],
        )
    except anthropic.AuthenticationError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid Anthropic API key. Please check and try again.",
        ) from exc


def _validate_gemini_key(api_key: str) -> None:
    from google import genai
    from google.genai.errors import ClientError

    client = genai.Client(api_key=api_key)
    try:
        # Cheapest possible call: list models.
        next(iter(client.models.list(config={"page_size": 1})))
    except ClientError as exc:
        if getattr(exc, "code", None) in (401, 403):
            raise HTTPException(
                status_code=400,
                detail="Invalid Gemini API key. Please check and try again.",
            ) from exc
        raise
