from __future__ import annotations

import json
import os
import time

from jobfinder.config import AppConfig, RoleFilters
from jobfinder.roles.checkpoint import Checkpoint
from jobfinder.roles.errors import RateLimitError
from jobfinder.storage.schemas import DiscoveredRole
from jobfinder.utils.display import console

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
- posted_after: Match roles posted on or after the given date. If a role has no date, EXCLUDE it.
- location: Match roles where the location clearly corresponds to any of the listed places.
  Remote/Anywhere roles match if "Remote" appears in the filter.
  Example: "SF, Seattle, NY or Remote" matches "San Francisco, CA", "New York", "Anywhere in US"
           but NOT "Austin, TX" or "London, UK".

Return ONLY a valid JSON array of matching indices, e.g. [0, 2, 5]. No explanation, no markdown.\
"""


def _build_prompt(roles: list[DiscoveredRole], filters: RoleFilters) -> str:
    criteria_lines = []
    if filters.title:
        criteria_lines.append(f"title: {filters.title}")
    if filters.posted_after:
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


def _call_llm(prompt: str, filters: RoleFilters, config: AppConfig) -> list[int]:
    system_prompt = _make_system_prompt(filters)
    if config.model_provider == "gemini":
        raw = _call_gemini(prompt, system_prompt, config)
    else:
        raw = _call_anthropic(prompt, system_prompt, config)
    return _parse_indices(raw)


def _call_anthropic(prompt: str, system_prompt: str, config: AppConfig) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    import anthropic

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=config.anthropic_model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError as exc:
        raise RateLimitError(str(exc)) from exc
    return response.content[0].text


def _call_gemini(prompt: str, system_prompt: str, config: AppConfig, *, _attempt: int = 0) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    try:
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
    except ClientError as exc:
        if getattr(exc, "code", None) == 429:
            detail = str(exc)
            console.print(f"[yellow]  Gemini 429 detail: {detail}[/yellow]")

            # Per-minute limits recover after ~60s → retry with backoff.
            # Daily/project quota limits do not recover — surface immediately.
            is_per_minute = any(
                kw in detail.lower()
                for kw in ("per_minute", "per minute", "perminute", "requests_per_minute")
            )
            if is_per_minute and _attempt < 3:
                wait = 65  # slightly over 1 min so the sliding window clears
                console.print(
                    f"[yellow]  RPM limit — waiting {wait}s, retry {_attempt + 1}/3...[/yellow]"
                )
                time.sleep(wait)
                return _call_gemini(prompt, system_prompt, config, _attempt=_attempt + 1)

            quota_type = (
                "per-minute limit (retries exhausted)" if is_per_minute else "daily quota"
            )
            raise RateLimitError(
                f"Gemini {quota_type} exceeded.\n"
                f"Detail: {detail}\n"
                f"Tip: try 'gemini-2.0-flash' in config.json (higher free-tier RPD) "
                f"or switch to model_provider='anthropic'."
            ) from exc
        raise
    return response.text


def _parse_indices(raw: str) -> list[int]:
    raw = raw.strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        result = json.loads(raw[start : end + 1])
        return [i for i in result if isinstance(i, int)]
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
) -> list[DiscoveredRole]:
    """Apply LLM-based filters to a list of roles. Returns only high-confidence matches.

    Args:
        roles: Full list of raw roles to filter.
        filters: Filter criteria from config or request.
        config: App configuration (model provider, etc.).
        checkpoint: If set, saves progress after each batch so the run can be resumed.
        resume_batches: Skip this many already-processed batches (used when resuming).
        resume_kept: Roles already matched in previously completed batches.
    """
    active = {k: v for k, v in filters.model_dump().items() if v is not None}
    if not active:
        return roles

    filter_desc = ", ".join(f"{k}={v!r}" for k, v in active.items())
    total_batches = (len(roles) + BATCH_SIZE - 1) // BATCH_SIZE

    matched: list[DiscoveredRole] = list(resume_kept or [])

    if resume_batches > 0:
        console.print(
            f"\nResuming filter from batch {resume_batches + 1}/{total_batches} "
            f"({len(matched)} roles matched so far)..."
        )
    else:
        console.print(f"\nFiltering [bold]{len(roles)}[/bold] roles with: {filter_desc}")

    start_offset = resume_batches * BATCH_SIZE

    for batch_start in range(start_offset, len(roles), BATCH_SIZE):
        batch = roles[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1

        with console.status(
            f"  Batch {batch_num}/{total_batches} ({len(batch)} roles)..."
        ):
            prompt = _build_prompt(batch, filters)
            try:
                indices = _call_llm(prompt, filters, config)
            except RateLimitError as exc:
                # Checkpoint progress before propagating so the caller can resume
                if checkpoint:
                    checkpoint.save_filter_batch(batch_num - 1, matched)
                raise RateLimitError(
                    f"Rate limit hit at filter batch {batch_num}/{total_batches}. "
                    f"{len(matched)} roles matched so far. "
                    f"Progress saved — use 'Continue from previous run' to resume."
                ) from exc

        for i in indices:
            if 0 <= i < len(batch):
                matched.append(batch[i])

        # Save progress after each successful batch
        if checkpoint:
            checkpoint.save_filter_batch(batch_num, matched)

    return matched
