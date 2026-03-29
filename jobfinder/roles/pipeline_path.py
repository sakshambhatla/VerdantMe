"""Pipeline path configuration for role discovery.

Each pipeline path defines which source fetched the roles and which
post-fetch filters to apply.  This allows the filter chain to skip
title filtering for TheirStack roles (where the title was already
pre-filtered server-side via ``job_title_or``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelinePathConfig:
    """Configuration for a single pipeline execution path."""
    source: str               # "ats" | "theirstack"
    skip_title_filter: bool   # True → title was pre-filtered at source
    skip_location_filter: bool
    skip_date_filter: bool


# ── Predefined paths ──────────────────────────────────────────────────────

ATS_PATH = PipelinePathConfig(
    source="ats",
    skip_title_filter=False,
    skip_location_filter=False,
    skip_date_filter=False,
)

THEIRSTACK_PATH = PipelinePathConfig(
    source="theirstack",
    skip_title_filter=True,   # title pre-filtered in TheirStack query
    skip_location_filter=False,
    skip_date_filter=False,
)

_PATH_REGISTRY: dict[str, PipelinePathConfig] = {
    "ats": ATS_PATH,
    "theirstack": THEIRSTACK_PATH,
}


def get_path_config(source_path: str) -> PipelinePathConfig:
    """Return the pipeline path config for a given source_path value."""
    return _PATH_REGISTRY.get(source_path, ATS_PATH)
