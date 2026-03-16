"""Shared pytest fixtures for JobFinder tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Paths ──────────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Config / storage fixtures ──────────────────────────────────────────────────

@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """A temporary data directory; isolated per test."""
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture()
def test_config(tmp_data_dir: Path):
    """Minimal AppConfig pointing at the temp data dir; no real API keys needed."""
    from jobfinder.config import AppConfig
    return AppConfig(
        data_dir=tmp_data_dir,
        resume_dir=tmp_data_dir,
        model_provider="anthropic",
        rpm_limit=0,
    )


@pytest.fixture()
def store(tmp_data_dir: Path):
    """StorageManager backed by the temporary data directory."""
    from jobfinder.storage.store import StorageManager
    return StorageManager(tmp_data_dir)


# ── FastAPI TestClient ─────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_data_dir: Path):
    """FastAPI TestClient with app state wired to tmp_data_dir.

    Overrides ``load_config`` so the app reads/writes to ``tmp_data_dir``
    rather than the real data/ directory.
    """
    import jobfinder.api.routes.resume
    import jobfinder.api.routes.companies
    import jobfinder.api.routes.roles
    from jobfinder.config import AppConfig
    from jobfinder.storage.store import StorageManager
    from jobfinder.api.main import app

    cfg = AppConfig(
        data_dir=tmp_data_dir,
        resume_dir=tmp_data_dir,
        model_provider="anthropic",
        rpm_limit=0,
    )
    test_store = StorageManager(tmp_data_dir)

    def _patched_load_config(*a, **kw):
        return cfg

    def _patched_get_storage_backend(user_id=None):
        return test_store

    # Patch load_config and get_storage_backend everywhere the routes call them
    originals: dict = {}
    route_modules = (
        jobfinder.api.routes.resume,
        jobfinder.api.routes.companies,
        jobfinder.api.routes.roles,
    )
    for mod in route_modules:
        originals[(mod, "load_config")] = getattr(mod, "load_config", None)
        mod.load_config = _patched_load_config
        originals[(mod, "get_storage_backend")] = getattr(mod, "get_storage_backend", None)
        mod.get_storage_backend = _patched_get_storage_backend

    with TestClient(app) as c:
        # Seed app state
        app.state.registry = []
        app.state.running_agents = {}
        yield c

    # Restore originals
    for (mod, attr), fn in originals.items():
        if fn is not None:
            setattr(mod, attr, fn)


# ── ATS fixture helpers ────────────────────────────────────────────────────────

@pytest.fixture()
def greenhouse_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "greenhouse_jobs.json").read_text())


@pytest.fixture()
def lever_fixture() -> list:
    return json.loads((FIXTURES_DIR / "lever_jobs.json").read_text())


@pytest.fixture()
def ashby_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "ashby_jobs.json").read_text())
