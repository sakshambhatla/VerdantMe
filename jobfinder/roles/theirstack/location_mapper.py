"""Convert a user location string to TheirStack API filter parameters.

Reuses the metro alias dictionary and remote-synonym detection from
``local_filters`` so that "SF, Seattle or Remote" becomes::

    {
        "job_location_pattern_or": ["san francisco", "bay area", ...],
        "remote": True,
    }

No LLM calls — purely rule-based.
"""

from __future__ import annotations

from jobfinder.roles.local_filters import (
    expand_metro_aliases,
    is_remote_part,
    split_location_filter,
)

# TheirStack uses regex matching on location fields.  We cap the number of
# alias patterns per metro to avoid bloating the request body.
_MAX_ALIASES_PER_METRO = 8


def map_location_to_theirstack_params(location: str) -> dict:
    """Convert a free-text location filter to TheirStack API parameters.

    Args:
        location: User-provided location string, e.g. "SF, Seattle or Remote".

    Returns:
        A dict with optional keys:
        - ``job_location_pattern_or``: list of city/region pattern strings
        - ``remote``: ``True`` if the user mentioned remote work
    """
    if not location or not location.strip():
        return {}

    parts = split_location_filter(location)
    patterns: list[str] = []
    remote = False

    for part in parts:
        if is_remote_part(part):
            remote = True
        else:
            aliases = expand_metro_aliases(part)
            # Deduplicate while preserving order, cap per metro
            for alias in aliases[:_MAX_ALIASES_PER_METRO]:
                lower = alias.lower()
                if lower not in patterns:
                    patterns.append(lower)

    result: dict = {}
    if patterns:
        result["job_location_pattern_or"] = patterns
    if remote:
        result["remote"] = True
    return result
