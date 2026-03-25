"""LLM-powered reasoning for pipeline sync.

Takes the current pipeline state plus Gmail/Calendar signals and uses
the user's LLM API key to generate stage transition suggestions,
new company detections, and a natural language summary.
"""

from __future__ import annotations

import json
import re
import logging
import uuid
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)

STAGE_TRANSITION_RULES = """
Stage transition rules:
- not_started → outreach: First LinkedIn InMail or cold recruiter email detected (no call scheduled yet)
- outreach → recruiter: Initial outreach turns into a scheduled recruiter call
- not_started → recruiter: Recruiter reaches out and call is already scheduled
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

LinkedIn signals (tagged [LINKEDIN]):
- Almost always recruiter outreach — suggest "outreach" stage (not "recruiter", which implies a call has occurred).
- If company_name is a placeholder like "[LinkedIn: FirstName LastName]", try to extract the real company name from the snippet (look for "at <Company>" in the recruiter's headline). Use the real name if found; otherwise keep the placeholder.
- For new_companies from LinkedIn signals: set "source" to "linkedin" and "suggested_stage" to "outreach".
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
        source_tag = "[LINKEDIN]" if g.get("source") == "linkedin" else ""
        gmail_summary.append(
            f"- [{g.get('signal_type', '?')}]{source_tag} {g.get('company_name', '?')}: "
            f"subject=\"{g.get('subject', '')[:80]}\" | "
            f"snippet=\"{g.get('snippet', '')[:100]}\" | {g.get('date', '')}"
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
- "company_name": inferred company name (resolve placeholders like "[LinkedIn: Name]" to real company if possible)
- "suggested_stage": "outreach" (for LinkedIn signals), "recruiter" (if call already scheduled), or "not_started"
- "reason": why this company was detected
- "source": "linkedin" (for [LINKEDIN]-tagged signals) or "gmail"

Only suggest changes that are clearly supported by the signals. Do not guess.
Respond with ONLY the JSON object, no markdown formatting.
"""


_COMPANY_SUFFIXES = re.compile(
    r"\s*\b(inc\.?|llc\.?|corp\.?|co\.?|ltd\.?|limited|incorporated|corporation)\s*$",
    re.IGNORECASE,
)


def _normalize_company(name: str) -> str:
    """Strip common corporate suffixes for fuzzy matching."""
    return _COMPANY_SUFFIXES.sub("", name.lower()).strip()


def _fuzzy_lookup(company: str, name_to_id: dict[str, str]) -> str | None:
    """Look up entry_id by company name, falling back to fuzzy matching."""
    key = company.lower()
    # Exact match
    if key in name_to_id:
        return name_to_id[key]

    # Normalized match (strip Inc/LLC/etc.)
    norm = _normalize_company(company)
    for entry_name, eid in name_to_id.items():
        if _normalize_company(entry_name) == norm:
            log.info("Fuzzy match (normalized): LLM said %r → matched %r", company, entry_name)
            return eid

    # Substring containment (either direction)
    for entry_name, eid in name_to_id.items():
        if norm in entry_name or entry_name in norm:
            log.info("Fuzzy match (substring): LLM said %r → matched %r", company, entry_name)
            return eid

    return None


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
        entry_id = _fuzzy_lookup(company, name_to_id)
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


# ── Signal type → stage mapping for rule-based fallback ──────────────────

_SIGNAL_STAGE_MAP: dict[str, str | None] = {
    "offer": "offer",
    "rejection": "rejected",
    "scheduling": None,  # Keep current stage, just update badge
    "confirmation": None,
    "recruiter_outreach": "not_started",
}

_SIGNAL_BADGE_MAP: dict[str, str | None] = {
    "offer": "new",
    "rejection": None,
    "scheduling": "sched",
    "confirmation": "done",
    "recruiter_outreach": "new",
}

_SIGNAL_CONFIDENCE: dict[str, str] = {
    "offer": "high",
    "rejection": "high",
    "scheduling": "medium",
    "confirmation": "medium",
    "recruiter_outreach": "low",
}

# Priority for dedup: higher = wins when multiple signals for same company
_SIGNAL_PRIORITY: dict[str, int] = {
    "offer": 5,
    "rejection": 4,
    "scheduling": 3,
    "confirmation": 2,
    "recruiter_outreach": 1,
}

_CALENDAR_STAGE_MAP: dict[str, str | None] = {
    "upcoming_interview": None,
    "completed_interview": None,
    "scheduled": None,
}

_CALENDAR_BADGE_MAP: dict[str, str | None] = {
    "upcoming_interview": "sched",
    "completed_interview": "done",
    "scheduled": "sched",
}


def rule_based_suggestions(
    gmail_signals: list[dict],
    calendar_signals: list[dict],
    entries: list[dict],
) -> ReasoningResult:
    """Generate pipeline suggestions from signals using rules (no LLM needed).

    Maps signal types to stage transitions and badge updates. Used as a
    fallback when no LLM API key is available, or when the LLM returns
    no suggestions.
    """
    # Build case-insensitive lookup: company_name → entry
    name_to_entry: dict[str, dict] = {}
    for e in entries:
        name = e.get("company_name", "").lower()
        if name:
            name_to_entry[name] = e

    # Deduplicate: keep highest-priority signal per company
    best_gmail: dict[str, dict] = {}
    for g in gmail_signals:
        company = g.get("company_name", "").strip()
        if not company:
            continue
        key = company.lower()
        signal_type = g.get("signal_type", "recruiter_outreach")
        priority = _SIGNAL_PRIORITY.get(signal_type, 0)
        existing = best_gmail.get(key)
        if not existing or priority > _SIGNAL_PRIORITY.get(
            existing.get("signal_type", ""), 0
        ):
            best_gmail[key] = g

    suggestions: list[PipelineSuggestion] = []
    new_companies: list[PipelineSuggestion] = []
    seen_companies: set[str] = set()

    # Process Gmail signals
    for key, g in best_gmail.items():
        company = g.get("company_name", "").strip()
        signal_type = g.get("signal_type", "recruiter_outreach")
        subject = g.get("subject", "")
        is_new = g.get("is_new_company", False)
        entry = name_to_entry.get(key)

        suggested_stage = _SIGNAL_STAGE_MAP.get(signal_type)
        suggested_badge = _SIGNAL_BADGE_MAP.get(signal_type)
        confidence = _SIGNAL_CONFIDENCE.get(signal_type, "low")
        reason = subject[:120] if subject else f"{signal_type} signal detected"

        if entry:
            # Existing entry — suggest update
            current_stage = entry.get("stage", "not_started")
            # Only suggest stage change if it's meaningful
            if suggested_stage and suggested_stage == current_stage:
                suggested_stage = None  # No change needed
            suggestions.append(
                PipelineSuggestion(
                    entry_id=entry.get("id"),
                    company_name=company,
                    suggested_stage=suggested_stage,
                    suggested_badge=suggested_badge,
                    reason=reason,
                    confidence=confidence,
                    source="gmail",
                )
            )
        elif is_new and key not in seen_companies:
            # New company detected
            new_companies.append(
                PipelineSuggestion(
                    entry_id=None,
                    company_name=company,
                    suggested_stage=suggested_stage or "not_started",
                    suggested_badge="new",
                    reason=reason,
                    confidence=confidence,
                    source="gmail",
                )
            )
            seen_companies.add(key)

    # Process Calendar signals
    for c in calendar_signals:
        company = (c.get("company_name") or "").strip()
        if not company:
            continue
        key = company.lower()
        if key in seen_companies:
            continue  # Already handled by Gmail signal

        event_type = c.get("event_type", "scheduled")
        entry = name_to_entry.get(key)
        suggested_badge = _CALENDAR_BADGE_MAP.get(event_type)
        title = c.get("title", "")
        reason = f"{title[:80]} ({c.get('start_time', '')})"

        if entry:
            suggestions.append(
                PipelineSuggestion(
                    entry_id=entry.get("id"),
                    company_name=company,
                    suggested_stage=None,
                    suggested_badge=suggested_badge,
                    reason=reason,
                    confidence="medium",
                    source="calendar",
                )
            )
            seen_companies.add(key)

    n_suggest = len(suggestions)
    n_new = len(new_companies)
    summary = (
        f"Found {n_suggest} update(s) for existing entries "
        f"and {n_new} new company signal(s) from email/calendar."
    )
    log.info("Rule-based fallback: %d suggestions, %d new companies", n_suggest, n_new)

    return ReasoningResult(
        suggestions=suggestions,
        new_companies=new_companies,
        summary=summary,
    )


def merge_rule_based_for_uncovered(
    llm_result: ReasoningResult,
    gmail_signals: list[dict],
    calendar_signals: list[dict],
    entries: list[dict],
) -> ReasoningResult:
    """Fill gaps the LLM missed by running rule-based on uncovered signals.

    Computes which companies were already addressed by the LLM, runs the
    rule-based engine on the full signal set, then appends only results
    for companies the LLM did NOT cover.
    """
    covered = {s.company_name.lower() for s in llm_result.suggestions}
    covered |= {c.company_name.lower() for c in llm_result.new_companies}

    fallback = rule_based_suggestions(gmail_signals, calendar_signals, entries)

    added_s = 0
    for s in fallback.suggestions:
        if s.company_name.lower() not in covered:
            llm_result.suggestions.append(s)
            covered.add(s.company_name.lower())
            added_s += 1

    added_n = 0
    for c in fallback.new_companies:
        if c.company_name.lower() not in covered:
            llm_result.new_companies.append(c)
            covered.add(c.company_name.lower())
            added_n += 1

    if added_s or added_n:
        log.info(
            "Hybrid merge: added %d rule-based suggestions + %d new companies "
            "for signals the LLM did not cover",
            added_s, added_n,
        )

    return llm_result
