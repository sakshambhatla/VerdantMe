from __future__ import annotations

import json
import os

from jobfinder.config import AppConfig, RoleFilters
from jobfinder.storage.schemas import DiscoveredRole
from jobfinder.utils.display import console

BATCH_SIZE = 50

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
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.anthropic_model,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_gemini(prompt: str, system_prompt: str, config: AppConfig) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    response = client.models.generate_content(
        model=config.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
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
) -> list[DiscoveredRole]:
    """Apply LLM-based filters to a list of roles. Returns only high-confidence matches."""
    active = {k: v for k, v in filters.model_dump().items() if v is not None}
    if not active:
        return roles

    filter_desc = ", ".join(f"{k}={v!r}" for k, v in active.items())
    console.print(
        f"\nFiltering [bold]{len(roles)}[/bold] roles with: {filter_desc}"
    )

    matched: list[DiscoveredRole] = []
    for batch_start in range(0, len(roles), BATCH_SIZE):
        batch = roles[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(roles) + BATCH_SIZE - 1) // BATCH_SIZE

        with console.status(
            f"  Batch {batch_num}/{total_batches} ({len(batch)} roles)..."
        ):
            prompt = _build_prompt(batch, filters)
            indices = _call_llm(prompt, filters, config)

        for i in indices:
            if 0 <= i < len(batch):
                matched.append(batch[i])

    return matched
