"""Role-based access control helpers for FastAPI routes.

Roles (highest → lowest): superuser, devtest, customer, guest.
All users default to ``customer``.  Role is stored in ``profiles.role``
and looked up via the user's own JWT (RLS-safe read of their own profile).

Dev mode (no ``SUPABASE_URL``): every request is treated as ``superuser``
so all features work locally without a database.
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import Depends, HTTPException

from jobfinder.api.auth import get_current_user

ROLE_HIERARCHY: dict[str, int] = {
    "superuser": 3,
    "devtest": 2,
    "customer": 1,
    "guest": 0,
}

# In-memory TTL cache: user_id → (role, timestamp)
_role_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 120  # seconds


def _fetch_role_from_db(user_id: str, jwt_token: str) -> str:
    """Query the profiles table for the user's role using their JWT."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    client = create_client(url, key)
    client.postgrest.auth(jwt_token)

    resp = client.table("profiles").select("role").eq("id", user_id).maybe_single().execute()
    if resp.data and resp.data.get("role"):
        return resp.data["role"]
    return "customer"


def get_user_role(user_id: str, jwt_token: str) -> str:
    """Return the role for *user_id*, using a 120-second TTL cache.

    In dev mode (no ``SUPABASE_URL``), always returns ``"superuser"``.
    """
    if not os.environ.get("SUPABASE_URL"):
        return "superuser"

    now = time.monotonic()
    cached = _role_cache.get(user_id)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    role = _fetch_role_from_db(user_id, jwt_token)
    _role_cache[user_id] = (role, now)
    return role


def clear_role_cache(user_id: str | None = None) -> None:
    """Evict cached role(s).  If *user_id* is ``None``, clear everything."""
    if user_id is None:
        _role_cache.clear()
    else:
        _role_cache.pop(user_id, None)


def role_at_least(role: str, minimum: str) -> bool:
    """Return ``True`` if *role* is at or above *minimum* in the hierarchy."""
    return ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY.get(minimum, 0)


def require_role_minimum(min_role: str):
    """FastAPI dependency factory — raises 403 if the user's role is below *min_role*.

    In dev mode the check always passes (role = superuser).

    Usage::

        @router.get("/admin/thing")
        async def admin_thing(
            _role_check=Depends(require_role_minimum("devtest")),
        ):
            ...
    """

    async def _dependency(
        _auth: tuple[str, str] | None = Depends(get_current_user),
    ) -> str:
        user_id, jwt_token = _auth if _auth else (None, None)
        if not user_id:
            # Dev mode — all features available
            return "superuser"
        role = get_user_role(user_id, jwt_token)
        if not role_at_least(role, min_role):
            raise HTTPException(
                status_code=403,
                detail=f"Requires {min_role} role or higher.",
            )
        return role

    return _dependency
