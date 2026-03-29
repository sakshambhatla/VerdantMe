from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

KNOWN_ATS_TYPES = {"greenhouse", "lever", "ashby", "workday", "linkedin", "ycombinator", "unknown"}

UserRole = Literal["superuser", "devtest", "customer", "guest"]


class ParsedResume(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    full_text: str
    sections: dict[str, str]
    skills: list[str]
    job_titles: list[str]
    companies_worked_at: list[str]
    education: list[str]
    years_of_experience: int | None = None
    parsed_at: str


class DiscoveredCompany(BaseModel):
    name: str
    reason: str
    career_page_url: str
    ats_type: str = "unknown"
    ats_board_token: str | None = None
    discovered_at: str = ""
    roles_fetched: bool = False

    @field_validator("ats_type", mode="before")
    @classmethod
    def normalize_ats_type(cls, v: object) -> str:
        if isinstance(v, str) and v.lower() in KNOWN_ATS_TYPES:
            return v.lower()
        return "unknown"


class DiscoveredRole(BaseModel):
    company_name: str
    title: str
    location: str = "Unknown"
    url: str = ""
    ats_type: str = ""
    ats_job_id: str | None = None
    department: str | None = None
    team: str | None = None
    commitment: str | None = None
    workplace_type: str | None = None
    employment_type: str | None = None
    is_remote: bool | None = None
    posted_at: str | None = None
    updated_at: str | None = None
    published_at: str | None = None
    fetched_at: str = ""
    relevance_score: int | None = None
    summary: str | None = None


class FlaggedCompany(BaseModel):
    name: str
    ats_type: str
    career_page_url: str
    reason: str


class CompanyRegistryEntry(BaseModel):
    name: str
    ats_type: str = "unknown"
    ats_board_token: str | None = None
    career_page_url: str = ""
    searchable: bool | None = None  # None=untested; True=LLM found jobs; False=failed


class RolesCacheEntry(BaseModel):
    company_name: str
    ats_type: str           # e.g. "greenhouse", "career_page"
    cached_at: str          # ISO timestamp (UTC)
    roles: list[DiscoveredRole]


class CompanyRun(BaseModel):
    """A single company-discovery run, persisted per user."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_name: str  # unique 2-word name per user (e.g. "dancing-monkey")
    source_type: str  # "resume" | "seed"
    source_id: str  # resume UUID (if resume) or seed list UUID (if seed)
    seed_companies: list[str] | None = None  # original seed input, for reference
    companies: list[DiscoveredCompany] = []
    created_at: str = ""


class JobRunMetrics(BaseModel):
    """Quantitative metrics collected during a single role-discovery run."""
    companies_total: int = 0
    companies_succeeded: int = 0
    companies_failed: int = 0

    ats_visits: dict[str, int] = {}        # e.g. {"greenhouse": 3, "lever": 2}
    jobs_per_ats: dict[str, int] = {}      # e.g. {"greenhouse": 45}
    jobs_per_company: dict[str, int] = {}  # e.g. {"Stripe": 30}
    career_page_per_company: dict[str, int] = {}  # company → roles found via Tier 2 scraping

    playwright_uses: int = 0
    browser_agent_uses: int = 0

    total_roles_fetched: int = 0
    total_roles_after_filter: int = 0
    total_roles_after_score: int = 0

    filter_batches: int = 0
    score_batches: int = 0

    errors: list[str] = []
    elapsed_seconds: float = 0.0


class JobRun(BaseModel):
    """A single role-discovery run, persisted per user."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_name: str
    company_run_id: str | None = None      # link to source CompanyRun
    parent_job_run_id: str | None = None   # browser agent → API run that flagged the company
    run_type: str = "api"                  # "api" | "browser"
    status: str = "running"                # running | completed | failed | killed
    companies_input: list[str] = []
    metrics: JobRunMetrics = Field(default_factory=JobRunMetrics)
    created_at: str = ""
    completed_at: str | None = None


class ExternalJobCacheEntry(BaseModel):
    """Cached results from an external job board source (e.g. YC Jobs API)."""
    source: str              # e.g. "ycombinator"
    cached_at: str           # ISO timestamp (UTC)
    expires_at: str          # ISO timestamp (UTC)
    total_jobs: int
    roles: list[DiscoveredRole]


# ── Pipeline ─────────────────────────────────────────────────────────────────

PIPELINE_STAGES = {
    "not_started", "outreach", "recruiter", "hm_screen", "onsite", "offer", "blocked", "rejected",
}
PIPELINE_BADGES = {"done", "new", "panel", "await", "sched"}


class PipelineEntry(BaseModel):
    """A single company in the user's job-search pipeline."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    role_title: str | None = None
    stage: str = "not_started"
    note: str = ""
    next_action: str | None = None
    badge: str | None = None
    tags: list[str] = []
    sort_order: int = 0
    source: str | None = None  # "gmail" | "linkedin" | None
    created_at: str = ""
    updated_at: str = ""

    @field_validator("stage", mode="before")
    @classmethod
    def validate_stage(cls, v: object) -> str:
        if isinstance(v, str) and v in PIPELINE_STAGES:
            return v
        return "not_started"

    @field_validator("badge", mode="before")
    @classmethod
    def validate_badge(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and v in PIPELINE_BADGES:
            return v
        return None


# ── Offer Analysis ───────────────────────────────────────────────────────────

OFFER_FLAGS = {"red", "yellow", "green"}


class OfferAnalysisDimension(BaseModel):
    """A single scored dimension in an offer analysis."""
    name: str
    score: int  # 1-5
    weight: float  # 1.0 or 1.5
    rationale: str = ""
    flag: str = "yellow"  # "red" | "yellow" | "green"

    @field_validator("flag", mode="before")
    @classmethod
    def validate_flag(cls, v: object) -> str:
        if isinstance(v, str) and v in OFFER_FLAGS:
            return v
        return "yellow"


class OfferAnalysis(BaseModel):
    """LLM-powered company evaluation for an offer-stage pipeline entry."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    personal_context: str = ""
    dimensions: list[OfferAnalysisDimension] = []
    weighted_score: float | None = None
    raw_average: float | None = None
    verdict: str | None = None
    key_question: str | None = None
    flags: dict[str, int] = Field(default_factory=lambda: {"red": 0, "yellow": 0, "green": 0})
    model_provider: str | None = None
    model_name: str | None = None
    created_at: str = ""
    updated_at: str = ""


class PipelineUpdate(BaseModel):
    """A changelog entry for a pipeline entry (stage change, note, etc.)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entry_id: str
    update_type: str = "note"  # "note" | "stage_change" | "created"
    from_stage: str | None = None
    to_stage: str | None = None
    message: str = ""
    created_at: str = ""
