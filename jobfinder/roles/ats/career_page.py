from __future__ import annotations

# VerdantMe Browser Agent — rev vm-6m3p8d-2026.03
_VERDANTME_AGENT_REV = "vm-6m3p8d-2026.03"

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
            f"  [dim]Career page not loaded — skipping LLM extraction "
            f"for {career_page_url}[/dim]"
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
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        # Stability in sandboxed / CI environments
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                page = await browser.new_page(
                    viewport={"width": 1280, "height": 800},
                )
                await page.set_extra_http_headers(
                    {
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/122.0.0.0 Safari/537.36"
                        )
                    }
                )
                try:
                    response = await page.goto(
                        url,
                        # "domcontentloaded" is reliable on chatty sites (Apple,
                        # Netflix, Discord, Roblox…) that never reach networkidle
                        # because of continuous telemetry/analytics traffic.
                        wait_until="domcontentloaded",
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
                    # Brief pause for JS-rendered content (SPAs hydrate after DCL)
                    await page.wait_for_timeout(1_500)
                    content = await page.content()
                except Exception as exc:
                    console.print(
                        f"  [yellow]⚠ Playwright timed out rendering {url}: {exc}[/yellow]"
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


# ── Browser-use LLM builder ──────────────────────────────────────────────────


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
        import os
        from browser_use.llm.anthropic.chat import ChatAnthropic  # type: ignore

        return ChatAnthropic(model=config.anthropic_model, api_key=os.environ.get("ANTHROPIC_API_KEY"))


# ── Task prompt builder ──────────────────────────────────────────────────────


def _build_task_prompt(
    company_name: str,
    url: str,
    profile: dict | None,
    config: AppConfig,
) -> str:
    """Build the browser-use agent task string.

    When a known API profile exists for the domain, the endpoint is injected so
    the agent skips re-discovery and goes straight to extraction.
    """
    api_hint = ""
    if profile and profile.get("endpoints"):
        ep = profile["endpoints"][0]
        rpm = ep.get("rate_limit_rpm_observed", 3)
        method = ep.get("method", "GET")
        path = ep.get("path", "")
        api_hint = (
            f"KNOWN API: {method} {path} (observed rate limit: ~{rpm} req/min). "
            f"Use this endpoint directly — skip manual page navigation. "
        )

    # Build filter hint when the user has configured role_filters.
    filter_hint = ""
    if config.role_filters:
        f = config.role_filters
        parts = []
        if f.title:
            parts.append(
                f'job title/type "{f.title}" — use the site\'s search bar or category filter'
            )
        if f.location:
            parts.append(
                f'location "{f.location}" — use the site\'s location filter if available'
            )
        if f.posted_after:
            parts.append(
                f'posted after {f.posted_after} — use the date-posted filter if available'
            )
        if parts:
            filter_hint = (
                "APPLY THESE FILTERS FIRST using the site's own search/filter UI before "
                "collecting results — this will significantly narrow the total roles: "
                + "; ".join(parts)
                + ". "
            )

    rate_hint = (
        f"If you encounter rate limiting (HTTP 429 or messages like 'Please rel...'), "
        f"wait {config.browser_agent_rate_limit_initial_wait}s then double the wait "
        f"each consecutive failure. Give up after "
        f"{config.browser_agent_rate_limit_max_retries} consecutive failures. "
    )

    efficiency_hint = (
        "EFFICIENCY RULES: "
        "Extract visible jobs from the DOM on the first page immediately — "
        "don't spend more than 2–3 steps trying to find a bulk API endpoint before "
        "falling back to page-by-page DOM extraction. "
        "If a JavaScript fetch() fails with a CORS or network error, do NOT retry "
        "the same approach with minor variations — move on to DOM extraction or "
        "direct browser navigation instead. "
        "If the site shows hundreds or thousands of results, use the site's own "
        "search/filter UI to narrow the listing before paginating. "
    )

    return (
        f"Go to {url}. This is the careers/jobs page for {company_name}. "
        f"{api_hint}"
        f"{filter_hint}"
        f"Extract ALL matching job listings from this page. Navigate through pagination "
        f"(Next buttons, page numbers, Load More buttons) and keep going until you have "
        f"seen every available role. "
        f"{efficiency_hint}"
        f"{rate_hint}"
        f"Return ONLY a JSON array where each item has exactly these keys: "
        f"title (string), location (string or 'Remote'), "
        f"url (full absolute URL to the job posting, or empty string if none), "
        f"department (string or null). "
        f"Do not include any markdown fences or explanations — just the raw JSON array."
    )


# ── Streaming LLM wrapper ────────────────────────────────────────────────────


class _StreamingLLMWrapper:
    """Wraps a browser-use LLM to stream intermediate job batches.

    Every time the underlying LLM responds, we scan the text for a JSON array
    that looks like a job listing batch (objects with ``title`` keys).  Any new
    jobs found (deduped by URL) are posted to the ``AgentSession.event_queue``
    immediately so the SSE generator can stream them to the UI before the full
    agent run completes.
    """

    def __init__(self, base_llm, session) -> None:  # session: AgentSession
        self._llm = base_llm
        self._session = session
        self._seen_urls: set[str] = set()

    def __getattr__(self, name: str):
        return getattr(self._llm, name)

    async def ainvoke(self, messages, *args, **kwargs):
        response = await self._llm.ainvoke(messages, *args, **kwargs)
        self._maybe_emit_jobs(str(getattr(response, "content", "")))
        return response

    # Some browser-use code paths call invoke() synchronously
    def invoke(self, messages, *args, **kwargs):
        response = self._llm.invoke(messages, *args, **kwargs)
        self._maybe_emit_jobs(str(getattr(response, "content", "")))
        return response

    def _maybe_emit_jobs(self, text: str) -> None:
        """Extract jobs from *text* and post new ones to the session event queue."""
        raw_jobs = _try_extract_job_dicts(text)
        new_jobs = [j for j in raw_jobs if j.get("url") not in self._seen_urls]
        if not new_jobs:
            return
        self._seen_urls.update(j.get("url", "") for j in new_jobs)
        self._session.partial_roles.extend(new_jobs)
        self._session.metrics.jobs_collected = len(self._session.partial_roles)
        try:
            self._session.event_queue.put_nowait({
                "type": "jobs_batch",
                "jobs": new_jobs,
                "total_so_far": len(self._session.partial_roles),
            })
        except Exception:
            pass  # queue full — drop; SSE generator drains asynchronously


# ── Streaming agent runner (API path) ────────────────────────────────────────


async def _run_with_kill_check(agent, session, max_steps: int):
    """Run ``agent.run(max_steps)`` but cancel if ``session.kill_event`` fires.

    ``agent.run()`` is launched as an independent ``asyncio.Task`` so it can be
    cancelled from outside.  When our own coroutine is cancelled (e.g. by
    ``asyncio.wait_for`` firing its timeout), we must explicitly cancel
    ``run_task`` too — otherwise it becomes an orphaned task that keeps running
    after the caller has already emitted a ``killed`` event to the UI.
    """
    import asyncio

    run_task = asyncio.create_task(agent.run(max_steps=max_steps))
    try:
        while not run_task.done():
            if session.kill_event.is_set():
                run_task.cancel()
                break
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        # Parent cancelled (e.g. asyncio.wait_for timeout) — stop the agent task.
        if not run_task.done():
            run_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(run_task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        raise
    try:
        return await run_task
    except asyncio.CancelledError:
        raise


async def _run_browser_agent_streaming(
    company_name: str,
    career_page_url: str,
    config: AppConfig,
    session,  # AgentSession
    store,    # StorageBackend
) -> None:
    """Run the browser-use agent with live streaming to *session*.

    Posts SSE events to ``session.event_queue``:

    - ``jobs_batch``  — whenever new jobs are found (via LLM wrapper interception)
    - ``done``        — on clean completion
    - ``killed``      — on time-limit or user kill
    - ``error``       — on unexpected exception

    This is the **API path** called from the SSE route.  The CLI still uses the
    synchronous :func:`fetch_career_page_roles_browser` wrapper below.
    """
    import asyncio
    from jobfinder.utils.display import console
    from jobfinder.storage.api_profiles import load_profile

    known_profile = load_profile(career_page_url, store)
    base_llm = _build_browser_llm(config)
    wrapped_llm = _StreamingLLMWrapper(base_llm, session)
    task_prompt = _build_task_prompt(company_name, career_page_url, known_profile, config)

    try:
        from browser_use import Agent  # type: ignore
    except ImportError:
        await session.event_queue.put({
            "type": "error",
            "error_type": "not_installed",
            "message": (
                "browser-use not installed. "
                "Run: pip install browser-use langchain-anthropic langchain-google-genai"
            ),
            "can_resume": False,
        })
        return

    agent = Agent(task=task_prompt, llm=wrapped_llm)
    max_seconds = config.browser_agent_max_time_minutes * 60

    console.print(
        f"  Starting streaming browser agent for [bold]{company_name}[/bold] → {career_page_url}"
    )

    try:
        result = await asyncio.wait_for(
            _run_with_kill_check(agent, session, config.browser_agent_max_steps),
            timeout=max_seconds,
        )

        # Parse final result — catches anything the LLM wrapper may have missed
        final_raw = (result.final_result() or "") if result else ""
        final_dicts = _try_extract_job_dicts(final_raw)
        existing_urls = {r.get("url", "") for r in session.partial_roles}
        new_final = [j for j in final_dicts if j.get("url") not in existing_urls]
        if new_final:
            session.partial_roles.extend(new_final)
            session.metrics.jobs_collected = len(session.partial_roles)
            await session.event_queue.put({
                "type": "jobs_batch",
                "jobs": new_final,
                "total_so_far": len(session.partial_roles),
            })

        # Persist API profile if the agent embedded one
        _maybe_save_api_profile(final_raw, career_page_url, company_name, store)

        session.metrics.status = "done"
        console.print(
            f"  [green]Browser agent completed:[/green] "
            f"{session.metrics.jobs_collected} roles for {company_name}"
        )
        await session.event_queue.put({
            "type": "done",
            "metrics": session.metrics.to_dict(),
        })

    except asyncio.TimeoutError:
        session.metrics.status = "killed"
        console.print(
            f"  [yellow]Browser agent time limit ({config.browser_agent_max_time_minutes} min) "
            f"reached for {company_name}[/yellow]"
        )
        await session.event_queue.put({
            "type": "killed",
            "reason": "time_limit",
            "partial_jobs": len(session.partial_roles),
            "metrics": session.metrics.to_dict(),
        })

    except asyncio.CancelledError:
        session.metrics.status = "killed"
        console.print(
            f"  [yellow]Browser agent cancelled by user for {company_name}[/yellow]"
        )
        await session.event_queue.put({
            "type": "killed",
            "reason": "user_request",
            "partial_jobs": len(session.partial_roles),
            "metrics": session.metrics.to_dict(),
        })

    except Exception as exc:
        session.metrics.status = "error"
        session.metrics.errors.append(str(exc))
        console.print(f"  [red]Browser agent error for {company_name}: {exc}[/red]")
        await session.event_queue.put({
            "type": "error",
            "error_type": "agent_error",
            "message": str(exc),
            "can_resume": False,
            "metrics": session.metrics.to_dict(),
        })


# ── Sync wrapper (CLI path) ──────────────────────────────────────────────────


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
    task = _build_task_prompt(company_name, url, None, config)
    agent = Agent(task=task, llm=llm)
    result = await agent.run(max_steps=config.browser_agent_max_steps)
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


# ── Response parsers ─────────────────────────────────────────────────────────


def _try_extract_job_dicts(text: str) -> list[dict]:
    """Extract the first valid JSON array of job-like dicts from *text*.

    Used by both :func:`_parse_roles` and :class:`_StreamingLLMWrapper` to pull
    partial results from LLM step responses.  Returns [] if nothing found.
    """
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?\s*```$", "", cleaned)

    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        return []

    try:
        data = json.loads(cleaned[start: end + 1])
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    return [item for item in data if isinstance(item, dict) and item.get("title")]


def _parse_roles(raw_text: str, company_name: str) -> list[DiscoveredRole]:
    """Parse LLM JSON output into DiscoveredRole objects."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    roles: list[DiscoveredRole] = []
    for item in _try_extract_job_dicts(raw_text):
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


def _maybe_save_api_profile(
    agent_output: str,
    career_page_url: str,
    company_name: str,
    store,  # StorageBackend
) -> None:
    """If the agent embedded API profile metadata in its output, persist it.

    The browser-use agent returns a JSON array of job objects.  When it also
    discovers an internal API, it may emit a JSON object with an
    ``api_discovered`` key.  We extract and save that to ``api_profiles.json``.
    """
    try:
        data = json.loads(agent_output.strip())
        if isinstance(data, dict) and "api_discovered" in data:
            profile = data["api_discovered"]
            from jobfinder.storage.api_profiles import save_profile

            profile.setdefault("discovered_at", datetime.now(timezone.utc).isoformat())
            save_profile(career_page_url, company_name, profile, store)
    except Exception:
        pass  # agent output was a plain JSON array — nothing to save
