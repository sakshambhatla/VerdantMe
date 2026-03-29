from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone

from jobfinder.companies.prompts import (
    SEED_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_seed_user_prompt,
    build_user_prompt,
)
from jobfinder.config import AppConfig
from jobfinder.storage.schemas import DiscoveredCompany
from jobfinder.utils.http import head_ok

_BATCH_SIZE = 20   # companies per LLM call — safe within max_tokens=4096
_MAX_BATCHES = 5   # hard cap: at most 100 companies total
_VALIDATION_TIMEOUT = 5  # seconds; HEAD requests should respond fast
_VALIDATION_WORKERS = 10  # parallel threads for company URL validation


def discover_companies(
    resumes: list[dict],
    config: AppConfig,
    *,
    seed_companies: list[str] | None = None,
    api_key: str | None = None,
    motivation_summary: str | None = None,
) -> list[DiscoveredCompany]:
    """Discover companies in batches to avoid LLM response truncation.

    Each batch requests up to _BATCH_SIZE companies and passes already-found
    names as exclusions so the model doesn't repeat them. Stops early when
    the model returns no new companies or max_companies is reached.
    """
    from jobfinder.utils.log_stream import log

    num_batches = min(_MAX_BATCHES, math.ceil(config.max_companies / _BATCH_SIZE))

    all_companies: list[DiscoveredCompany] = []
    seen_names: set[str] = set()

    for batch_num in range(num_batches):
        remaining = config.max_companies - len(all_companies)
        if remaining <= 0:
            break

        batch_size = min(_BATCH_SIZE, remaining)
        exclude = list(seen_names)

        if num_batches > 1:
            log(
                f"  [dim]Batch {batch_num + 1}/{num_batches} "
                f"(requesting {batch_size}, {len(all_companies)} found so far)[/dim]"
            )

        if config.model_provider == "gemini":
            raw_text = _call_gemini(
                resumes, config,
                seed_companies=seed_companies,
                batch_size=batch_size,
                exclude_names=exclude,
                api_key=api_key,
                motivation_summary=motivation_summary,
            )
        else:
            raw_text = _call_anthropic(
                resumes, config,
                seed_companies=seed_companies,
                batch_size=batch_size,
                exclude_names=exclude,
                api_key=api_key,
                motivation_summary=motivation_summary,
            )

        try:
            batch = _parse_response(raw_text)
        except ValueError:
            # LLM returned non-JSON text — retry the batch once
            log(
                f"  [yellow]Model returned non-JSON response — retrying batch {batch_num + 1}…[/yellow]",
                level="warning",
            )
            if config.model_provider == "gemini":
                raw_text = _call_gemini(
                    resumes, config,
                    seed_companies=seed_companies,
                    batch_size=batch_size,
                    exclude_names=exclude,
                    api_key=api_key,
                    motivation_summary=motivation_summary,
                )
            else:
                raw_text = _call_anthropic(
                    resumes, config,
                    seed_companies=seed_companies,
                    batch_size=batch_size,
                    exclude_names=exclude,
                    api_key=api_key,
                    motivation_summary=motivation_summary,
                )
            batch = _parse_response(raw_text)  # let it raise on second failure

        new = [c for c in batch if c.name.lower() not in seen_names]

        if not new:
            log(
                f"  [dim]No new companies in batch {batch_num + 1} — stopping early[/dim]"
            )
            break

        seen_names.update(c.name.lower() for c in new)
        all_companies.extend(new)

    _validate_companies(all_companies, timeout=_VALIDATION_TIMEOUT)

    now = datetime.now(timezone.utc).isoformat()
    for c in all_companies:
        c.discovered_at = now

    return all_companies


def _call_anthropic(
    resumes: list[dict],
    config: AppConfig,
    *,
    seed_companies: list[str] | None = None,
    batch_size: int = _BATCH_SIZE,
    exclude_names: list[str] | None = None,
    api_key: str | None = None,
    motivation_summary: str | None = None,
) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    import anthropic

    client = anthropic.Anthropic(**({"api_key": api_key} if api_key else {}))
    if seed_companies:
        system = SEED_SYSTEM_PROMPT
        user_prompt = build_seed_user_prompt(
            seed_companies, batch_size,
            exclude_names=exclude_names, motivation_summary=motivation_summary,
        )
    else:
        system = SYSTEM_PROMPT
        user_prompt = build_user_prompt(
            resumes, batch_size,
            exclude_names=exclude_names, motivation_summary=motivation_summary,
        )

    print()  # blank line before stream
    chunks: list[str] = []
    with client.messages.stream(
        model=config.anthropic_model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            chunks.append(text)
    print("\n")  # blank line after stream
    return "".join(chunks)


def _call_gemini(
    resumes: list[dict],
    config: AppConfig,
    *,
    seed_companies: list[str] | None = None,
    batch_size: int = _BATCH_SIZE,
    exclude_names: list[str] | None = None,
    api_key: str | None = None,
    motivation_summary: str | None = None,
    _attempt: int = 0,
) -> str:
    import time

    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError

    from jobfinder.utils.log_stream import log as _log

    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
    if seed_companies:
        system = SEED_SYSTEM_PROMPT
        user_prompt = build_seed_user_prompt(
            seed_companies, batch_size,
            exclude_names=exclude_names, motivation_summary=motivation_summary,
        )
    else:
        system = SYSTEM_PROMPT
        user_prompt = build_user_prompt(
            resumes, batch_size,
            exclude_names=exclude_names, motivation_summary=motivation_summary,
        )

    print()  # blank line before stream
    chunks: list[str] = []
    try:
        for chunk in client.models.generate_content_stream(
            model=config.gemini_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
            ),
        ):
            if chunk.text:
                print(chunk.text, end="", flush=True)
                chunks.append(chunk.text)
    except ClientError as exc:
        if getattr(exc, "code", None) == 429:
            from jobfinder.utils.gemini_errors import log_gemini_429

            from jobfinder.utils.display import console
            summary, is_daily, retry_wait = log_gemini_429(
                exc, config.gemini_model, config.debug, console
            )
            if not is_daily and _attempt < 3:
                _log(
                    f"[yellow]  Retrying in {retry_wait}s ({_attempt + 1}/3)...[/yellow]",
                    level="warning",
                )
                time.sleep(retry_wait)
                return _call_gemini(
                    resumes, config,
                    seed_companies=seed_companies,
                    batch_size=batch_size,
                    exclude_names=exclude_names,
                    api_key=api_key,
                    motivation_summary=motivation_summary,
                    _attempt=_attempt + 1,
                )

            tip = (
                "Daily quota resets at midnight Pacific. Try gemini_model='gemini-2.0-flash' or model_provider='anthropic'."
                if is_daily
                else "Per-minute retries exhausted. Try model_provider='anthropic'."
            )
            raise RuntimeError(f"{summary}\n{tip}") from exc
        raise
    print("\n")  # blank line after stream
    return "".join(chunks)


_ATS_CHECK_URLS: dict[str, str] = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
}

# Probe order for ATS auto-detection (most to least common)
_ATS_PROBE_ORDER = ["greenhouse", "lever", "ashby"]


def _name_to_slug(name: str) -> str:
    """Convert a company name to a likely ATS board slug.

    Examples: "Postman" → "postman", "Scale AI" → "scale-ai"
    """
    slug = name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _validate_one(c: DiscoveredCompany, timeout: int) -> None:
    """Validate a single company's career_page_url and ats_board_token in place."""
    from jobfinder.utils.log_stream import log

    if c.career_page_url:
        if not head_ok(c.career_page_url, timeout=timeout):
            log(
                f"  [yellow]⚠[/yellow] {c.name}: career_page_url unreachable — cleared",
                level="warning",
            )
            c.career_page_url = ""

    if c.ats_type in _ATS_CHECK_URLS and c.ats_board_token:
        check_url = _ATS_CHECK_URLS[c.ats_type].format(token=c.ats_board_token)
        if not head_ok(check_url, timeout=timeout):
            log(
                f"  [yellow]⚠[/yellow] {c.name}: ats_board_token "
                f"'{c.ats_board_token}' not found on {c.ats_type} — cleared",
                level="warning",
            )
            c.ats_board_token = None

    # Auto-detect ATS for unknown/unresolved companies
    if c.ats_type == "unknown" or not c.ats_board_token:
        slug = _name_to_slug(c.name)
        detected = False
        for ats_name in _ATS_PROBE_ORDER:
            probe_url = _ATS_CHECK_URLS[ats_name].format(token=slug)
            if head_ok(probe_url, timeout=timeout):
                c.ats_type = ats_name
                c.ats_board_token = slug
                log(
                    f"  [green]✓[/green] {c.name}: auto-detected as {ats_name} "
                    f"(token: {slug!r})",
                    level="success",
                )
                detected = True
                break
        if not detected and c.ats_type == "unknown":
            log(
                f"  [dim]{c.name}: ATS not auto-detected — will try career page[/dim]"
            )


def _validate_companies(companies: list[DiscoveredCompany], timeout: int = 10) -> None:
    """Validate career_page_url and ats_board_token in place; log warnings for failures.

    Runs validation for all companies in parallel using a thread pool to avoid
    sequential HEAD-request latency (which caused timeouts on large seed lists).

    Also auto-detects ATS for companies with ats_type == 'unknown' or missing board token
    by probing Greenhouse → Lever → Ashby with a slug derived from the company name.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from jobfinder.utils.log_stream import log

    log(f"  [dim]Validating {len(companies)} companies ({_VALIDATION_WORKERS} workers, {timeout}s timeout)...[/dim]")

    with ThreadPoolExecutor(max_workers=_VALIDATION_WORKERS) as pool:
        futures = {pool.submit(_validate_one, c, timeout): c for c in companies}
        for future in as_completed(futures):
            future.result()  # propagate any unexpected exceptions


def _parse_response(raw_text: str) -> list[DiscoveredCompany]:
    """Parse a JSON array of companies from an LLM response."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?\s*```$", "", cleaned)

    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(
            f"Could not find JSON array in model response:\n{raw_text[:500]}"
        )

    data = json.loads(cleaned[start : end + 1])
    return [DiscoveredCompany.model_validate(item) for item in data]
