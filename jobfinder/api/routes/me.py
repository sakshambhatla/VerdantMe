"""Lightweight /me endpoint returning the authenticated user's role."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from jobfinder.api.auth import get_current_user
from jobfinder.api.rbac import get_user_role

router = APIRouter()


@router.get("/me")
async def get_me(
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    user_id, jwt_token = _auth if _auth else (None, None)
    if not user_id:
        return {"user_id": None, "role": "superuser", "display_name": "Local Dev"}
    role = await asyncio.to_thread(get_user_role, user_id, jwt_token)
    return {"user_id": user_id, "role": role}
