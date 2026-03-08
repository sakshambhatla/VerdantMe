from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ParsedResume(BaseModel):
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
    ats_type: Literal[
        "greenhouse", "lever", "ashby", "workday", "linkedin", "unknown"
    ] = "unknown"
    ats_board_token: str | None = None
    discovered_at: str = ""
    roles_fetched: bool = False


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


class FlaggedCompany(BaseModel):
    name: str
    ats_type: str
    career_page_url: str
    reason: str
