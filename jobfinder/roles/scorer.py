from __future__ import annotations

import json
import os

from jobfinder.config import AppConfig
from jobfinder.storage.schemas import DiscoveredRole
from jobfinder.utils.display import console

BATCH_SIZE = 30

_SYSTEM_PROMPT = """\
You are a job relevance scorer. Given scoring criteria and a numbered list of job postings,
assign each posting a relevance score from 1 to 10 (10 = most relevant, 1 = least relevant).

Score based solely on how well the posting matches the provided criteria.
Be precise — use the full 1–10 range, not just extremes.

Return ONLY a valid JSON object mapping 0-based index (as string) to score (as integer).
Example: {"0": 9, "1": 3, "2": 7}
No explanation, no markdown.\
"""


def _build_prompt(roles: list[DiscoveredRole], criteria: str) -> str:
    postings = []
    for i, role in enumerate(roles):
        date = role.posted_at or role.published_at or role.updated_at or "no date"
        parts = [
            f"{i}.",
            f"title={role.title!r}",
            f"company={role.company_name!r}",
            f"location={role.location!r}",
            f"date={date!r}",
        ]
        if role.department:
            parts.append(f"dept={role.department!r}")
        postings.append(" | ".join(parts))

    return (
        f"Scoring criteria:\n{criteria}\n\n"
        f"Job postings:\n" + "\n".join(postings)
    )


def _call_anthropic(prompt: str, config: AppConfig) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.anthropic_model,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_gemini(prompt: str, config: AppConfig) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
    response = client.models.generate_content(
        model=config.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
    )
    return response.text


def _call_llm(prompt: str, config: AppConfig) -> dict[int, int]:
    raw = (
        _call_gemini(prompt, config)
        if config.model_provider == "gemini"
        else _call_anthropic(prompt, config)
    )
    raw = raw.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
        return {int(k): max(1, min(10, int(v))) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError):
        return {}


def score_roles(
    roles: list[DiscoveredRole],
    criteria: str,
    config: AppConfig,
) -> list[DiscoveredRole]:
    """Score each role 1–10 for relevance using the LLM, then sort highest-first."""
    console.print(f"\nScoring [bold]{len(roles)}[/bold] roles for relevance...")

    for batch_start in range(0, len(roles), BATCH_SIZE):
        batch = roles[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(roles) + BATCH_SIZE - 1) // BATCH_SIZE

        with console.status(
            f"  Scoring batch {batch_num}/{total_batches} ({len(batch)} roles)..."
        ):
            prompt = _build_prompt(batch, criteria)
            scores = _call_llm(prompt, config)

        for i, role in enumerate(batch):
            if i in scores:
                role.relevance_score = scores[i]

    return sorted(roles, key=lambda r: -(r.relevance_score or 0))
