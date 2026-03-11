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

Do not invent or construct URLs. Only include the exact href values that are explicitly \
present as hyperlinks in the HTML. If a job listing has no visible link, use an empty \
string for url.

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

    Uses Playwright (headless browser) to render JS SPAs when available, falling
    back to a plain httpx GET. Respects robots.txt and handles rate-limiting.

    Returns an empty list if the page is unreachable, JS-only, or has no jobs.
    Never raises — callers rely on empty list as the failure signal.
    """
    from jobfinder.utils.display import console

    html = _fetch_html_playwright(career_page_url, timeout=config.request_timeout)
    if html is None:
        console.print(
            f"  [dim]Career page unreachable: {career_page_url}[/dim]"
        )
        return []
    raw_text = _call_llm(html, config)
    roles = _parse_roles(raw_text, company_name)
    if roles:
        validated = _validate_role_urls(roles, config.request_timeout)
        dropped = len(roles) - len(validated)
        if dropped:
            console.print(
                f"  [dim]URL validation: {len(validated)} kept, {dropped} dropped[/dim]"
            )
        return validated
    return roles


# ── robots.txt helper ────────────────────────────────────────────────────────


def _is_allowed_by_robots(url: str) -> bool:
    """Return True if our crawler is allowed to fetch *url* per robots.txt.

    Fetches robots.txt with a short timeout; fails open (returns True) on any
    error so a broken or missing robots.txt never blocks crawling.
    """
    try:
        import httpx
        from urllib.parse import urlparse
        from urllib.robotparser import RobotFileParser

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        try:
            with httpx.Client(timeout=5, follow_redirects=True) as client:
                r = client.get(
                    robots_url,
                    headers={"User-Agent": "Mozilla/5.0 JobFinder/1.0"},
                )
                if r.status_code != 200:
                    return True  # no robots.txt → allow
                rp = RobotFileParser()
                rp.parse(r.text.splitlines())
        except Exception:
            return True  # can't reach robots.txt → allow

        # Check both our specific agent name and the wildcard
        return rp.can_fetch("JobFinder", url) or rp.can_fetch("*", url)
    except Exception:
        return True  # fail open


# ── HTML fetch helpers ───────────────────────────────────────────────────────


def _fetch_html(url: str, timeout: int) -> str | None:
    """GET the career page with httpx and return its text content, or None on failure.

    Logs a warning for HTTP 429 (rate limited) responses so callers know why
    the fetch failed rather than just seeing an empty result.
    """
    import httpx
    from jobfinder.utils.display import console

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "Mozilla/5.0 JobFinder/1.0"})
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After", "unknown")
                console.print(
                    f"  [yellow]⚠ Career page rate-limited (429) — "
                    f"Retry-After: {retry_after}: {url}[/yellow]"
                )
                return None
            if r.status_code >= 400:
                return None
            return r.text[:_MAX_HTML_CHARS]
    except Exception:
        return None


def _fetch_html_playwright(url: str, timeout: int) -> str | None:
    """Render the career page with a headless Chromium browser.

    Falls back to a plain :func:`_fetch_html` httpx GET when Playwright is not
    installed.  Respects robots.txt and logs a warning for rate-limited (429)
    or timed-out responses.
    """
    from jobfinder.utils.display import console

    # Robots.txt check applies to both playwright and httpx paths
    if not _is_allowed_by_robots(url):
        console.print(f"  [dim]robots.txt disallows crawling: {url}[/dim]")
        return None

    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def _render() -> str | None:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_extra_http_headers(
                    {"User-Agent": "Mozilla/5.0 JobFinder/1.0"}
                )
                try:
                    response = await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=timeout * 1_000,
                    )
                    if response is not None:
                        if response.status == 429:
                            retry_after = response.headers.get(
                                "retry-after", "unknown"
                            )
                            console.print(
                                f"  [yellow]⚠ Career page rate-limited (429) — "
                                f"Retry-After: {retry_after}: {url}[/yellow]"
                            )
                            await browser.close()
                            return None
                        if response.status >= 400:
                            await browser.close()
                            return None
                    content = await page.content()
                except Exception as exc:
                    console.print(
                        f"  [yellow]⚠ Playwright timeout/error for {url}: {exc}[/yellow]"
                    )
                    await browser.close()
                    return None
                await browser.close()
                return content[:_MAX_HTML_CHARS]

        return asyncio.run(_render())

    except ImportError:
        console.print("  [dim]playwright not installed — using httpx fallback[/dim]")
        return _fetch_html(url, timeout)
    except Exception as exc:
        console.print(f"  [dim]Playwright error for {url}: {exc}[/dim]")
        return None


# ── Browser-use agent path ───────────────────────────────────────────────────


def _build_browser_llm(config: AppConfig):
    """Build a browser-use native LLM from the app config.

    browser-use 0.12+ ships its own LLM wrappers under ``browser_use.llm``
    and no longer requires LangChain as a bridge.
    """
    if config.model_provider == "gemini":
        import os
        from browser_use.llm.google.chat import ChatGoogle  # type: ignore

        return ChatGoogle(
            model=config.gemini_model,
            api_key=os.environ.get("GEMINI_API_KEY"),
        )
    else:
        from browser_use.llm.anthropic.chat import ChatAnthropic  # type: ignore

        return ChatAnthropic(model=config.anthropic_model)


async def _run_browser_agent(
    company_name: str,
    url: str,
    config: AppConfig,
) -> str:
    """Run a browser-use Agent to extract job listings from *url*.

    The agent navigates pagination, search bars, and filters autonomously.
    Returns a JSON string (may be empty or malformed on failure).
    """
    from browser_use import Agent  # type: ignore

    llm = _build_browser_llm(config)
    task = (
        f"Go to {url}. This is the careers/jobs page for {company_name}. "
        f"Extract ALL job listings from this page. Navigate through pagination "
        f"(Next buttons, page numbers, Load More buttons), apply any relevant "
        f"category or location filters if needed, and keep going until you have "
        f"seen every available role. "
        f"Return ONLY a JSON array where each item has exactly these keys: "
        f"title (string), location (string or 'Remote'), "
        f"url (full absolute URL to the job posting, or empty string if none), "
        f"department (string or null). "
        f"Do not include any markdown fences or explanations — just the raw JSON array."
    )
    agent = Agent(task=task, llm=llm)
    result = await agent.run(max_steps=50)
    return result.final_result() or ""


def fetch_career_page_roles_browser(
    company_name: str,
    career_page_url: str,
    config: AppConfig,
) -> list[DiscoveredRole]:
    """Full browser-use agent fetch — handles pagination, filters, and interactive pages.

    Raises :class:`RuntimeError` if browser-use is not installed so callers can
    surface a clear install instruction.  All other exceptions are caught, logged,
    and converted to an empty list.
    """
    import asyncio
    from jobfinder.utils.display import console

    # Validate robots.txt before invoking the agent
    if not _is_allowed_by_robots(career_page_url):
        console.print(
            f"  [dim]robots.txt disallows browser agent for: {career_page_url}[/dim]"
        )
        return []

    try:
        import browser_use  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "browser-use not installed. "
            "Run: pip install browser-use langchain-anthropic langchain-google-genai"
        )

    console.print(
        f"  Starting browser agent for [bold]{company_name}[/bold] → {career_page_url}"
    )

    try:
        raw = asyncio.run(_run_browser_agent(company_name, career_page_url, config))
    except Exception as exc:
        console.print(
            f"  [red]Browser agent error for {company_name}: {exc}[/red]"
        )
        return []

    roles = _parse_roles(raw, company_name)
    console.print(
        f"  [green]Browser agent completed:[/green] "
        f"{len(roles)} roles found for {company_name}"
    )

    if roles:
        validated = _validate_role_urls(roles, config.request_timeout)
        dropped = len(roles) - len(validated)
        if dropped:
            console.print(
                f"  [dim]URL validation: {len(validated)} kept, {dropped} dropped[/dim]"
            )
        return validated
    return roles


# ── LLM call helpers ─────────────────────────────────────────────────────────


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


def _call_gemini(html: str, config: AppConfig, *, _attempt: int = 0) -> str:
    import os
    import time

    from jobfinder.utils.throttle import get_limiter

    get_limiter(config.rpm_limit).wait()

    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError

    from jobfinder.utils.display import console

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    try:
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=f"Extract job listings from this career page HTML:\n\n{html}",
            config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
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
                return _call_gemini(html, config, _attempt=_attempt + 1)
            # Career page is best-effort — treat exhaustion as empty page, never raise
            return ""
        raise
    return response.text or ""


# ── URL validation ───────────────────────────────────────────────────────────


def _validate_role_urls(
    roles: list[DiscoveredRole], timeout: int
) -> list[DiscoveredRole]:
    """HEAD-check all non-empty URLs; drop roles whose URLs return 4xx/5xx or fail."""
    from concurrent.futures import ThreadPoolExecutor

    from jobfinder.utils.http import head_ok

    to_check = [(i, r) for i, r in enumerate(roles) if r.url]
    if not to_check:
        return roles

    cap = min(timeout, 5)
    with ThreadPoolExecutor(max_workers=10) as ex:
        ok_flags = list(ex.map(lambda x: head_ok(x[1].url, cap), to_check))

    valid_indices = {idx for (idx, _), ok in zip(to_check, ok_flags) if ok}
    return [r for i, r in enumerate(roles) if not r.url or i in valid_indices]


# ── Response parser ──────────────────────────────────────────────────────────


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
