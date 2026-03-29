"""Rule-based title broadening for TheirStack job search queries.

Strips seniority prefixes, expands common abbreviations, and removes
trailing level indicators to increase recall.  TheirStack already does
natural-language matching, so the broadening just widens the search
aperture — the post-fetch filter chain catches false positives.

Also extracts seniority level and employment type from the title for
use as additional TheirStack API parameters (``job_seniority_or``,
``employment_statuses_or``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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

# ── Seniority mapping (prefix → TheirStack job_seniority_or value) ────────

_SENIORITY_MAP: dict[str, str] = {
    "senior": "senior",
    "sr": "senior",
    "staff": "staff",
    "principal": "senior",
    "lead": "senior",
    "head of": "senior",
    "director of": "senior",
    "junior": "junior",
    "jr": "junior",
    "associate": "junior",
    "vp of": "c_level",
    "vice president of": "c_level",
    "chief": "c_level",
    "executive": "c_level",
}

# ── Employment type patterns (keyword → TheirStack employment_statuses_or) ─

_EMPLOYMENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\binternship\b", re.IGNORECASE), "internship"),
    (re.compile(r"\bintern\b", re.IGNORECASE), "internship"),
    (re.compile(r"\bcontractor\b", re.IGNORECASE), "contract"),
    (re.compile(r"\bcontract\b", re.IGNORECASE), "contract"),
    (re.compile(r"\bfreelance\b", re.IGNORECASE), "contract"),
    (re.compile(r"\bpart[- ]time\b", re.IGNORECASE), "part_time"),
    (re.compile(r"\btemporary\b", re.IGNORECASE), "temporary"),
    (re.compile(r"\btemp\b", re.IGNORECASE), "temporary"),
]


@dataclass
class TitleAnalysis:
    """Result of analysing a job title for TheirStack query parameters."""

    broadened_title: str
    seniority: str | None = None        # "senior"|"staff"|"junior"|"c_level"
    employment_type: str | None = None  # "full_time"|"part_time"|"internship"|"contract"|"temporary"


def analyze_title(title: str) -> TitleAnalysis:
    """Broaden a job title and extract seniority + employment type.

    Returns a ``TitleAnalysis`` with:
    - ``broadened_title``: title with seniority/level stripped, abbreviations expanded
    - ``seniority``: TheirStack ``job_seniority_or`` value, or ``None``
    - ``employment_type``: TheirStack ``employment_statuses_or`` value, or ``None``
    """
    if not title or not title.strip():
        return TitleAnalysis(broadened_title=title or "")

    original = title.strip()
    result = original

    # 1. Extract seniority from prefix (before stripping)
    seniority: str | None = None
    match = _PREFIX_RE.match(result)
    if match:
        prefix = match.group(0).strip().lower()
        seniority = _SENIORITY_MAP.get(prefix)

    # 2. Strip seniority prefix
    result = _PREFIX_RE.sub("", result).strip()

    # 3. Strip trailing level indicator
    result = _LEVEL_SUFFIX_RE.sub("", result).strip()

    # 4. Expand abbreviations (whole-word only)
    for pattern, expansion in _ABBR_PATTERNS:
        result = pattern.sub(expansion, result)

    # 5. Extract employment type from original title
    employment_type: str | None = None
    for pattern, emp_type in _EMPLOYMENT_PATTERNS:
        if pattern.search(original):
            employment_type = emp_type
            break

    broadened = result.strip() if result.strip() else original
    return TitleAnalysis(
        broadened_title=broadened,
        seniority=seniority,
        employment_type=employment_type,
    )


def broaden_title(title: str) -> str:
    """Broaden a job title for TheirStack search to increase recall.

    Transformations applied in order:
    1. Strip seniority prefixes (Senior, Staff, Lead, etc.)
    2. Strip trailing level indicators (I, II, III, IV, L3–L7)
    3. Expand common abbreviations (EM → Engineering Manager, etc.)

    Returns the original title if no transformations applied.
    """
    return analyze_title(title).broadened_title
