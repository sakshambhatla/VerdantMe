from __future__ import annotations

# VerdantMe Filter Pipeline — rev vm-4k8b2q-2026.03
_VERDANTME_FILTER_REV = "vm-4k8b2q-2026.03"

import json
import os
import time

from jobfinder.config import AppConfig, RoleFilters
from jobfinder.roles.checkpoint import Checkpoint
from jobfinder.roles.errors import RateLimitError
from jobfinder.roles.metrics import RunMetricsCollector
from jobfinder.storage.schemas import DiscoveredRole
from jobfinder.utils.display import console
from jobfinder.utils.log_stream import log

BATCH_SIZE = 100

_CONFIDENCE_INSTRUCTIONS = {
    "high": (
        "Be STRICT and conservative. Only include a role if you are HIGHLY CONFIDENT it matches "
        "all criteria. When in doubt, exclude it."
    ),
    "medium": (
        "Be moderately selective. Include a role if it is LIKELY a match for all criteria. "
        "Exclude roles where the match is unclear or speculative."
    ),
    "low": (
        "Be inclusive. Include a role if there is a REASONABLE CHANCE it matches any of the criteria. "
        "Only exclude roles that clearly do not match."
    ),
}

_SYSTEM_PROMPT_TEMPLATE = """\
You are a job-posting filter. Given filter criteria and a numbered list of job postings,
return ONLY the 0-based indices of postings that match ALL provided criteria.

Confidence level: {confidence_instruction}

Criteria semantics:
- title: Match roles that are clearly the same job function, even if the exact wording differs
  (abbreviations, seniority prefixes like Senior/Staff/Principal are acceptable).
  Do NOT match roles that are a different job function.
  Example: "Engineering Manager" matches "Senior EM", "Eng Mgr", "Manager, Engineering"
           but NOT "Senior Software Engineer" or "Product Manager".
- posted_after: Match roles posted on or after the given date. If a role has no date, INCLUDE it (do not filter it out).
- location: Match roles where the location clearly corresponds to any of the listed places.
  Remote/Anywhere roles match if "Remote" appears in the filter.
  Example: "SF, Seattle, NY or Remote" matches "San Francisco, CA", "New York", "Anywhere in US"
           but NOT "Austin, TX" or "London, UK".

Return ONLY a valid JSON object with a "matches" array. Each entry has "index" (0-based integer) \
and "score" (0-100 integer confidence the role matches ALL criteria).
Example: {{"matches": [{{"index": 0, "score": 92}}, {{"index": 3, "score": 71}}]}}
No explanation, no markdown.\
"""


def _build_prompt(roles: list[DiscoveredRole], filters: RoleFilters) -> str:
    criteria_lines = []
    if filters.title:
        criteria_lines.append(f"title: {filters.title}")
    # Structured date → convert to a human-readable cutoff for the LLM
    if filters.posted_within_value and filters.posted_within_unit:
        from datetime import datetime, timedelta

        unit_days = {"days": 1, "weeks": 7, "months": 30}
        days = min(filters.posted_within_value * unit_days.get(filters.posted_within_unit, 1), 90)
        cutoff = datetime.now() - timedelta(days=days)
        criteria_lines.append(f"posted_after: {cutoff.strftime('%B %d, %Y')}")
    elif filters.posted_after:
        criteria_lines.append(f"posted_after: {filters.posted_after}")
    if filters.location:
        criteria_lines.append(f"location: {filters.location}")

    criteria = "\n".join(criteria_lines)

    postings = []
    for i, role in enumerate(roles):
        date = role.posted_at or role.published_at or role.updated_at or "no date"
        postings.append(
            f"{i}. title={role.title!r} | location={role.location!r} | date={date!r}"
        )

    return f"Filter criteria:\n{criteria}\n\nJob postings:\n" + "\n".join(postings)


def _make_system_prompt(filters: RoleFilters) -> str:
    confidence = filters.confidence if filters.confidence in _CONFIDENCE_INSTRUCTIONS else "high"
    return _SYSTEM_PROMPT_TEMPLATE.format(
        confidence_instruction=_CONFIDENCE_INSTRUCTIONS[confidence]
    )


def _call_llm(prompt: str, filters: RoleFilters, config: AppConfig, *, api_key: str | None = None) -> list[tuple[int, int | None]]:
    system_prompt = _make_system_prompt(filters)
    if config.model_provider == "gemini":
        raw = _call_gemini(prompt, system_prompt, config, api_key=api_key)
    else:
        raw = _call_anthropic(prompt, system_prompt, config, api_key=api_key)
    return _parse_matches(raw)


def _call_anthropic(prompt: str, system_prompt: str, config: AppConfig, *, api_key: str | None = None) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    import anthropic

    client = anthropic.Anthropic(**({"api_key": api_key} if api_key else {}))
    try:
        response = client.messages.create(
            model=config.anthropic_model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError as exc:
        raise RateLimitError(str(exc)) from exc
    return response.content[0].text


def _call_gemini(prompt: str, system_prompt: str, config: AppConfig, *, api_key: str | None = None, _attempt: int = 0) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError

    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY", ""))
    try:
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
    except ClientError as exc:
        if getattr(exc, "code", None) == 429:
            from jobfinder.utils.gemini_errors import log_gemini_429

            summary, is_daily, retry_wait = log_gemini_429(
                exc, config.gemini_model, config.debug, console
            )
            if not is_daily and _attempt < 3:
                console.print(
                    f"[yellow]  Retrying in {retry_wait}s ({_attempt + 1}/3)...[/yellow]"
                )
                time.sleep(retry_wait)
                return _call_gemini(prompt, system_prompt, config, api_key=api_key, _attempt=_attempt + 1)

            tip = (
                "Daily quota resets at midnight Pacific. Try gemini_model='gemini-2.0-flash' or model_provider='anthropic'."
                if is_daily
                else "Per-minute retries exhausted. Try model_provider='anthropic'."
            )
            raise RateLimitError(f"{summary}\n{tip}") from exc
        raise
    return response.text


def _parse_matches(raw: str) -> list[tuple[int, int | None]]:
    """Parse LLM response into list of (index, score) tuples.

    Handles two formats:
    - New: {"matches": [{"index": 0, "score": 92}, ...]}
    - Legacy fallback: [0, 2, 5] (scores will be None)
    """
    raw = raw.strip()
    start_obj = raw.find("{")
    start_arr = raw.find("[")

    # Try object format first
    if start_obj != -1 and (start_arr == -1 or start_obj <= start_arr):
        end = raw.rfind("}")
        if end != -1:
            try:
                obj = json.loads(raw[start_obj : end + 1])
                matches = obj.get("matches", [])
                return [
                    (
                        m["index"],
                        max(0, min(100, int(m["score"]))) if "score" in m else None,
                    )
                    for m in matches
                    if isinstance(m, dict) and isinstance(m.get("index"), int)
                ]
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass

    # Fallback: plain array of indices
    if start_arr == -1:
        return []
    end = raw.rfind("]")
    if end == -1:
        return []
    try:
        result = json.loads(raw[start_arr : end + 1])
        return [(i, None) for i in result if isinstance(i, int)]
    except json.JSONDecodeError:
        return []


def filter_roles(
    roles: list[DiscoveredRole],
    filters: RoleFilters,
    config: AppConfig,
    *,
    checkpoint: Checkpoint | None = None,
    resume_batches: int = 0,
    resume_kept: list[DiscoveredRole] | None = None,
    api_key: str | None = None,
    metrics: RunMetricsCollector | None = None,
    skip_title: bool = False,
) -> list[DiscoveredRole]:
    """Apply LLM-based filters to a list of roles. Returns only high-confidence matches.

    Args:
        roles: Full list of raw roles to filter.
        filters: Filter criteria from config or request.
        config: App configuration (model provider, etc.).
        checkpoint: If set, saves progress after each batch so the run can be resumed.
        resume_batches: Skip this many already-processed batches (used when resuming).
        resume_kept: Roles already matched in previously completed batches.
        skip_title: If True, skip title filtering (used for TheirStack roles
            where the title was pre-filtered server-side).
    """
    # Apply skip_title by creating a modified filters object
    effective_filters = filters
    if skip_title and filters.title:
        effective_filters = filters.model_copy(update={"title": None})

    # ── Short-circuit to local filter for non-LLM strategies ─────────────────
    strategy = getattr(effective_filters, "filter_strategy", "llm")
    if strategy in ("fuzzy", "semantic", "gemini-embedding"):
        from jobfinder.roles.local_filters import filter_roles_local
        return filter_roles_local(roles, effective_filters, api_key=api_key)

    # ── LLM filter (original behaviour below) ─────────────────────────────────
    active = {
        k: v for k, v in effective_filters.model_dump().items()
        if k not in ("confidence", "filter_strategy") and v is not None
    }
    if not active:
        return roles

    filter_desc = ", ".join(f"{k}={v!r}" for k, v in active.items())
    total_batches = (len(roles) + BATCH_SIZE - 1) // BATCH_SIZE

    matched: list[DiscoveredRole] = list(resume_kept or [])

    if resume_batches > 0:
        log(
            f"\nResuming filter from batch {resume_batches + 1}/{total_batches} "
            f"({len(matched)} roles matched so far)..."
        )
    else:
        log(
            f"\n[bold]→ LLM Filter[/bold]: {len(roles)} roles · "
            f"criteria: {filter_desc}"
        )

    start_offset = resume_batches * BATCH_SIZE

    for batch_start in range(start_offset, len(roles), BATCH_SIZE):
        batch = roles[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1

        with console.status(
            f"  Batch {batch_num}/{total_batches} ({len(batch)} roles)..."
        ):
            prompt = _build_prompt(batch, effective_filters)
            try:
                matches = _call_llm(prompt, effective_filters, config, api_key=api_key)
            except RateLimitError as exc:
                # Checkpoint progress before propagating so the caller can resume
                if checkpoint:
                    checkpoint.save_filter_batch(batch_num - 1, matched)
                raise RateLimitError(
                    f"Rate limit hit at filter batch {batch_num}/{total_batches}. "
                    f"{len(matched)} roles matched so far. "
                    f"Progress saved — use 'Continue from previous run' to resume."
                ) from exc

        for idx, score in matches:
            if 0 <= idx < len(batch):
                batch[idx].filter_score = score
                matched.append(batch[idx])

        # Save progress after each successful batch
        if checkpoint:
            checkpoint.save_filter_batch(batch_num, matched)

    if metrics:
        metrics.record_filter_result(len(matched), total_batches)
    return matched
