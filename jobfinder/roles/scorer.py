from __future__ import annotations

import json
import os
import re
import time

from jobfinder.config import AppConfig
from jobfinder.roles.checkpoint import Checkpoint
from jobfinder.roles.errors import RateLimitError
from jobfinder.storage.schemas import DiscoveredRole
from jobfinder.utils.display import console

BATCH_SIZE = 60

_SYSTEM_PROMPT = """\
You are a job relevance scorer. Given scoring criteria and a numbered list of job postings,
assign each posting a relevance score (1–10) and a brief summary of its key differentiators.

Score based solely on how well the posting matches the provided criteria.
Be precise — use the full 1–10 range, not just extremes.

Summary: 1–2 phrases capturing what makes this role distinctive (e.g. team focus, tech stack,
seniority level, domain). Max 15 words. Do NOT repeat the job title.

Return ONLY a valid JSON object mapping 0-based index (as string) to {"score": int, "summary": str}.
Example: {"0": {"score": 9, "summary": "Platform eng, Spark/Flink, 5+ yrs"}, "1": {"score": 3, "summary": "Mobile infra, iOS-heavy"}}
No explanation, no markdown.\
"""


def _build_prompt(roles: list[DiscoveredRole], criteria: str) -> str:
    postings = []
    for i, role in enumerate(roles):
        parts = [
            f"{i}.",
            f"title={role.title!r}",
            f"company={role.company_name!r}",
            f"location={role.location!r}",
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
    try:
        response = client.messages.create(
            model=config.anthropic_model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError as exc:
        raise RateLimitError(str(exc)) from exc
    return response.content[0].text


def _call_gemini(prompt: str, config: AppConfig, *, _attempt: int = 0) -> str:
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
            config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
        )
    except ClientError as exc:
        if getattr(exc, "code", None) == 429:
            detail = str(exc)
            console.print(f"[yellow]  Gemini 429 detail: {detail}[/yellow]")
            dl = detail.lower()

            is_daily = "perday" in dl or "per_day" in dl
            is_per_minute = "perminute" in dl or "per_minute" in dl

            if is_per_minute and not is_daily and _attempt < 3:
                m = re.search(r"retry in ([\d.]+)s", dl)
                wait = int(float(m.group(1))) + 5 if m else 65
                console.print(
                    f"[yellow]  RPM limit — waiting {wait}s, retry {_attempt + 1}/3...[/yellow]"
                )
                time.sleep(wait)
                return _call_gemini(prompt, config, _attempt=_attempt + 1)

            if is_daily:
                tip = "Daily quota resets at midnight Pacific. Try again tomorrow, or set gemini_model='gemini-2.0-flash' / model_provider='anthropic' in config.json."
                quota_type = "daily quota"
            elif is_per_minute:
                tip = "Per-minute retries exhausted. Set gemini_model='gemini-2.0-flash' or model_provider='anthropic' in config.json."
                quota_type = "per-minute limit"
            else:
                tip = "Check your quota at https://ai.dev/rate-limit."
                quota_type = "quota"

            raise RateLimitError(
                f"Gemini {quota_type} exceeded.\n{tip}"
            ) from exc
        raise
    return response.text


def _call_llm(prompt: str, config: AppConfig) -> dict[int, dict]:
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
        result: dict[int, dict] = {}
        for k, v in data.items():
            idx = int(k)
            if isinstance(v, dict):
                score = max(1, min(10, int(v.get("score", 5))))
                summary = str(v.get("summary", "")).strip() or None
                result[idx] = {"score": score, "summary": summary}
            elif isinstance(v, (int, float)):
                # Graceful fallback if LLM omits summary
                result[idx] = {"score": max(1, min(10, int(v))), "summary": None}
        return result
    except (json.JSONDecodeError, ValueError):
        return {}


def score_roles(
    roles: list[DiscoveredRole],
    criteria: str,
    config: AppConfig,
    *,
    checkpoint: Checkpoint | None = None,
    resume_batches: int = 0,
) -> list[DiscoveredRole]:
    """Score each role 1–10 and generate a summary, then sort highest-first.

    Args:
        roles: Roles to score (typically already filtered).
        criteria: Free-text description of what makes a role relevant.
        config: App configuration (model provider, etc.).
        checkpoint: If set, saves progress after each batch so the run can be resumed.
        resume_batches: Number of already-scored batches to skip (used when resuming).
    """
    total_batches = (len(roles) + BATCH_SIZE - 1) // BATCH_SIZE

    if resume_batches > 0:
        console.print(
            f"\nResuming scoring from batch {resume_batches + 1}/{total_batches}..."
        )
    else:
        console.print(f"\nScoring [bold]{len(roles)}[/bold] roles for relevance...")

    start_offset = resume_batches * BATCH_SIZE

    for batch_start in range(start_offset, len(roles), BATCH_SIZE):
        batch = roles[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1

        with console.status(
            f"  Scoring batch {batch_num}/{total_batches} ({len(batch)} roles)..."
        ):
            prompt = _build_prompt(batch, criteria)
            try:
                scores = _call_llm(prompt, config)
            except RateLimitError as exc:
                # Checkpoint with whatever has been scored so far before propagating
                if checkpoint:
                    checkpoint.save_score_batch(batch_num - 1, roles, total_batches)
                raise RateLimitError(
                    f"Rate limit hit at scoring batch {batch_num}/{total_batches}. "
                    f"Progress saved — use 'Continue from previous run' to resume."
                ) from exc

        for i, role in enumerate(batch):
            if i in scores:
                role.relevance_score = scores[i]["score"]
                role.summary = scores[i].get("summary")

        # Save progress after each successful batch
        if checkpoint:
            checkpoint.save_score_batch(batch_num, roles, total_batches)

    return sorted(roles, key=lambda r: -(r.relevance_score or 0))
