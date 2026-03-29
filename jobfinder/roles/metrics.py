"""Mutable metrics collector for a single role-discovery run.

Threaded through ``discover_roles()``, ``filter_roles()``, and
``score_roles()`` to accumulate quantitative data.  At the end of the run,
call ``to_schema()`` to freeze the state into a Pydantic model for storage.
"""

from __future__ import annotations

import time


class RunMetricsCollector:
    """Accumulates metrics during a role-discovery run."""

    def __init__(self) -> None:
        self._start = time.monotonic()
        self.companies_total: int = 0
        self.companies_succeeded: int = 0
        self.companies_failed: int = 0

        self.ats_visits: dict[str, int] = {}
        self.jobs_per_ats: dict[str, int] = {}
        self.jobs_per_company: dict[str, int] = {}
        self.career_page_per_company: dict[str, int] = {}

        self.playwright_uses: int = 0
        self.browser_agent_uses: int = 0
        self.theirstack_uses: int = 0
        self.theirstack_credits_used: int = 0

        self.total_roles_fetched: int = 0
        self.total_roles_after_filter: int = 0
        self.total_roles_after_score: int = 0

        self.filter_batches: int = 0
        self.score_batches: int = 0

        self.errors: list[str] = []

    # ── Recording methods ─────────────────────────────────────────────────

    def record_ats_fetch(
        self, company_name: str, ats_type: str, role_count: int
    ) -> None:
        self.ats_visits[ats_type] = self.ats_visits.get(ats_type, 0) + 1
        self.jobs_per_ats[ats_type] = self.jobs_per_ats.get(ats_type, 0) + role_count
        self.jobs_per_company[company_name] = (
            self.jobs_per_company.get(company_name, 0) + role_count
        )
        self.companies_succeeded += 1
        self.total_roles_fetched += role_count

    def record_ats_failure(
        self, company_name: str, ats_type: str, error: str
    ) -> None:
        self.ats_visits[ats_type] = self.ats_visits.get(ats_type, 0) + 1
        self.companies_failed += 1
        self.errors.append(f"{company_name} ({ats_type}): {error}")

    def record_career_page(self, company_name: str, role_count: int) -> None:
        self.playwright_uses += 1
        ats = "career_page"
        self.ats_visits[ats] = self.ats_visits.get(ats, 0) + 1
        self.jobs_per_ats[ats] = self.jobs_per_ats.get(ats, 0) + role_count
        self.jobs_per_company[company_name] = (
            self.jobs_per_company.get(company_name, 0) + role_count
        )
        self.career_page_per_company[company_name] = role_count
        if role_count > 0:
            self.companies_succeeded += 1
        self.total_roles_fetched += role_count

    def record_career_page_failure(self, company_name: str, error: str) -> None:
        self.playwright_uses += 1
        self.errors.append(f"{company_name} (career_page): {error}")

    def record_browser_agent(self, company_name: str, role_count: int) -> None:
        self.browser_agent_uses += 1
        ats = "browser_agent"
        self.ats_visits[ats] = self.ats_visits.get(ats, 0) + 1
        self.jobs_per_ats[ats] = self.jobs_per_ats.get(ats, 0) + role_count
        self.jobs_per_company[company_name] = (
            self.jobs_per_company.get(company_name, 0) + role_count
        )
        self.total_roles_fetched += role_count

    def record_theirstack_fetch(
        self, company_name: str, role_count: int, credits: int
    ) -> None:
        self.theirstack_uses += 1
        self.theirstack_credits_used += credits
        ats = "theirstack"
        self.ats_visits[ats] = self.ats_visits.get(ats, 0) + 1
        self.jobs_per_ats[ats] = self.jobs_per_ats.get(ats, 0) + role_count
        self.jobs_per_company[company_name] = (
            self.jobs_per_company.get(company_name, 0) + role_count
        )
        if role_count > 0:
            self.companies_succeeded += 1
        self.total_roles_fetched += role_count

    def record_external_source(
        self, source_name: str, role_count: int
    ) -> None:
        self.ats_visits[source_name] = self.ats_visits.get(source_name, 0) + 1
        self.jobs_per_ats[source_name] = (
            self.jobs_per_ats.get(source_name, 0) + role_count
        )
        self.total_roles_fetched += role_count

    def record_filter_result(self, kept: int, batches: int) -> None:
        self.total_roles_after_filter = kept
        self.filter_batches = batches

    def record_score_result(self, scored: int, batches: int) -> None:
        self.total_roles_after_score = scored
        self.score_batches = batches

    # ── Snapshot ──────────────────────────────────────────────────────────

    def to_schema(self) -> dict:
        """Freeze into a plain dict matching JobRunMetrics fields."""
        from jobfinder.storage.schemas import JobRunMetrics

        return JobRunMetrics(
            companies_total=self.companies_total,
            companies_succeeded=self.companies_succeeded,
            companies_failed=self.companies_failed,
            ats_visits=dict(self.ats_visits),
            jobs_per_ats=dict(self.jobs_per_ats),
            jobs_per_company=dict(self.jobs_per_company),
            career_page_per_company=dict(self.career_page_per_company),
            playwright_uses=self.playwright_uses,
            browser_agent_uses=self.browser_agent_uses,
            theirstack_uses=self.theirstack_uses,
            theirstack_credits_used=self.theirstack_credits_used,
            total_roles_fetched=self.total_roles_fetched,
            total_roles_after_filter=self.total_roles_after_filter,
            total_roles_after_score=self.total_roles_after_score,
            filter_batches=self.filter_batches,
            score_batches=self.score_batches,
            errors=list(self.errors),
            elapsed_seconds=round(time.monotonic() - self._start, 2),
        ).model_dump()
