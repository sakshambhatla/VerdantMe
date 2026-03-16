"""Authentication dependency for FastAPI routes.

When ``SUPABASE_URL`` is set, verifies the Supabase JWT from the
``Authorization: Bearer <token>`` header (or ``?token=`` query param for SSE)
and returns the ``user_id``.

When ``SUPABASE_URL`` is **not** set (local dev), returns ``None`` — the
storage factory falls back to :class:`JsonStorageBackend` and no auth is
required.
"""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# auto_error=False so the dependency doesn't 403 when no header is present
# (we handle the missing-header case ourselves below).
_bearer = HTTPBearer(auto_error=False)


def _decode_jwt(raw_token: str) -> str:
    """Decode a Supabase JWT and return the user UUID (``sub`` claim)."""
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not jwt_secret:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: SUPABASE_JWT_SECRET not set",
        )
    try:
        import jwt

        payload = jwt.decode(
            raw_token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload["sub"]
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: pyjwt not installed",
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(None),
) -> str | None:
    """Return the authenticated user's UUID, or ``None`` in dev mode.

    Accepts the JWT from either:
      - ``Authorization: Bearer <token>`` header (standard REST calls)
      - ``?token=<jwt>`` query param (SSE via EventSource, which can't send headers)

    Dev mode: ``SUPABASE_URL`` is not set -> no auth required.
    Prod mode: ``SUPABASE_URL`` is set -> JWT must be valid.
    """
    if not os.environ.get("SUPABASE_URL"):
        return None  # dev bypass -- local JSON storage, no auth

    # Prefer header, fall back to query param (SSE)
    raw_token = (credentials.credentials if credentials else None) or token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return _decode_jwt(raw_token)
