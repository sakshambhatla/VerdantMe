"""Functional tests for the browser-agent post-processing pipeline.

filter → score → persist

The browser-use agent itself is never invoked.  Static job dicts from
``tests/fixtures/browser_agent_jobs.json`` simulate what the agent would find.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _load_browser_jobs() -> list[dict]:
    return json.loads((FIXTURES_DIR / "browser_agent_jobs.json").read_text())


def _config_with_scoring(test_config):
    """Return a copy of *test_config* with relevance_score_criteria set."""
    from jobfinder.config import AppConfig

    return AppConfig(
        data_dir=test_config.data_dir,
        resume_dir=test_config.resume_dir,
        model_provider="anthropic",
        rpm_limit=0,
        relevance_score_criteria="platform engineering, 5+ years",
    )


def _seed_roles(store, roles: list[dict]) -> None:
    """Write *roles* into roles.json with a minimal envelope."""
    store.write(
        "roles.json",
        {
            "fetched_at": "2026-01-01T00:00:00Z",
            "total_roles": len(roles),
            "roles_after_filter": len(roles),
            "companies_fetched": 1,
            "companies_flagged": 0,
            "flagged_companies": [],
            "roles": roles,
        },
    )


def _make_scored_roles(role_objs, scores: list[int]):
    """Return copies of *role_objs* with relevance_score and summary set."""
    return [
        r.model_copy(update={"relevance_score": s, "summary": f"Strong match — score {s}"})
        for r, s in zip(role_objs, scores)
    ]


# ─── TestScoreBrowserRoles ────────────────────────────────────────────────────

class TestScoreBrowserRoles:
    """Unit tests for the _score_browser_roles module-level helper."""

    async def test_scores_and_persists(self, store, test_config):
        from jobfinder.api.routes.roles import _score_browser_roles
        from jobfinder.storage.schemas import DiscoveredRole

        config = _config_with_scoring(test_config)
        raw = _load_browser_jobs()
        _seed_roles(store, raw)

        role_objs = [DiscoveredRole.model_validate(r) for r in raw]
        scored = _make_scored_roles(role_objs, [9, 7, 5])

        with patch("jobfinder.roles.scorer.score_roles", return_value=scored) as mock_score:
            n = await _score_browser_roles("Acme", config, store)

        assert n == 3
        mock_score.assert_called_once()

        data = store.read("roles.json")
        assert data is not None
        acme = [r for r in data["roles"] if r["company_name"] == "Acme"]
        score_vals = [r["relevance_score"] for r in acme]
        assert all(s is not None for s in score_vals)
        # Must be sorted descending
        assert score_vals == sorted(score_vals, reverse=True)

    async def test_noop_when_no_criteria(self, store, test_config):
        from jobfinder.api.routes.roles import _score_browser_roles

        # test_config has no relevance_score_criteria
        _seed_roles(store, _load_browser_jobs())

        with patch("jobfinder.roles.scorer.score_roles") as mock_score:
            n = await _score_browser_roles("Acme", test_config, store)

        assert n == 0
        mock_score.assert_not_called()

        data = store.read("roles.json")
        scores = [r.get("relevance_score") for r in data["roles"]]
        assert scores == [None, None, None]

    async def test_noop_when_no_matching_roles(self, store, test_config):
        from jobfinder.api.routes.roles import _score_browser_roles

        config = _config_with_scoring(test_config)
        _seed_roles(
            store,
            [
                {
                    "company_name": "Other Co",
                    "title": "PM",
                    "url": "https://other.co/1",
                    "ats_type": "greenhouse",
                    "fetched_at": "2026-01-01T00:00:00Z",
                }
            ],
        )

        with patch("jobfinder.roles.scorer.score_roles") as mock_score:
            n = await _score_browser_roles("Acme", config, store)

        assert n == 0
        mock_score.assert_not_called()

    async def test_preserves_other_companies(self, store, test_config):
        from jobfinder.api.routes.roles import _score_browser_roles
        from jobfinder.storage.schemas import DiscoveredRole

        config = _config_with_scoring(test_config)
        raw = _load_browser_jobs()
        beta_role = {
            "company_name": "Beta Corp",
            "title": "Designer",
            "url": "https://beta.io/1",
            "ats_type": "lever",
            "fetched_at": "2026-01-01T00:00:00Z",
            "relevance_score": 8,
        }
        _seed_roles(store, raw + [beta_role])

        acme_objs = [DiscoveredRole.model_validate(r) for r in raw]
        scored = _make_scored_roles(acme_objs, [9, 7, 5])

        with patch("jobfinder.roles.scorer.score_roles", return_value=scored):
            await _score_browser_roles("Acme", config, store)

        data = store.read("roles.json")
        beta = [r for r in data["roles"] if r["company_name"] == "Beta Corp"]
        assert len(beta) == 1
        assert beta[0]["relevance_score"] == 8  # unchanged


# ─── TestBrowserAgentJobList ──────────────────────────────────────────────────

class TestBrowserAgentJobList:
    """Functional: pre-seeded browser-agent roles appear correctly via GET /api/roles."""

    def test_get_roles_includes_browser_agent_roles(self, client, store):
        raw = _load_browser_jobs()
        _seed_roles(store, raw)

        resp = client.get("/api/roles")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_roles"] == 3
        titles = {r["title"] for r in body["roles"]}
        assert "Software Engineer" in titles
        assert "Data Scientist" in titles
        assert "Product Manager" in titles

    def test_scored_roles_have_relevance_score_and_summary(self, client, store):
        raw = _load_browser_jobs()
        scored = [
            {**r, "relevance_score": 9 - i, "summary": f"Good match {i}"}
            for i, r in enumerate(raw)
        ]
        _seed_roles(store, scored)

        resp = client.get("/api/roles")
        assert resp.status_code == 200
        roles = resp.json()["roles"]
        assert all(r["relevance_score"] is not None for r in roles)
        assert all(r["summary"] is not None for r in roles)


# ─── TestBrowserAgentFullPipeline ─────────────────────────────────────────────

class TestBrowserAgentFullPipeline:
    """Functional: static jobs → filter (simulated) → score → storage → GET /api/roles."""

    async def test_filter_then_score_pipeline(self, client, store, test_config):
        from jobfinder.api.routes.roles import _merge_to_file, _score_browser_roles
        from jobfinder.storage.schemas import DiscoveredRole

        config = _config_with_scoring(test_config)
        raw = _load_browser_jobs()

        # Start with empty storage (agent hasn't saved anything yet)
        _seed_roles(store, [])

        # Simulate filter_result: LLM kept "Software Engineer" and "Data Scientist"
        kept_raw = [r for r in raw if r["title"] != "Product Manager"]
        kept_objs = [DiscoveredRole.model_validate(r) for r in kept_raw]
        _merge_to_file([r.model_dump() for r in kept_objs], store)

        # Verify filter step: only 2 roles in storage
        assert len(store.read("roles.json")["roles"]) == 2

        # Simulate scoring
        scored_objs = _make_scored_roles(kept_objs, [9, 7])
        with patch("jobfinder.roles.scorer.score_roles", return_value=scored_objs):
            n = await _score_browser_roles("Acme", config, store)

        assert n == 2

        # Storage should have 2 scored roles
        data = store.read("roles.json")
        acme = [r for r in data["roles"] if r["company_name"] == "Acme"]
        assert len(acme) == 2
        assert all(r["relevance_score"] is not None for r in acme)
        titles = {r["title"] for r in acme}
        assert "Product Manager" not in titles

        # GET /api/roles returns scored roles
        resp = client.get("/api/roles")
        assert resp.status_code == 200
        roles = resp.json()["roles"]
        assert len(roles) == 2
        assert all(r["relevance_score"] is not None for r in roles)

    async def test_pipeline_noop_without_criteria(self, store, test_config):
        from jobfinder.api.routes.roles import _score_browser_roles

        # test_config has no relevance_score_criteria
        raw = _load_browser_jobs()
        _seed_roles(store, raw)

        with patch("jobfinder.roles.scorer.score_roles") as mock_score:
            n = await _score_browser_roles("Acme", test_config, store)

        assert n == 0
        mock_score.assert_not_called()

        data = store.read("roles.json")
        for r in data["roles"]:
            assert r.get("relevance_score") is None
