"""Local (non-LLM) role filtering: fuzzy string matching and semantic embedding similarity.

Both strategies avoid LLM API calls entirely, providing instant, free filtering.
The tradeoff vs. LLM filtering is reduced semantic understanding, compensated by
configurable confidence thresholds.

Usage:
    from jobfinder.roles.local_filters import filter_roles_local

    # fuzzy (always available — rapidfuzz is a core dependency)
    filters = RoleFilters(title="engineering manager", filter_strategy="fuzzy")
    matched = filter_roles_local(roles, filters)

    # semantic (requires: pip install "jobfinder[semantic]")
    filters = RoleFilters(title="engineering manager", filter_strategy="semantic")
    matched = filter_roles_local(roles, filters)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rapidfuzz import fuzz

from jobfinder.config import RoleFilters
from jobfinder.storage.schemas import DiscoveredRole
from jobfinder.utils.log_stream import log

if TYPE_CHECKING:
    pass

# ── Confidence thresholds ─────────────────────────────────────────────────────

# rapidfuzz token_set_ratio returns 0–100
_FUZZY_THRESHOLDS: dict[str, float] = {
    "high":   82.0,
    "medium": 72.0,
    "low":    60.0,
}

# cosine similarity returns 0.0–1.0
_SEMANTIC_THRESHOLDS: dict[str, float] = {
    "high":   0.72,
    "medium": 0.60,
    "low":    0.48,
}

# ── Semantic model (lazy-loaded, cached per process) ─────────────────────────

_semantic_model = None  # fastembed.TextEmbedding instance


def _get_semantic_model():
    """Return a cached fastembed TextEmbedding instance.

    Raises ImportError with install instructions if fastembed is not installed.
    The model (~70 MB) is downloaded to ~/.cache/fastembed/ on first use.

    HuggingFace authentication (optional):
    fastembed downloads models from the HF Hub.  Without a token the download
    still works but is subject to lower rate limits.  Set ``HF_TOKEN`` in your
    environment to authenticate and suppress the unauthenticated-request warning:
        export HF_TOKEN=hf_...
    """
    global _semantic_model
    if _semantic_model is not None:
        return _semantic_model
    try:
        from fastembed import TextEmbedding  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "The 'semantic' filter strategy requires fastembed.\n"
            "Install it with: pip install \"jobfinder[semantic]\"\n"
            "Or: pip install fastembed"
        ) from exc

    # Authenticate with the HF Hub if a token is available so the download
    # gets higher rate limits and the "unauthenticated requests" warning is
    # suppressed.  We accept both the canonical HF_TOKEN name and the legacy
    # HUGGING_FACE_HUB_TOKEN that some environments export instead.
    import os
    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if hf_token:
        try:
            import huggingface_hub  # transitive dep of fastembed
            huggingface_hub.login(token=hf_token, add_to_git_credential=False)
        except Exception:
            pass  # non-critical — a failed login just means the warning stays
    else:
        log(
            "[dim]Tip: set HF_TOKEN in your environment to enable faster "
            "HuggingFace model downloads and suppress the unauthenticated-request warning.[/dim]"
        )

    log("[dim]Loading embedding model (BAAI/bge-small-en-v1.5) — first use only…[/dim]")
    _semantic_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _semantic_model


# ── Utilities ─────────────────────────────────────────────────────────────────

def _split_location_filter(location_str: str) -> list[str]:
    """Split a location filter string like 'SF, Seattle or Remote' into parts."""
    parts = re.split(r",|\bor\b", location_str, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


_REMOTE_SYNONYMS = frozenset({"remote", "anywhere", "distributed", "worldwide", "globally"})


def _is_remote_part(part: str) -> bool:
    return part.lower() in _REMOTE_SYNONYMS


# ── Metro alias dictionary ────────────────────────────────────────────────────
# Each metro's aliases are the substrings we'll look for inside a role's
# location string via fuzz.partial_ratio.  Partial-ratio finds the best
# alignment of the shorter alias inside the longer role string, so "san mateo"
# scores 100 against "San Mateo, CA, United States".
#
# Keys cover every abbreviation / alias a user might type in the filter box.
# Multiple keys can share the same alias tuple (see SF aliases below).

_SF_ALIASES: tuple[str, ...] = (
    "san francisco", "bay area", "greater bay area", "silicon valley",
    "south bay", "east bay", "peninsula",
    # North Peninsula / Mid Peninsula
    "san mateo", "burlingame", "foster city", "redwood city", "belmont",
    "san carlos", "menlo park",
    # South Bay / Silicon Valley proper
    "palo alto", "mountain view", "sunnyvale", "santa clara", "cupertino",
    "san jose", "campbell", "milpitas",
    # East Bay
    "oakland", "berkeley", "emeryville", "fremont", "hayward",
    "san leandro", "walnut creek", "pleasanton",
)

_SEATTLE_ALIASES: tuple[str, ...] = (
    "seattle", "greater seattle", "puget sound",
    "bellevue", "redmond", "kirkland", "bothell",
    "renton", "issaquah", "kent", "tacoma",
)

_NYC_ALIASES: tuple[str, ...] = (
    "new york", "new york city", "nyc", "manhattan", "brooklyn",
    "queens", "bronx", "staten island", "long island",
    "jersey city", "hoboken", "newark",
    "tri-state", "greater new york",
)

_LA_ALIASES: tuple[str, ...] = (
    "los angeles", "greater los angeles", "socal", "southern california",
    "santa monica", "west hollywood", "culver city", "el segundo",
    "venice", "playa vista", "burbank", "pasadena", "glendale",
    "long beach", "torrance", "manhattan beach",
    "irvine", "orange county", "anaheim",
)

_BOSTON_ALIASES: tuple[str, ...] = (
    "boston", "greater boston", "cambridge", "somerville",
    "waltham", "burlington", "woburn", "lexington",
    "kendall square", "seaport", "back bay",
)

_DC_ALIASES: tuple[str, ...] = (
    "washington", "washington dc", "washington d.c.", "dmv",
    "arlington", "alexandria", "mclean", "tysons",
    "bethesda", "silver spring", "rockville",
    "northern virginia", "nova", "fairfax",
)

_CHICAGO_ALIASES: tuple[str, ...] = (
    "chicago", "chicagoland", "greater chicago",
    "evanston", "naperville", "schaumburg", "rosemont",
    "oak brook", "downers grove",
)

_AUSTIN_ALIASES: tuple[str, ...] = (
    "austin", "greater austin",
    "round rock", "cedar park", "pflugerville",
    "kyle", "buda",
)

_DENVER_ALIASES: tuple[str, ...] = (
    "denver", "boulder", "greater denver", "front range",
    "aurora", "broomfield", "littleton",
    "fort collins", "colorado springs", "englewood",
)

_ATLANTA_ALIASES: tuple[str, ...] = (
    "atlanta", "greater atlanta",
    "buckhead", "midtown atlanta", "alpharetta",
    "sandy springs", "decatur", "smyrna", "marietta",
)

_MIAMI_ALIASES: tuple[str, ...] = (
    "miami", "south florida",
    "fort lauderdale", "boca raton", "coral gables",
    "wynwood", "miami beach", "doral",
)

_RTP_ALIASES: tuple[str, ...] = (
    "raleigh", "durham", "chapel hill", "research triangle",
    "cary", "morrisville", "apex",
)

_PORTLAND_ALIASES: tuple[str, ...] = (
    "portland", "greater portland",
    "beaverton", "hillsboro", "lake oswego",
)

_MINNEAPOLIS_ALIASES: tuple[str, ...] = (
    "minneapolis", "saint paul", "st. paul", "twin cities",
    "bloomington", "eden prairie", "minnetonka",
)

_PHOENIX_ALIASES: tuple[str, ...] = (
    "phoenix", "scottsdale", "tempe", "mesa",
    "chandler", "gilbert", "glendale", "greater phoenix",
)

_DALLAS_ALIASES: tuple[str, ...] = (
    "dallas", "fort worth", "dfw", "greater dallas",
    "plano", "irving", "frisco", "mckinney",
    "arlington", "garland",
)

_HOUSTON_ALIASES: tuple[str, ...] = (
    "houston", "greater houston",
    "the woodlands", "sugar land", "katy",
)

# All user-facing filter keys → aliases list.
# Multiple abbreviations / synonyms that map to the same metro share one tuple.
_METRO_ALIASES: dict[str, tuple[str, ...]] = {
    # SF Bay Area
    "sf":             _SF_ALIASES,
    "bay area":       _SF_ALIASES,
    "silicon valley": _SF_ALIASES,
    "sfo":            _SF_ALIASES,
    "san francisco":  _SF_ALIASES,

    # Seattle
    "seattle":        _SEATTLE_ALIASES,
    "sea":            _SEATTLE_ALIASES,

    # New York
    "nyc":            _NYC_ALIASES,
    "ny":             _NYC_ALIASES,
    "new york":       _NYC_ALIASES,

    # Los Angeles
    "la":             _LA_ALIASES,
    "los angeles":    _LA_ALIASES,
    "socal":          _LA_ALIASES,

    # Boston
    "boston":         _BOSTON_ALIASES,

    # Washington DC
    "dc":             _DC_ALIASES,
    "washington dc":  _DC_ALIASES,
    "dmv":            _DC_ALIASES,

    # Chicago
    "chicago":        _CHICAGO_ALIASES,
    "chi":            _CHICAGO_ALIASES,

    # Austin
    "austin":         _AUSTIN_ALIASES,

    # Denver
    "denver":         _DENVER_ALIASES,

    # Atlanta
    "atlanta":        _ATLANTA_ALIASES,
    "atl":            _ATLANTA_ALIASES,

    # Miami
    "miami":          _MIAMI_ALIASES,

    # Research Triangle
    "rtp":            _RTP_ALIASES,
    "raleigh":        _RTP_ALIASES,

    # Portland
    "portland":       _PORTLAND_ALIASES,

    # Minneapolis
    "minneapolis":    _MINNEAPOLIS_ALIASES,
    "twin cities":    _MINNEAPOLIS_ALIASES,

    # Phoenix
    "phoenix":        _PHOENIX_ALIASES,

    # Dallas
    "dallas":         _DALLAS_ALIASES,
    "dfw":            _DALLAS_ALIASES,

    # Houston
    "houston":        _HOUSTON_ALIASES,
}


def _expand_metro_aliases(part: str) -> list[str]:
    """Return metro alias strings for ``part``, or ``[part]`` if no metro matches.

    Matching is two-pass:
    1. Direct dict key lookup (fast, handles "sf", "nyc", "bay area").
    2. Fuzzy key scan with token_set_ratio ≥ 85 (handles "Greater SF", "Seattle WA").

    Returns the alias list so the caller can check each alias via partial_ratio.
    """
    part_lower = part.lower().strip()

    # Fast path — exact key
    if part_lower in _METRO_ALIASES:
        return list(_METRO_ALIASES[part_lower])

    # Fuzzy key scan — handles user input like "Greater Seattle Area" → "seattle"
    for key in _METRO_ALIASES:
        if fuzz.token_set_ratio(part_lower, key) >= 85:
            return list(_METRO_ALIASES[key])

    # No metro match — fall back to the original single-string behaviour
    return [part]


def _cosine(a: "list | Any", b: "list | Any") -> float:
    """Cosine similarity between two embedding vectors."""
    import numpy as np  # fastembed brings numpy; it's a transitive dep
    a_arr = np.array(a, dtype=float)
    b_arr = np.array(b, dtype=float)
    denom = (np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


# ── Title matching ────────────────────────────────────────────────────────────

def _title_matches_fuzzy(role_title: str, filter_title: str, threshold: float) -> bool:
    """token_set_ratio handles word-order variance and function-word noise.

    Examples that pass at threshold=82:
      "manager of engineering"   ↔ "software engineering manager"  → ~85
      "senior engineering manager" ↔ "engineering manager"          → ~90
    Examples that (usually) fail at threshold=82:
      "product manager"          ↔ "engineering manager"            → ~72
      "software engineer"        ↔ "engineering manager"            → ~65
    """
    score = fuzz.token_set_ratio(role_title.lower(), filter_title.lower())
    return score >= threshold


def _title_matches_semantic(role_title: str, filter_title: str, threshold: float) -> bool:
    model = _get_semantic_model()
    embeddings = list(model.embed([role_title, filter_title]))
    sim = _cosine(embeddings[0], embeddings[1])
    return sim >= threshold


def _filter_roles_semantic(
    roles: list[DiscoveredRole],
    filters: RoleFilters,
    threshold: float,
    *,
    skip_title: bool = False,
) -> list[DiscoveredRole]:
    """Batch-embed all role texts in a single model call, then filter in memory.

    Replaces the per-role embed() loop for large batches (1 call vs N calls).
    """
    import numpy as np

    model = _get_semantic_model()

    check_title = bool(filters.title and not skip_title)
    check_location = bool(filters.location)

    # ── Build a single flat list of texts to embed ────────────────────────────
    texts: list[str] = []

    filter_title_idx: int | None = None
    if check_title:
        filter_title_idx = len(texts)
        texts.append(filters.title)  # type: ignore[arg-type]

    # For location: embed each unique non-remote filter part once
    loc_parts: list[str] = []
    non_remote_parts: list[str] = []
    has_remote_part = False
    filter_loc_part_start: int | None = None

    if check_location:
        loc_parts = _split_location_filter(filters.location)  # type: ignore[arg-type]
        has_remote_part = any(_is_remote_part(p) for p in loc_parts)
        seen: set[str] = set()
        for p in loc_parts:
            if not _is_remote_part(p) and p not in seen:
                non_remote_parts.append(p)
                seen.add(p)
        if non_remote_parts:
            filter_loc_part_start = len(texts)
            texts.extend(non_remote_parts)

    role_title_start: int | None = None
    if check_title:
        role_title_start = len(texts)
        texts.extend(r.title or "" for r in roles)

    role_loc_start: int | None = None
    if check_location:
        role_loc_start = len(texts)
        texts.extend(r.location or "" for r in roles)

    if not texts:
        # Nothing to embed — fall through to posted_after only
        return [
            r for r in roles
            if not filters.posted_after or _posted_after_matches(r, filters.posted_after)
        ]

    # ── Single batch embed + L2-normalise ─────────────────────────────────────
    emb = np.array(list(model.embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    emb /= norms  # dot(a_norm, b_norm) == cosine(a, b)

    # ── Pre-compute per-role similarity scores ────────────────────────────────
    title_sims: "np.ndarray | None" = None
    if check_title and filter_title_idx is not None and role_title_start is not None:
        title_sims = emb[role_title_start : role_title_start + len(roles)] @ emb[filter_title_idx]

    # Shape: (n_roles, n_non_remote_parts)
    loc_sims: "np.ndarray | None" = None
    if check_location and non_remote_parts and filter_loc_part_start is not None and role_loc_start is not None:
        filter_loc_vecs = emb[filter_loc_part_start : filter_loc_part_start + len(non_remote_parts)]
        role_loc_vecs = emb[role_loc_start : role_loc_start + len(roles)]
        loc_sims = role_loc_vecs @ filter_loc_vecs.T  # (n_roles, n_parts)

    # ── Filter ────────────────────────────────────────────────────────────────
    matched: list[DiscoveredRole] = []
    for i, role in enumerate(roles):
        if check_title and title_sims is not None:
            if float(title_sims[i]) < threshold:
                continue

        if check_location:
            role_loc_lower = (role.location or "").lower()
            loc_ok = False
            if has_remote_part and any(syn in role_loc_lower for syn in _REMOTE_SYNONYMS):
                loc_ok = True
            if not loc_ok and loc_sims is not None:
                if float(loc_sims[i].max()) >= threshold:
                    loc_ok = True
            if not loc_ok:
                continue

        if filters.posted_after and not _posted_after_matches(role, filters.posted_after):
            continue

        matched.append(role)

    return matched


# ── Location matching ─────────────────────────────────────────────────────────

def _location_matches_fuzzy(role_location: str, filter_location: str, threshold: float) -> bool:
    """Return True if any comma/or-separated part of filter_location matches role_location.

    Metro-aware: filter parts are first expanded to a list of metro aliases so that
    "SF" matches "San Mateo, CA", "Bay Area", "Silicon Valley", etc.  Non-metro parts
    fall back to direct partial_ratio substring matching.
    """
    parts = _split_location_filter(filter_location)
    role_loc_lower = role_location.lower()

    for part in parts:
        if _is_remote_part(part):
            # "Remote" in filter → match any role location that mentions remote synonyms
            if any(syn in role_loc_lower for syn in _REMOTE_SYNONYMS):
                return True
        else:
            # Expand filter part to metro aliases (returns [part] for non-metro terms)
            candidates = _expand_metro_aliases(part)
            for candidate in candidates:
                if fuzz.partial_ratio(candidate.lower(), role_loc_lower) >= threshold:
                    return True
    return False


def _location_matches_semantic(role_location: str, filter_location: str, threshold: float) -> bool:
    """Match each filter location part semantically against the role location."""
    parts = _split_location_filter(filter_location)
    role_loc_lower = role_location.lower()
    model = _get_semantic_model()

    for part in parts:
        if _is_remote_part(part):
            if any(syn in role_loc_lower for syn in _REMOTE_SYNONYMS):
                return True
        else:
            embeddings = list(model.embed([part, role_location]))
            sim = _cosine(embeddings[0], embeddings[1])
            if sim >= threshold:
                return True
    return False


# ── Date matching (shared for all non-LLM strategies) ────────────────────────

def _posted_after_matches(role: DiscoveredRole, after_str: str) -> bool:
    """Return True if the role was posted on or after the given natural-language date.

    Roles with no date field are excluded (consistent with LLM filter behaviour).
    """
    from dateutil.parser import parse as _parse_date, ParserError

    date_str = role.posted_at or role.published_at or role.updated_at
    if not date_str:
        return False
    try:
        cutoff = _parse_date(after_str, ignoretz=True)
        role_date = _parse_date(date_str, ignoretz=True)
        return role_date >= cutoff
    except (ParserError, ValueError, OverflowError):
        return False


# ── Public entry point ────────────────────────────────────────────────────────

def filter_roles_local(
    roles: list[DiscoveredRole],
    filters: RoleFilters,
    *,
    skip_title: bool = False,
) -> list[DiscoveredRole]:
    """Filter roles using fuzzy or semantic matching — no LLM calls.

    Args:
        roles:   Full list of raw roles to filter.
        filters: Filter criteria; ``filters.filter_strategy`` must be "fuzzy" or "semantic".
        skip_title: If True, skip title matching (e.g. for TheirStack roles
            where the title was pre-filtered server-side).

    Returns:
        Subset of *roles* that satisfy ALL provided criteria (AND logic).
    """
    strategy = filters.filter_strategy
    confidence = filters.confidence if filters.confidence in _FUZZY_THRESHOLDS else "high"
    fuzzy_threshold = _FUZZY_THRESHOLDS[confidence]
    semantic_threshold = _SEMANTIC_THRESHOLDS[confidence]

    active_criteria = {
        k: v
        for k, v in filters.model_dump().items()
        if k not in ("confidence", "filter_strategy") and v is not None
    }
    if not active_criteria:
        return roles

    log(
        f"\n[bold]→ Local Filter ({strategy})[/bold]: {len(roles)} roles · "
        + ", ".join(f"{k}={v!r}" for k, v in active_criteria.items())
    )

    if strategy == "semantic":
        matched = _filter_roles_semantic(
            roles, filters, semantic_threshold, skip_title=skip_title
        )
    else:
        matched = []
        for role in roles:
            keep = True

            if filters.title and not skip_title:
                keep = _title_matches_fuzzy(role.title, filters.title, fuzzy_threshold)
                if not keep:
                    continue

            if filters.location:
                keep = _location_matches_fuzzy(role.location, filters.location, fuzzy_threshold)
                if not keep:
                    continue

            if filters.posted_after:
                keep = _posted_after_matches(role, filters.posted_after)
                if not keep:
                    continue

            matched.append(role)

    log(f"  [dim]Local filter complete: {len(matched)}/{len(roles)} roles kept[/dim]")
    return matched
