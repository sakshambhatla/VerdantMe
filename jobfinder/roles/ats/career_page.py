from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from jobfinder.config import AppConfig
from jobfinder.storage.schemas import DiscoveredRole

_MAX_HTML_CHARS = 80_000  # truncate large pages to stay within token limits

_SYSTEM_PROMPT = """\
You are a job listing extractor. Given HTML content from a company's career page, \
extract all visible job postings and return ONLY a JSON array where each element has:
  - title:      job title (string)
  - location:   location or "Remote" (string)
  - url:        full URL to the job posting (string, empty string if not found)
  - department: department or team (string or null)

If you cannot find any job listings — because the page requires login, is \
JavaScript-rendered with no visible content, or simply has no open roles — \
return an empty array: []

Return ONLY the JSON array. No markdown fences, no explanation."""


def fetch_career_page_roles(
    company_name: str,
    career_page_url: str,
    config: AppConfig,
) -> list[DiscoveredRole]:
    """Fetch roles from a career page by parsing its HTML with an LLM.

    Returns an empty list if the page is unreachable, JS-only, or has no jobs.
    Never raises — callers rely on empty list as the failure signal.
    """
    html = _fetch_html(career_page_url, timeout=config.request_timeout)
    if html is None:
        return []
    raw_text = _call_llm(html, config)
    return _parse_roles(raw_text, company_name)


# ── internal helpers ────────────────────────────────────────────────────────


def _fetch_html(url: str, timeout: int) -> str | None:
    """GET the career page and return its text content, or None on failure."""
    import httpx

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "Mozilla/5.0 JobFinder/1.0"})
            if r.status_code >= 400:
                return None
            return r.text[:_MAX_HTML_CHARS]
    except Exception:
        return None


def _call_llm(html: str, config: AppConfig) -> str:
    if config.model_provider == "gemini":
        return _call_gemini(html, config)
    return _call_anthropic(html, config)


def _call_anthropic(html: str, config: AppConfig) -> str:
    from jobfinder.utils.throttle import get_limiter

    get_limiter(config.rpm_limit).wait()

    import anthropic

    client = anthropic.Anthropic()
    result = client.messages.create(
        model=config.anthropic_model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Extract job listings from this career page HTML:\n\n{html}",
            }
        ],
    )
    return result.content[0].text  # type: ignore[union-attr]


def _call_gemini(html: str, config: AppConfig) -> str:
    from jobfinder.utils.throttle import get_limiter

    get_limiter(config.rpm_limit).wait()

    import os

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=config.gemini_model,
        contents=f"Extract job listings from this career page HTML:\n\n{html}",
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
    )
    return response.text or ""


def _parse_roles(raw_text: str, company_name: str) -> list[DiscoveredRole]:
    """Parse LLM JSON output into DiscoveredRole objects."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?\s*```$", "", cleaned)

    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        return []

    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return []

    fetched_at = datetime.now(timezone.utc).isoformat()
    roles: list[DiscoveredRole] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        roles.append(
            DiscoveredRole(
                company_name=company_name,
                title=item.get("title", ""),
                location=item.get("location") or "Unknown",
                url=item.get("url") or "",
                department=item.get("department") or None,
                ats_type="career_page",
                fetched_at=fetched_at,
            )
        )
    return roles
