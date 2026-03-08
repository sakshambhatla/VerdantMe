from __future__ import annotations

from pydantic import BaseModel


class DiscoverCompaniesRequest(BaseModel):
    max_companies: int | None = None
    model_provider: str | None = None  # overrides config


class RoleFiltersRequest(BaseModel):
    title: str | None = None
    posted_after: str | None = None
    location: str | None = None
    confidence: str = "high"


class DiscoverRolesRequest(BaseModel):
    company: str | None = None  # limit to one company
    refresh: bool = False
    role_filters: RoleFiltersRequest | None = None  # overrides config.role_filters
    relevance_score_criteria: str | None = None  # overrides config
