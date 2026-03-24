"""LLM-powered reasoning for pipeline sync.

Takes the current pipeline state plus Gmail/Calendar signals and uses
the user's LLM API key to generate stage transition suggestions,
new company detections, and a natural language summary.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)

STAGE_TRANSITION_RULES = """
Stage transition rules:
- not_started → recruiter: Recruiter reaches out / screen scheduled
- recruiter → hm_screen: Recruiter screen completed, advancing to hiring manager
- hm_screen → onsite: Panel / full onsite loop confirmed
- any → blocked: ATS rejection, no open roles, no response, hiring freeze
- any → rejected: Formal rejection after an actual interview
- blocked means never had a real interview; rejected means post-interview rejection

Badge rules:
- "sched" = upcoming confirmed interview with a specific date/time
- "done" = completed a step today, awaiting next
- "await" = waiting on a response, no action needed
- "new" = just entered the pipeline today
- "panel" = panel or full onsite loop confirmed
- null = no active status
"""


@dataclass
class PipelineSuggestion:
    id: str = ""
    entry_id: str | None = None  # None = new company
    company_name: str = ""
    suggested_stage: str | None = None
    suggested_badge: str | None = None
    suggested_next_action: str | None = None
    reason: str = ""
    confidence: str = "medium"
    source: str = "llm"

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReasoningResult:
    suggestions: list[PipelineSuggestion] = field(default_factory=list)
    new_companies: list[PipelineSuggestion] = field(default_factory=list)
    summary: str | None = None

    def to_dict(self) -> dict:
        return {
            "suggestions": [s.to_dict() for s in self.suggestions],
            "new_companies": [c.to_dict() for c in self.new_companies],
            "summary": self.summary,
        }


def _build_prompt(
    entries: list[dict],
    gmail_signals: list[dict],
    calendar_signals: list[dict],
) -> str:
    """Build the LLM prompt with pipeline state and external signals."""

    entries_summary = []
    for e in entries:
        entries_summary.append(
            f"- {e.get('company_name', '?')} | stage: {e.get('stage', '?')} | "
            f"badge: {e.get('badge') or 'none'} | "
            f"next: {e.get('next_action') or 'none'} | "
            f"note: {(e.get('note') or '')[:100]}"
        )

    gmail_summary = []
    for g in gmail_signals:
        gmail_summary.append(
            f"- [{g.get('signal_type', '?')}] {g.get('company_name', '?')}: "
            f"subject=\"{g.get('subject', '')[:80]}\" | {g.get('date', '')}"
        )

    calendar_summary = []
    for c in calendar_signals:
        calendar_summary.append(
            f"- [{c.get('event_type', '?')}] {c.get('company_name') or 'Unknown'}: "
            f"\"{c.get('title', '')[:80]}\" | {c.get('start_time', '')} | "
            f"status: {c.get('status', 'confirmed')}"
        )

    return f"""You are a job search pipeline assistant. Analyze the current pipeline state
and external signals (email + calendar) to suggest updates.

{STAGE_TRANSITION_RULES}

== CURRENT PIPELINE ==
{chr(10).join(entries_summary) if entries_summary else "(empty)"}

== GMAIL SIGNALS (recent emails) ==
{chr(10).join(gmail_summary) if gmail_summary else "(no email signals)"}

== CALENDAR SIGNALS (upcoming/recent events) ==
{chr(10).join(calendar_summary) if calendar_summary else "(no calendar events)"}

Based on the above, respond with a JSON object containing:
1. "suggestions": array of updates for EXISTING pipeline entries (stage changes, badge updates, next_action updates)
2. "new_companies": array of NEW companies detected from emails that are NOT in the pipeline yet
3. "summary": a brief natural language summary (2-3 sentences) of today's pipeline activity

Each suggestion should have:
- "entry_id": null (you don't have IDs, the system will match by company_name)
- "company_name": exact name from the pipeline
- "suggested_stage": new stage (or null if no stage change)
- "suggested_badge": new badge (or null)
- "suggested_next_action": updated next action text (or null)
- "reason": brief explanation
- "confidence": "high", "medium", or "low"
- "source": "gmail", "calendar", or "both"

Each new_company should have:
- "company_name": inferred company name
- "suggested_stage": "not_started" or "recruiter"
- "reason": why this company was detected
- "source": "gmail"

Only suggest changes that are clearly supported by the signals. Do not guess.
Respond with ONLY the JSON object, no markdown formatting.
"""


def _parse_llm_response(text: str, entries: list[dict]) -> ReasoningResult:
    """Parse the LLM's JSON response into structured suggestions."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (code fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning("Failed to parse LLM reasoning response as JSON")
        return ReasoningResult(summary="LLM response could not be parsed.")

    # Build company name → entry_id lookup
    name_to_id: dict[str, str] = {}
    for e in entries:
        name = e.get("company_name", "").lower()
        if name:
            name_to_id[name] = e.get("id", "")

    suggestions = []
    for s in data.get("suggestions", []):
        company = s.get("company_name", "")
        entry_id = name_to_id.get(company.lower())
        if not entry_id:
            continue  # Skip suggestions for unknown companies

        suggestions.append(
            PipelineSuggestion(
                entry_id=entry_id,
                company_name=company,
                suggested_stage=s.get("suggested_stage"),
                suggested_badge=s.get("suggested_badge"),
                suggested_next_action=s.get("suggested_next_action"),
                reason=s.get("reason", ""),
                confidence=s.get("confidence", "medium"),
                source=s.get("source", "llm"),
            )
        )

    new_companies = []
    for nc in data.get("new_companies", []):
        new_companies.append(
            PipelineSuggestion(
                entry_id=None,
                company_name=nc.get("company_name", ""),
                suggested_stage=nc.get("suggested_stage", "not_started"),
                reason=nc.get("reason", ""),
                confidence="medium",
                source=nc.get("source", "gmail"),
            )
        )

    return ReasoningResult(
        suggestions=suggestions,
        new_companies=new_companies,
        summary=data.get("summary"),
    )


def _call_anthropic(
    prompt: str,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    """Call Anthropic API for pipeline reasoning."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_gemini(
    prompt: str,
    api_key: str,
    model: str = "gemini-2.5-flash-lite",
) -> str:
    """Call Gemini API for pipeline reasoning."""
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return response.text


def reason_pipeline(
    entries: list[dict],
    gmail_signals: list[dict],
    calendar_signals: list[dict],
    api_key: str,
    model_provider: str = "anthropic",
    model_name: str | None = None,
) -> ReasoningResult:
    """Run LLM reasoning on pipeline state + external signals.

    Returns structured suggestions for the user to review.
    """
    if not gmail_signals and not calendar_signals:
        return ReasoningResult(summary="No external signals detected — nothing to analyze.")

    prompt = _build_prompt(entries, gmail_signals, calendar_signals)

    try:
        if model_provider == "anthropic":
            response_text = _call_anthropic(prompt, api_key, model_name or "claude-sonnet-4-6")
        elif model_provider == "gemini":
            response_text = _call_gemini(prompt, api_key, model_name or "gemini-2.5-flash-lite")
        else:
            return ReasoningResult(summary=f"Unsupported model provider: {model_provider}")
    except Exception as exc:
        log.error("LLM reasoning call failed: %s", exc)
        return ReasoningResult(summary=f"LLM reasoning failed: {exc}")

    return _parse_llm_response(response_text, entries)
