"""Google Calendar integration for pipeline sync.

Reads the user's calendar for upcoming and recently completed interviews,
matching events to pipeline companies.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

# Keywords that suggest an event is interview-related
_INTERVIEW_KEYWORDS = {
    "interview",
    "screen",
    "screening",
    "onsite",
    "panel",
    "technical",
    "behavioral",
    "hiring",
    "recruiter",
    "phone screen",
    "final round",
    "coding",
    "system design",
    "culture fit",
    "take-home",
    "assessment",
}


@dataclass
class CalendarSignal:
    company_name: str | None
    event_type: str  # upcoming_interview | completed_interview | scheduled
    title: str
    start_time: str
    end_time: str
    organizer: str | None = None
    status: str = "confirmed"  # confirmed | tentative

    def to_dict(self) -> dict:
        return asdict(self)


def _build_calendar_service(tokens: dict[str, str]):
    """Build an authenticated Calendar API service from stored tokens."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        token_uri=_GOOGLE_TOKEN_URI,
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            log.warning("Failed to refresh Google access token for Calendar")

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _is_interview_event(title: str, description: str = "") -> bool:
    """Check if an event title/description suggests it's interview-related."""
    text = f"{title} {description}".lower()
    return any(kw in text for kw in _INTERVIEW_KEYWORDS)


def _match_company(
    title: str,
    organizer_email: str,
    attendees: list[str],
    known_companies: dict[str, str],
) -> str | None:
    """Try to match an event to a known pipeline company.

    Returns the company name if matched, None otherwise.
    """
    text = f"{title} {organizer_email} {' '.join(attendees)}".lower()

    for company_lower, company_original in known_companies.items():
        if company_lower in text:
            return company_original

    # Try domain matching from organizer email
    if "@" in organizer_email:
        domain = organizer_email.split("@")[1].split(".")[0].lower()
        if domain in known_companies:
            return known_companies[domain]
        # Check if domain is a substring of any company name
        for company_lower, company_original in known_companies.items():
            if domain in company_lower or company_lower in domain:
                return company_original

    return None


def _infer_company_from_event(title: str, organizer_email: str) -> str | None:
    """Try to infer a company name from an event when no pipeline match exists."""
    # Try from organizer email domain
    if "@" in organizer_email:
        domain = organizer_email.split("@")[1].split(".")[0].lower()
        if domain not in ("gmail", "yahoo", "hotmail", "outlook", "icloud", "google", "calendar"):
            return domain.replace("-", " ").title()

    # Try to extract from title patterns like "Interview with Company" or "Company - Technical Screen"
    patterns = [
        r"(?:interview|screen|call)\s+(?:with|at|@)\s+(.+?)(?:\s*[-–—]|\s*$)",
        r"^(.+?)\s*[-–—]\s*(?:interview|screen|call|round|panel)",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def scan_calendar(
    tokens: dict[str, str],
    pipeline_entries: list[dict],
    past_days: int = 3,
    future_days: int = 7,
) -> list[CalendarSignal]:
    """Read Google Calendar for interview-related events.

    Returns a list of CalendarSignal objects.
    """
    try:
        service = _build_calendar_service(tokens)
    except Exception as exc:
        log.error("Failed to build Calendar service: %s", exc)
        return []

    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=past_days)).isoformat()
    time_max = (now + timedelta(days=future_days)).isoformat()

    # Build company lookup (lowercase → original name)
    known_companies: dict[str, str] = {}
    for entry in pipeline_entries:
        name = entry.get("company_name", "")
        if name:
            known_companies[name.lower()] = name

    signals: list[CalendarSignal] = []

    try:
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=100,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except Exception as exc:
        log.warning("Calendar events.list failed: %s", exc)
        return []

    events = events_result.get("items", [])

    for event in events:
        title = event.get("summary", "")
        description = event.get("description", "")
        organizer = event.get("organizer", {}).get("email", "")
        attendee_emails = [a.get("email", "") for a in event.get("attendees", [])]
        event_status = event.get("status", "confirmed")

        # Skip non-interview events
        if not _is_interview_event(title, description):
            continue

        # Try to match to a pipeline company
        company_name = _match_company(title, organizer, attendee_emails, known_companies)
        if not company_name:
            company_name = _infer_company_from_event(title, organizer)

        # Determine event type
        start = event.get("start", {})
        start_str = start.get("dateTime", start.get("date", ""))
        end = event.get("end", {})
        end_str = end.get("dateTime", end.get("date", ""))

        try:
            # Parse start time to determine if past or future
            if "T" in start_str:
                event_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            else:
                event_time = datetime.fromisoformat(start_str + "T00:00:00+00:00")

            if event_time < now:
                event_type = "completed_interview"
            else:
                event_type = "upcoming_interview"
        except (ValueError, TypeError):
            event_type = "scheduled"

        signals.append(
            CalendarSignal(
                company_name=company_name,
                event_type=event_type,
                title=title[:200],
                start_time=start_str,
                end_time=end_str,
                organizer=organizer or None,
                status="tentative" if event_status == "tentative" else "confirmed",
            )
        )

    return signals
