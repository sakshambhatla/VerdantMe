from __future__ import annotations

from pydantic import BaseModel


class DiscoverCompaniesRequest(BaseModel):
    max_companies: int | None = None
    model_provider: str | None = None  # overrides config
    seed_companies: list[str] | None = None  # if set, use seed-based discovery instead of resume
    resume_id: str | None = None  # UUID of the selected resume (required in resume mode)
    focus: str | None = None  # "regular" | "startups"; startups enables YC Jobs in role discovery


class RoleFiltersRequest(BaseModel):
    title: str | None = None
    posted_after: str | None = None
    location: str | None = None
    confidence: str = "high"
    filter_strategy: str | None = None  # "llm" | "fuzzy" | "semantic"; None → use config default


class DiscoverRolesRequest(BaseModel):
    company_names: list[str] | None = None  # limit to specific companies from registry
    company_run_id: str | None = None  # use all companies from a specific company run
    refresh: bool = False
    resume: bool = False  # resume from checkpoint if one exists
    use_cache: bool = False  # re-use cached roles (TTL: 2 days) per company+ATS
    role_filters: RoleFiltersRequest | None = None  # overrides config.role_filters
    relevance_score_criteria: str | None = None  # overrides config
    model_provider: str | None = None  # overrides config
    skip_career_page: bool | None = None  # True → skip Playwright Pass 2; None → use config default
    enable_yc_jobs: bool | None = None  # True → enable YC Jobs Pass 0; auto-set from company run focus


class MotivationChatRequest(BaseModel):
    message: str  # user's latest chat message
    resume_id: str | None = None  # optional resume for context
    model_provider: str | None = None  # override LLM provider


class FetchBrowserRolesRequest(BaseModel):
    company_name: str  # must exist in the company registry


# ── Pipeline ─────────────────────────────────────────────────────────────────

class CreatePipelineEntryRequest(BaseModel):
    company_name: str
    role_title: str | None = None
    stage: str = "not_started"
    note: str = ""
    next_action: str | None = None
    badge: str | None = None
    tags: list[str] = []


class UpdatePipelineEntryRequest(BaseModel):
    company_name: str | None = None
    role_title: str | None = None
    stage: str | None = None
    note: str | None = None
    next_action: str | None = None
    badge: str | None = None
    tags: list[str] | None = None
    sort_order: int | None = None


class ReorderPipelineRequest(BaseModel):
    """Batch update sort_order and stage for drag-and-drop."""
    moves: list[dict]  # [{id, stage, sort_order}, ...]


class CreatePipelineUpdateRequest(BaseModel):
    entry_id: str
    message: str


class PipelineSyncRequest(BaseModel):
    model_provider: str | None = None  # override LLM provider for reasoning
    lookback_days: int = 3  # 1–14; how far back to scan Gmail/Calendar
    custom_phrases: list[str] = []  # extra company names or keywords to search


class SyncSuggestionApply(BaseModel):
    entry_id: str | None = None
    company_name: str
    suggested_stage: str | None = None
    suggested_badge: str | None = None
    suggested_next_action: str | None = None
    reason: str = ""
    source: str = "llm"


class ApplySyncSuggestionsRequest(BaseModel):
    suggestions: list[SyncSuggestionApply] = []  # accepted updates to existing entries
    new_companies: list[SyncSuggestionApply] = []  # accepted new companies to add


# ── Offer Analysis ──────────────────────────────────────────────────────────

class AnalyzeOfferRequest(BaseModel):
    company_name: str
    personal_context: str = ""
    model_provider: str | None = None  # override LLM provider


class SaveOfferContextRequest(BaseModel):
    company_name: str
    personal_context: str
