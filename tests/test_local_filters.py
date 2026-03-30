"""Tests for local (fuzzy/semantic) role filtering and skip_career_page flag."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from jobfinder.config import AppConfig, RoleFilters
from jobfinder.roles.local_filters import (
    _title_matches_fuzzy,
    _location_matches_fuzzy,
    _expand_metro_aliases,
    _posted_after_matches,
    filter_roles_local,
)
from jobfinder.storage.schemas import DiscoveredRole


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _role(
    title: str,
    location: str = "San Francisco, CA",
    posted_at: str | None = None,
) -> DiscoveredRole:
    return DiscoveredRole(
        company_name="Acme",
        title=title,
        location=location,
        url=f"https://acme.com/jobs/{title.replace(' ', '-').lower()}",
        posted_at=posted_at,
    )


# ─── Fuzzy title matching ─────────────────────────────────────────────────────

class TestFuzzyTitleMatch:
    def test_exact_match(self):
        assert _title_matches_fuzzy("Engineering Manager", "Engineering Manager", 82) is True

    def test_word_order_variance(self):
        assert _title_matches_fuzzy("Manager of Engineering", "Engineering Manager", 82) is True

    def test_seniority_prefix_ok(self):
        assert _title_matches_fuzzy("Senior Engineering Manager", "Engineering Manager", 82) is True

    def test_group_prefix_ok(self):
        assert _title_matches_fuzzy("Group Engineering Manager", "Engineering Manager", 72) is True

    def test_different_function_fails_high(self):
        # "Product Manager" should NOT match "Engineering Manager" at high threshold
        assert _title_matches_fuzzy("Product Manager", "Engineering Manager", 82) is False

    def test_software_engineer_fails_high(self):
        # "Software Engineer" should NOT match "Engineering Manager" at high threshold
        assert _title_matches_fuzzy("Software Engineer", "Engineering Manager", 82) is False

    def test_case_insensitive(self):
        assert _title_matches_fuzzy("engineering manager", "Engineering Manager", 82) is True

    def test_low_threshold_more_permissive(self):
        # At low threshold, more titles pass (Director of Engineering scores ~73 vs threshold 60)
        assert _title_matches_fuzzy("Director of Engineering", "Engineering Manager", 60) is True


# ─── Fuzzy location matching ──────────────────────────────────────────────────

class TestFuzzyLocationMatch:
    def test_exact_city_match(self):
        assert _location_matches_fuzzy("San Francisco, CA", "San Francisco, Seattle or Remote", 70) is True

    def test_seattle_match(self):
        assert _location_matches_fuzzy("Seattle, WA", "SF, Seattle or Remote", 70) is True

    def test_remote_matches_anywhere(self):
        assert _location_matches_fuzzy("Anywhere in US", "SF, Seattle or Remote", 70) is True

    def test_remote_matches_remote(self):
        assert _location_matches_fuzzy("Remote", "SF or Remote", 70) is True

    def test_remote_matches_distributed(self):
        assert _location_matches_fuzzy("Distributed Team", "SF or Remote", 70) is True

    def test_no_match_different_city(self):
        assert _location_matches_fuzzy("London, UK", "SF, Seattle or Remote", 70) is False

    def test_no_match_austin(self):
        assert _location_matches_fuzzy("Austin, TX", "SF, Seattle or Remote", 80) is False

    def test_single_location_filter(self):
        assert _location_matches_fuzzy("New York, NY", "New York", 70) is True

    def test_location_split_on_comma(self):
        # "NYC, Boston" → ["NYC", "Boston"]
        assert _location_matches_fuzzy("Boston, MA", "NYC, Boston", 70) is True


# ─── Metro alias expansion ────────────────────────────────────────────────────

class TestExpandMetroAliases:
    """Unit tests for _expand_metro_aliases — verifies the dict keys and lookup."""

    def test_sf_key_returns_aliases(self):
        aliases = _expand_metro_aliases("SF")
        assert "san francisco" in aliases
        assert "san mateo" in aliases
        assert "silicon valley" in aliases

    def test_bay_area_key_returns_sf_aliases(self):
        aliases = _expand_metro_aliases("bay area")
        assert "palo alto" in aliases

    def test_silicon_valley_key_returns_sf_aliases(self):
        aliases = _expand_metro_aliases("silicon valley")
        assert "mountain view" in aliases

    def test_nyc_key_returns_aliases(self):
        aliases = _expand_metro_aliases("NYC")
        assert "manhattan" in aliases
        assert "brooklyn" in aliases

    def test_ny_key_returns_aliases(self):
        aliases = _expand_metro_aliases("ny")
        assert "new york" in aliases

    def test_la_key_returns_aliases(self):
        aliases = _expand_metro_aliases("LA")
        assert "los angeles" in aliases
        assert "santa monica" in aliases

    def test_seattle_key_returns_aliases(self):
        aliases = _expand_metro_aliases("seattle")
        assert "bellevue" in aliases
        assert "redmond" in aliases

    def test_dc_key_returns_aliases(self):
        aliases = _expand_metro_aliases("DC")
        assert "arlington" in aliases
        assert "northern virginia" in aliases

    def test_unknown_returns_original(self):
        # Non-metro term → returns list containing just the original part
        aliases = _expand_metro_aliases("Hamburg")
        assert aliases == ["Hamburg"]

    def test_fuzzy_key_lookup(self):
        # "Greater Seattle Area" should fuzzy-match the "seattle" key
        aliases = _expand_metro_aliases("Greater Seattle Area")
        assert "bellevue" in aliases

    def test_case_insensitive(self):
        aliases_lower = _expand_metro_aliases("sf")
        aliases_upper = _expand_metro_aliases("SF")
        assert aliases_lower == aliases_upper


class TestMetroAwareLocationMatch:
    """Integration tests for _location_matches_fuzzy with metro alias expansion."""

    # ── SF Bay Area ───────────────────────────────────────────────────────────

    def test_sf_filter_matches_san_mateo(self):
        """The canonical failing case from the user report."""
        assert _location_matches_fuzzy("San Mateo, CA", "SF", 70) is True

    def test_sf_filter_matches_bay_area(self):
        assert _location_matches_fuzzy("Bay Area", "SF", 70) is True

    def test_sf_filter_matches_silicon_valley(self):
        assert _location_matches_fuzzy("Silicon Valley, CA", "SF", 70) is True

    def test_sf_filter_matches_palo_alto(self):
        assert _location_matches_fuzzy("Palo Alto, CA", "SF", 70) is True

    def test_sf_filter_matches_mountain_view(self):
        assert _location_matches_fuzzy("Mountain View, CA", "SF", 70) is True

    def test_sf_filter_matches_san_jose(self):
        assert _location_matches_fuzzy("San Jose, CA", "SF", 70) is True

    def test_sf_filter_matches_oakland(self):
        assert _location_matches_fuzzy("Oakland, CA", "SF", 70) is True

    def test_sf_filter_matches_menlo_park(self):
        assert _location_matches_fuzzy("Menlo Park, CA", "SF", 70) is True

    def test_bay_area_filter_matches_san_mateo(self):
        assert _location_matches_fuzzy("San Mateo, CA", "Bay Area", 70) is True

    def test_greater_sf_filter_matches_palo_alto(self):
        # Fuzzy key lookup: "Greater SF" → resolves to SF aliases
        assert _location_matches_fuzzy("Palo Alto, CA", "Greater SF", 70) is True

    # ── Seattle ───────────────────────────────────────────────────────────────

    def test_seattle_filter_matches_bellevue(self):
        assert _location_matches_fuzzy("Bellevue, WA", "Seattle", 70) is True

    def test_seattle_filter_matches_redmond(self):
        assert _location_matches_fuzzy("Redmond, WA", "Seattle", 70) is True

    def test_seattle_filter_matches_kirkland(self):
        assert _location_matches_fuzzy("Kirkland, WA", "Seattle", 70) is True

    # ── New York ──────────────────────────────────────────────────────────────

    def test_nyc_filter_matches_brooklyn(self):
        assert _location_matches_fuzzy("Brooklyn, NY", "NYC", 70) is True

    def test_nyc_filter_matches_jersey_city(self):
        assert _location_matches_fuzzy("Jersey City, NJ", "NYC", 70) is True

    def test_ny_filter_matches_manhattan(self):
        assert _location_matches_fuzzy("Manhattan, New York", "NY", 70) is True

    # ── Los Angeles ───────────────────────────────────────────────────────────

    def test_la_filter_matches_santa_monica(self):
        assert _location_matches_fuzzy("Santa Monica, CA", "LA", 70) is True

    def test_la_filter_matches_culver_city(self):
        assert _location_matches_fuzzy("Culver City, CA", "LA", 70) is True

    # ── No false positives ────────────────────────────────────────────────────

    def test_sf_filter_does_not_match_austin(self):
        """Austin is not in the SF metro."""
        assert _location_matches_fuzzy("Austin, TX", "SF", 70) is False

    def test_sf_filter_does_not_match_london(self):
        assert _location_matches_fuzzy("London, UK", "SF", 70) is False

    def test_seattle_filter_does_not_match_miami(self):
        assert _location_matches_fuzzy("Miami, FL", "Seattle", 70) is False

    # ── Remote still works ────────────────────────────────────────────────────

    def test_remote_still_matches_after_metro_expansion(self):
        assert _location_matches_fuzzy("Remote", "SF or Remote", 70) is True

    def test_remote_still_matches_anywhere(self):
        assert _location_matches_fuzzy("Anywhere in US", "NYC or Remote", 70) is True

    # ── Non-metro fallback ────────────────────────────────────────────────────

    def test_non_metro_filter_still_works(self):
        # "Portland" IS a known metro, but test the general fallback concept
        assert _location_matches_fuzzy("Portland, OR", "Portland", 70) is True

    def test_unknown_city_falls_back_to_substring(self):
        # "Hamburg" has no metro entry → falls back to partial_ratio directly
        assert _location_matches_fuzzy("Hamburg, Germany", "Hamburg", 70) is True

    # ── Combined filter strings ───────────────────────────────────────────────

    def test_sf_or_remote_matches_san_mateo(self):
        assert _location_matches_fuzzy("San Mateo, CA", "SF or Remote", 70) is True

    def test_sf_or_nyc_matches_brooklyn(self):
        assert _location_matches_fuzzy("Brooklyn, NY", "SF or NYC", 70) is True

    def test_sf_comma_nyc_matches_palo_alto(self):
        assert _location_matches_fuzzy("Palo Alto, CA", "SF, NYC", 70) is True


# ─── Date matching ────────────────────────────────────────────────────────────

class TestPostedAfterMatch:
    def test_role_after_cutoff_passes(self):
        role = _role("SWE", posted_at="2026-02-15")
        assert _posted_after_matches(role, "Jan 1, 2026") is True

    def test_role_on_cutoff_passes(self):
        role = _role("SWE", posted_at="2026-01-01")
        assert _posted_after_matches(role, "Jan 1, 2026") is True

    def test_role_before_cutoff_fails(self):
        role = _role("SWE", posted_at="2025-12-31")
        assert _posted_after_matches(role, "Jan 1, 2026") is False

    def test_no_date_included(self):
        """Roles with no posting date are kept (not filtered out)."""
        role = _role("SWE", posted_at=None)
        assert _posted_after_matches(role, "Jan 1, 2026") is True

    def test_iso_date_format(self):
        role = _role("SWE", posted_at="2026-03-01T12:00:00Z")
        assert _posted_after_matches(role, "Feb 1, 2026") is True

    def test_invalid_cutoff_keeps_role(self):
        """Unparseable cutoff date → keep the role (fail open)."""
        role = _role("SWE", posted_at="2026-01-01")
        assert _posted_after_matches(role, "not a date at all xyz") is True


# ─── filter_roles_local integration ──────────────────────────────────────────

class TestFilterRolesLocal:
    def _make_roles(self) -> list[DiscoveredRole]:
        return [
            _role("Engineering Manager", "San Francisco, CA", "2026-02-01"),
            _role("Senior Engineering Manager", "Remote", "2026-01-15"),
            _role("Product Manager", "Seattle, WA", "2026-02-10"),
            _role("Software Engineer", "San Francisco, CA", "2025-12-01"),
            _role("Group Engineering Manager", "New York, NY", "2026-03-01"),
        ]

    def test_fuzzy_title_filter(self):
        roles = self._make_roles()
        filters = RoleFilters(title="engineering manager", filter_strategy="fuzzy", confidence="high")
        result = filter_roles_local(roles, filters)
        titles = [r.title for r in result]
        assert "Engineering Manager" in titles
        assert "Senior Engineering Manager" in titles
        # "Product Manager" and "Software Engineer" should be filtered out at high confidence
        assert "Product Manager" not in titles
        assert "Software Engineer" not in titles

    def test_fuzzy_location_filter(self):
        roles = self._make_roles()
        filters = RoleFilters(location="SF, Remote", filter_strategy="fuzzy", confidence="medium")
        result = filter_roles_local(roles, filters)
        for r in result:
            loc_lower = r.location.lower()
            assert any(
                kw in loc_lower for kw in ("san francisco", "remote", "anywhere", "distributed")
            )

    def test_fuzzy_posted_after_filter(self):
        roles = self._make_roles()
        filters = RoleFilters(posted_after="Feb 1, 2026", filter_strategy="fuzzy")
        result = filter_roles_local(roles, filters)
        # Only roles on/after Feb 1 pass; "Software Engineer" (Dec 2025) excluded
        dates = [r.posted_at for r in result]
        assert "2025-12-01" not in dates

    def test_fuzzy_combined_title_and_location(self):
        roles = self._make_roles()
        filters = RoleFilters(
            title="engineering manager",
            location="SF or Remote",
            filter_strategy="fuzzy",
            confidence="high",
        )
        result = filter_roles_local(roles, filters)
        # Only EM roles in SF/Remote pass
        for r in result:
            assert "manager" in r.title.lower()
            loc_lower = r.location.lower()
            assert any(kw in loc_lower for kw in ("san francisco", "remote", "anywhere"))

    def test_empty_criteria_returns_all(self):
        roles = self._make_roles()
        filters = RoleFilters(filter_strategy="fuzzy")
        result = filter_roles_local(roles, filters)
        assert len(result) == len(roles)

    def test_llm_strategy_is_not_handled(self):
        """filter_roles_local is only called for fuzzy/semantic; llm strategy is caught upstream."""
        # If somehow called with llm, it should return all (no criteria match any non-llm filter)
        roles = self._make_roles()
        filters = RoleFilters(title="engineering manager", filter_strategy="llm")
        # All criteria are inactive for llm strategy in local_filters (returns all)
        result = filter_roles_local(roles, filters)
        # With filter_strategy="llm", active_criteria won't include title (it IS set),
        # but the strategy check in filter_roles() dispatches BEFORE reaching here.
        # This test just verifies it doesn't crash.
        assert isinstance(result, list)


# ─── Filter strategy dispatching (via filter_roles()) ────────────────────────

class TestFilterStrategyDispatching:
    def test_fuzzy_strategy_skips_llm(self):
        """When filter_strategy='fuzzy', _call_llm should never be called."""
        from jobfinder.roles.filters import filter_roles

        roles = [_role("Engineering Manager", "SF")]
        filters = RoleFilters(title="engineering manager", filter_strategy="fuzzy")
        config = AppConfig(model_provider="anthropic", rpm_limit=0)

        with patch("jobfinder.roles.filters._call_llm") as mock_llm:
            result = filter_roles(roles, filters, config)
            mock_llm.assert_not_called()
        assert isinstance(result, list)

    def test_llm_strategy_calls_llm(self):
        """When filter_strategy='llm' (default), _call_llm should be called."""
        from jobfinder.roles.filters import filter_roles

        roles = [_role("Engineering Manager", "SF")]
        filters = RoleFilters(title="engineering manager", filter_strategy="llm")
        config = AppConfig(model_provider="anthropic", rpm_limit=0)

        with patch("jobfinder.roles.filters._call_llm", return_value=[(0, 85)]) as mock_llm:
            result = filter_roles(roles, filters, config)
            mock_llm.assert_called_once()


# ─── skip_career_page flag ────────────────────────────────────────────────────

class TestSkipCareerPage:
    def test_skip_career_page_skips_pass2(self):
        """With skip_career_page=True, discover_roles should return without calling Pass 2."""
        from jobfinder.roles.discovery import discover_roles
        from jobfinder.storage.schemas import DiscoveredCompany
        from jobfinder.storage.store import StorageManager

        company = DiscoveredCompany(
            name="Acme",
            reason="test",
            career_page_url="https://acme.com/careers",
            ats_type="unsupported",
            ats_board_token="",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        config = AppConfig(
            skip_career_page=True,
            rpm_limit=0,
        )

        with patch("jobfinder.roles.discovery.fetch_career_page_roles") as mock_cp:
            with patch("jobfinder.roles.discovery.get_fetcher") as mock_fetcher:
                # Make the ATS fetcher raise UnsupportedATSError so company gets flagged
                from jobfinder.roles.ats.base import UnsupportedATSError
                mock_fetcher.return_value.fetch.side_effect = UnsupportedATSError("no public api")

                import tempfile, pathlib
                with tempfile.TemporaryDirectory() as tmpdir:
                    store = StorageManager(pathlib.Path(tmpdir))
                    roles, flagged = discover_roles([company], config, store=store)

            # Career page should NOT have been called
            mock_cp.assert_not_called()

        # Company should be in flagged list
        assert len(flagged) == 1
        assert flagged[0].name == "Acme"

    def test_skip_career_page_false_by_default(self):
        config = AppConfig()
        assert config.skip_career_page is False

    def test_skip_career_page_config_field(self):
        config = AppConfig(skip_career_page=True)
        assert config.skip_career_page is True
