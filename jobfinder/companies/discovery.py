from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from jobfinder.companies.prompts import SYSTEM_PROMPT, build_user_prompt
from jobfinder.config import AppConfig
from jobfinder.storage.schemas import DiscoveredCompany


def discover_companies(
    resumes: list[dict],
    config: AppConfig,
) -> list[DiscoveredCompany]:
    """Discover companies using the configured model provider."""
    if config.model_provider == "gemini":
        raw_text = _call_gemini(resumes, config)
    else:
        raw_text = _call_anthropic(resumes, config)

    companies = _parse_response(raw_text)

    now = datetime.now(timezone.utc).isoformat()
    for c in companies:
        c.discovered_at = now

    return companies


def _call_anthropic(resumes: list[dict], config: AppConfig) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    import anthropic

    client = anthropic.Anthropic()
    user_prompt = build_user_prompt(resumes, config.max_companies)

    print()  # blank line before stream
    chunks: list[str] = []
    with client.messages.stream(
        model=config.anthropic_model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            chunks.append(text)
    print("\n")  # blank line after stream
    return "".join(chunks)


def _call_gemini(resumes: list[dict], config: AppConfig) -> str:
    from jobfinder.utils.throttle import get_limiter
    get_limiter(config.rpm_limit).wait()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    user_prompt = build_user_prompt(resumes, config.max_companies)

    print()  # blank line before stream
    chunks: list[str] = []
    for chunk in client.models.generate_content_stream(
        model=config.gemini_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    ):
        if chunk.text:
            print(chunk.text, end="", flush=True)
            chunks.append(chunk.text)
    print("\n")  # blank line after stream
    return "".join(chunks)


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
