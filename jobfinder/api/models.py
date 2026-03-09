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
    company_names: list[str] | None = None  # limit to specific companies from registry
    refresh: bool = False
    resume: bool = False  # resume from checkpoint if one exists
    use_cache: bool = False  # re-use cached roles (TTL: 2 days) per company+ATS
    role_filters: RoleFiltersRequest | None = None  # overrides config.role_filters
    relevance_score_criteria: str | None = None  # overrides config
    model_provider: str | None = None  # overrides config
