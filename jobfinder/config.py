from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel


SUPPORTED_PROVIDERS = ("anthropic", "gemini")


class RoleFilters(BaseModel):
    title: str | None = None        # e.g. "Engineering Manager"
    posted_after: str | None = None # e.g. "Feb 20, 2026"
    location: str | None = None     # e.g. "SF, Seattle, NY or Remote"
    confidence: str = "high"        # "high", "medium", or "low"
    # Matching strategy for title and location filters (posted_after is always programmatic)
    # "llm"      — batch LLM calls (default, most accurate, uses API credits)
    # "fuzzy"    — local rapidfuzz token matching (instant, free, no model needed)
    # "semantic" — local ONNX embedding similarity (instant, free, requires pip install jobfinder[semantic])
    filter_strategy: str = "llm"


class AppConfig(BaseModel):
    resume_dir: Path = Path("./resumes")
    data_dir: Path = Path("./data")
    # Model provider: "anthropic" or "gemini"
    model_provider: str = "anthropic"
    # Model name used when provider = "anthropic"
    anthropic_model: str = "claude-sonnet-4-6"
    # Model name used when provider = "gemini"
    gemini_model: str = "gemini-2.5-flash-lite"
    max_companies: int = 15
    # Default refresh behaviour for discover-companies and discover-roles
    refresh: bool = False
    request_timeout: int = 30
    role_filters: RoleFilters | None = None
    # Natural language description used to score each role 1–10 for relevance
    relevance_score_criteria: str | None = None
    # "overwrite": replace existing output file; "merge": combine with existing, sort by score
    write_preference: str = "overwrite"
    # Max LLM requests per minute (client-side throttle). Set to 0 to disable.
    rpm_limit: int = 4
    # Print full raw API error responses alongside formatted summaries.
    debug: bool = False

    # Skip Playwright career-page fallback (Pass 2) and return only ATS API results.
    # Companies with unsupported ATS types are still returned as flagged_companies.
    # Loosely coupled: set by UI checkbox today, could be auto-determined in future.
    skip_career_page: bool = False

    # Enable Y Combinator Jobs API (requires a RapidAPI key).
    enable_yc_jobs: bool = False

    # ── TheirStack settings ──────────────────────────────────────────────────
    # Enable TheirStack Job Search API as a fallback when ATS APIs fail.
    # Requires THEIRSTACK_API_KEY environment variable.
    enable_theirstack: bool = False
    # Maximum jobs to return per TheirStack query (1 credit per job).
    theirstack_max_results: int = 25
    # Total credit budget for the free tier (auto-resets after 30 days).
    theirstack_credit_budget: int = 200

    # ── Browser agent settings (config.json only, not exposed in the UI) ──────
    # Hard time wall: agent is cancelled after this many minutes regardless of steps.
    browser_agent_max_time_minutes: int = 15
    # Step budget passed to browser-use Agent.run(max_steps=...).
    browser_agent_max_steps: int = 100
    # Give up after this many consecutive 429 / rate-limit responses from the career page API.
    browser_agent_rate_limit_max_retries: int = 5
    # Initial back-off in seconds; doubles each consecutive rate-limit hit (capped at 120s).
    browser_agent_rate_limit_initial_wait: int = 5


def load_config(config_path: str | None = None, **overrides: object) -> AppConfig:
    """Load config from JSON file, then apply CLI overrides."""
    values: dict = {}

    # Default to config.json in the working directory when no explicit path is given.
    # This ensures the API server reads the same config as the CLI.
    resolved_path = config_path or "config.json"
    if Path(resolved_path).exists():
        with open(resolved_path) as f:
            values = json.load(f)

    # Apply non-None overrides from CLI flags (bool False is a valid override)
    for key, val in overrides.items():
        if val is not None:
            values[key] = val

    config = AppConfig(**values)

    if config.model_provider not in SUPPORTED_PROVIDERS:
        raise SystemExit(
            f"Invalid model_provider '{config.model_provider}' in config. "
            f"Must be one of: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    return config


def require_api_key(provider: str) -> str:
    """Ensure the correct API key env var is set for the given provider.

    Used by the **CLI** path where there is no authenticated user context.
    For the API server, use :func:`resolve_api_key` instead.
    """
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SystemExit(
                "GEMINI_API_KEY environment variable is not set.\n"
                "Export it with: export GEMINI_API_KEY=your-key-here\n"
                "Get a free key at: https://aistudio.google.com"
            )
    elif provider == "rapidapi":
        key = os.environ.get("RAPIDAPI_KEY")
        if not key:
            raise SystemExit(
                "RAPIDAPI_KEY environment variable is not set.\n"
                "Export it with: export RAPIDAPI_KEY=your-key-here\n"
                "Get a key at: https://rapidapi.com"
            )
    else:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit(
                "ANTHROPIC_API_KEY environment variable is not set.\n"
                "Export it with: export ANTHROPIC_API_KEY=your-key-here\n"
                "Get a key at: https://console.anthropic.com"
            )
    return key


def resolve_api_key(provider: str, user_id: str | None = None) -> str:
    """Resolve an LLM API key: user Vault → server env var fallback.

    Used by **API routes** where an authenticated user may have stored
    their own key in Supabase Vault.  Falls back to the server-level
    environment variable when no user key is found (or when running in
    local / unauthenticated mode).

    Raises ``ValueError`` if no key can be resolved from either source.
    """
    env_var = "GEMINI_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"

    managed_mode = bool(user_id and os.environ.get("SUPABASE_URL"))

    # 1. Try user-specific key from Vault (managed mode only).
    if managed_mode:
        try:
            from jobfinder.storage.vault import get_api_key

            vault_key = get_api_key(user_id, provider)
            if vault_key:
                return vault_key
        except Exception as exc:
            logging.warning("Vault lookup failed for user %s / %s: %s", user_id, provider, exc)

        # In managed mode, do NOT fall back to server env vars — each user
        # must store their own key via Settings → API Keys.
        raise ValueError(
            f"No {provider} API key stored. "
            "Open Settings → API Keys to add your key."
        )

    # 2. Server-level environment variable (local / CLI mode only).
    env_key = os.environ.get(env_var)
    if env_key:
        return env_key

    raise ValueError(
        f"No {provider} API key available. "
        f"Set the {env_var} environment variable."
    )


def get_rapidapi_key() -> str | None:
    """Return the server-level RapidAPI key from env, or None if not set.

    Unlike LLM keys, the RapidAPI key is a shared backend credential —
    not stored per-user in Vault.
    """
    return os.environ.get("RAPIDAPI_KEY")


def get_theirstack_api_key() -> str | None:
    """Return the TheirStack API key from env, or None if not set."""
    return os.environ.get("THEIRSTACK_API_KEY")
