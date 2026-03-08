from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel


SUPPORTED_PROVIDERS = ("anthropic", "gemini")


class RoleFilters(BaseModel):
    title: str | None = None        # e.g. "Engineering Manager"
    posted_after: str | None = None # e.g. "Feb 20, 2026"
    location: str | None = None     # e.g. "SF, Seattle, NY or Remote"
    confidence: str = "high"        # "high", "medium", or "low"


class AppConfig(BaseModel):
    resume_dir: Path = Path("./resumes")
    data_dir: Path = Path("./data")
    # Model provider: "anthropic" or "gemini"
    model_provider: str = "anthropic"
    # Model name used when provider = "anthropic"
    anthropic_model: str = "claude-sonnet-4-6"
    # Model name used when provider = "gemini"
    gemini_model: str = "gemini-1.5-flash"
    max_companies: int = 15
    # Default refresh behaviour for discover-companies and discover-roles
    refresh: bool = False
    request_timeout: int = 30
    role_filters: RoleFilters | None = None


def load_config(config_path: str | None = None, **overrides: object) -> AppConfig:
    """Load config from JSON file, then apply CLI overrides."""
    values: dict = {}

    if config_path and Path(config_path).exists():
        with open(config_path) as f:
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
    """Ensure the correct API key env var is set for the given provider."""
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SystemExit(
                "GEMINI_API_KEY environment variable is not set.\n"
                "Export it with: export GEMINI_API_KEY=your-key-here\n"
                "Get a free key at: https://aistudio.google.com"
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
