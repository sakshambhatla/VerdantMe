"""Rule-based title broadening for TheirStack job search queries.

Strips seniority prefixes, expands common abbreviations, and removes
trailing level indicators to increase recall.  TheirStack already does
natural-language matching, so the broadening just widens the search
aperture — the post-fetch filter chain catches false positives.
"""

from __future__ import annotations

import re

# ── Seniority prefixes (removed entirely) ──────────────────────────────────

_SENIORITY_PREFIXES: tuple[str, ...] = (
    "senior", "staff", "principal", "lead", "junior",
    "jr", "sr", "head of", "vp of", "vice president of",
    "director of", "associate", "chief", "executive",
)

# Compiled pattern: match any prefix at start of string followed by whitespace
_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in _SENIORITY_PREFIXES) + r")\s+",
    re.IGNORECASE,
)

# ── Trailing level indicators (removed) ────────────────────────────────────

_LEVEL_SUFFIX_RE = re.compile(
    r"\s+(?:I{1,3}V?|IV|L[3-7])\s*$",
    re.IGNORECASE,
)

# ── Abbreviation expansion ─────────────────────────────────────────────────
# Only applied when the abbreviation is the entire title (after prefix strip)
# or appears as a whole word.

_ABBREVIATIONS: dict[str, str] = {
    "em": "Engineering Manager",
    "swe": "Software Engineer",
    "sde": "Software Development Engineer",
    "pm": "Product Manager",
    "tpm": "Technical Program Manager",
    "mle": "Machine Learning Engineer",
    "devops": "DevOps Engineer",
    "sre": "Site Reliability Engineer",
    "qa": "Quality Assurance Engineer",
    "ds": "Data Scientist",
    "de": "Data Engineer",
    "fe": "Frontend Engineer",
    "be": "Backend Engineer",
}

# Word-boundary pattern for each abbreviation
_ABBR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"\b{re.escape(abbr)}\b", re.IGNORECASE), expansion)
    for abbr, expansion in _ABBREVIATIONS.items()
]


def broaden_title(title: str) -> str:
    """Broaden a job title for TheirStack search to increase recall.

    Transformations applied in order:
    1. Strip seniority prefixes (Senior, Staff, Lead, etc.)
    2. Strip trailing level indicators (I, II, III, IV, L3–L7)
    3. Expand common abbreviations (EM → Engineering Manager, etc.)

    Returns the original title if no transformations applied.
    """
    if not title or not title.strip():
        return title

    result = title.strip()

    # 1. Strip seniority prefix
    result = _PREFIX_RE.sub("", result).strip()

    # 2. Strip trailing level indicator
    result = _LEVEL_SUFFIX_RE.sub("", result).strip()

    # 3. Expand abbreviations (whole-word only)
    for pattern, expansion in _ABBR_PATTERNS:
        result = pattern.sub(expansion, result)

    # If everything was stripped, return the original
    return result.strip() if result.strip() else title.strip()
