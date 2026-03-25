"""Gmail integration for pipeline sync.

Searches the user's Gmail for interview-related signals using stored
Google OAuth tokens.  Three-pass search:
  0. LinkedIn notification emails — InMails and connection messages
  1. Known companies — messages mentioning pipeline company names
  2. New company detection — broad recruiter/interview keyword search
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

# Google API client ID for token refresh
_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

# LinkedIn notification sender domains
_LINKEDIN_SENDER_DOMAINS = frozenset({
    "linkedin.com",
    "messages-noreply.linkedin.com",
    "jobalerts-noreply.linkedin.com",
    "hit-reply.linkedin.com",
})

# LinkedIn subject patterns to skip (no actionable pipeline signal)
_LINKEDIN_SKIP_PATTERNS = re.compile(
    r"viewed your profile|linkedin digest|jobs you may be interested|new jobs for you|"
    r"weekly job picks|profile views|who viewed",
    re.IGNORECASE,
)

# Regex to extract company from recruiter headline in snippet (e.g. "at Acme Corp" or "@ Acme")
_LINKEDIN_COMPANY_RE = re.compile(r"(?:^|\s)(?:at|@)\s+([A-Z][A-Za-z0-9&.,'\- ]{1,50}?)(?:\s*[|·•\n,]|$)")

# LinkedIn subject patterns for recruiter name extraction
_LINKEDIN_SUBJECT_NAME_RE = re.compile(
    r"(?:(?:You have a new message from|New message from)\s+(.+?)(?:\s+on LinkedIn)?$)|"
    r"^(.+?)\s+(?:sent you a message|wants to connect|sent you an InMail)",
    re.IGNORECASE,
)


@dataclass
class GmailSignal:
    company_name: str
    signal_type: str  # scheduling | confirmation | rejection | offer | recruiter_outreach
    subject: str
    snippet: str
    date: str
    is_new_company: bool = False
    source: str = "gmail"  # "gmail" | "linkedin"

    def to_dict(self) -> dict:
        return asdict(self)


def _build_gmail_service(tokens: dict[str, str]):
    """Build an authenticated Gmail API service from stored tokens."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        token_uri=_GOOGLE_TOKEN_URI,
        # Client ID/secret not needed for token refresh via Supabase-issued tokens
        # The refresh is handled by Google's token endpoint with the refresh token alone
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            log.warning("Failed to refresh Google access token; using existing token")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _classify_signal(subject: str, snippet: str) -> str:
    """Classify an email into a signal type based on subject + snippet text."""
    text = f"{subject} {snippet}".lower()

    rejection_words = ["unfortunately", "not moving forward", "decided not to", "other candidates", "not a fit", "regret"]
    offer_words = ["offer letter", "compensation", "start date", "we'd like to offer", "pleased to offer"]
    scheduling_words = ["schedule", "calendar invite", "interview time", "availability", "slot", "book a time"]
    confirmation_words = ["confirmed", "looking forward", "see you", "joining link", "zoom link", "meet link"]

    if any(w in text for w in offer_words):
        return "offer"
    if any(w in text for w in rejection_words):
        return "rejection"
    if any(w in text for w in scheduling_words):
        return "scheduling"
    if any(w in text for w in confirmation_words):
        return "confirmation"
    return "recruiter_outreach"


def _extract_company_from_email(sender: str) -> str | None:
    """Extract company name from sender email address domain."""
    match = re.search(r"@([\w.-]+)\.", sender)
    if match:
        domain = match.group(1).lower()
        # Skip generic email providers
        if domain in ("gmail", "yahoo", "hotmail", "outlook", "icloud", "protonmail", "aol"):
            return None
        return domain.replace("-", " ").title()
    return None


def _is_linkedin_sender(sender: str) -> bool:
    """Return True if the email is from a LinkedIn notification address."""
    sender_lower = sender.lower()
    return any(d in sender_lower for d in _LINKEDIN_SENDER_DOMAINS)


def _extract_linkedin_company(subject: str, snippet: str, known_companies: set[str]) -> str | None:
    """Extract company name from a LinkedIn notification email.

    Hierarchy:
      1. Known pipeline company name appearing in subject or snippet
      2. Regex match for 'at <Company>' in snippet (recruiter headline)
      3. Recruiter name from subject as placeholder '[LinkedIn: Name]'
      4. None (caller should skip)
    """
    text_lower = (subject + " " + snippet).lower()

    # 1. Known pipeline company match
    for name in known_companies:
        if name in text_lower:
            return name.title()

    # 2. Recruiter headline pattern in snippet
    match = _LINKEDIN_COMPANY_RE.search(snippet)
    if match:
        company = match.group(1).strip().rstrip(".,")
        if len(company) > 1:
            return company

    # 3. Recruiter name from subject → placeholder
    name_match = _LINKEDIN_SUBJECT_NAME_RE.search(subject)
    if name_match:
        recruiter_name = (name_match.group(1) or name_match.group(2) or "").strip()
        if recruiter_name:
            return f"[LinkedIn: {recruiter_name}]"

    return None


def scan_gmail(
    tokens: dict[str, str],
    pipeline_entries: list[dict],
    lookback_days: int = 3,
    custom_phrases: list[str] | None = None,
) -> list[GmailSignal]:
    """Search Gmail for interview-related signals.

    Returns a list of GmailSignal objects (serializable via .to_dict()).
    """
    try:
        service = _build_gmail_service(tokens)
    except Exception as exc:
        log.error("Failed to build Gmail service: %s", exc)
        return []

    signals: list[GmailSignal] = []
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y/%m/%d")

    # Build known company names set (lowercase for matching)
    known_companies = {e.get("company_name", "").lower() for e in pipeline_entries}
    known_companies.discard("")

    # ── Pass 0: LinkedIn notification emails ─────────────────────────────
    linkedin_signals = _search_and_extract_linkedin(service, since, known_companies)
    signals.extend(linkedin_signals)
    linkedin_companies = {s.company_name.lower() for s in linkedin_signals}

    # ── Pass 1: Known companies ──────────────────────────────────────────
    if known_companies:
        company_names = list(known_companies)
        # Gmail OR query has limits; batch if needed
        for i in range(0, len(company_names), 20):
            batch = company_names[i : i + 20]
            or_clause = " OR ".join(f'"{name}"' for name in batch)
            query = f"after:{since} ({or_clause})"
            new_sigs = _search_and_extract(service, query, known_companies, is_new=False)
            # Skip any that were already captured as LinkedIn signals
            for sig in new_sigs:
                if sig.company_name.lower() not in linkedin_companies:
                    signals.append(sig)

    # ── Pass 2: Broad recruiter signal search ────────────────────────────
    broad_query = (
        f"after:{since} "
        '(recruiter OR "hiring manager" OR "next steps" OR "move forward" '
        'OR "schedule a call" OR interview OR screening OR application OR offer '
        'OR "excited to connect" OR "opportunity at")'
    )
    broad_signals = _search_and_extract(service, broad_query, known_companies, is_new=True)

    # Only keep truly new companies (not already in known set, pass 1, or pass 0 results)
    existing_names = {s.company_name.lower() for s in signals}
    for sig in broad_signals:
        if sig.company_name.lower() not in existing_names and sig.company_name.lower() not in known_companies:
            signals.append(sig)
            existing_names.add(sig.company_name.lower())

    # ── Pass 3: Custom phrases (user-specified companies/keywords) ─────
    phrases = [p.strip() for p in (custom_phrases or []) if p.strip()]
    if phrases:
        or_clause = " OR ".join(f'"{p}"' for p in phrases)
        phrase_query = f"after:{since} ({or_clause})"
        phrase_signals = _search_and_extract(service, phrase_query, known_companies, is_new=True)
        for sig in phrase_signals:
            if sig.company_name.lower() not in existing_names and sig.company_name.lower() not in known_companies:
                signals.append(sig)
                existing_names.add(sig.company_name.lower())

    return signals


def _search_and_extract_linkedin(
    service,
    since: str,
    known_companies: set[str],
    max_results: int = 30,
) -> list[GmailSignal]:
    """Search Gmail for LinkedIn notification emails and extract recruiter signals."""
    query = (
        f"after:{since} "
        "from:(linkedin.com OR messages-noreply.linkedin.com OR "
        "jobalerts-noreply.linkedin.com OR hit-reply.linkedin.com)"
    )
    signals: list[GmailSignal] = []
    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
    except Exception as exc:
        log.warning("LinkedIn Gmail search failed: %s", exc)
        return []

    messages = results.get("messages", [])

    for msg_ref in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
        except Exception:
            continue

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")
        snippet = msg.get("snippet", "")

        # Verify sender is actually from LinkedIn
        if not _is_linkedin_sender(sender):
            continue

        # Skip non-actionable notification types
        if _LINKEDIN_SKIP_PATTERNS.search(subject):
            continue

        company_name = _extract_linkedin_company(subject, snippet, known_companies)
        if not company_name:
            continue

        signals.append(
            GmailSignal(
                company_name=company_name,
                signal_type="recruiter_outreach",
                subject=subject[:200],
                snippet=snippet[:300],
                date=date_str[:30],
                is_new_company=company_name.lower() not in known_companies,
                source="linkedin",
            )
        )

    return signals


def _search_and_extract(
    service,
    query: str,
    known_companies: set[str],
    is_new: bool,
    max_results: int = 30,
) -> list[GmailSignal]:
    """Execute a Gmail search and extract signals from results."""
    signals: list[GmailSignal] = []
    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
    except Exception as exc:
        log.warning("Gmail search failed for query [%s]: %s", query[:60], exc)
        return []

    messages = results.get("messages", [])

    for msg_ref in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
        except Exception:
            continue

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")
        snippet = msg.get("snippet", "")

        # Skip LinkedIn emails here — handled in Pass 0
        if _is_linkedin_sender(sender):
            continue

        # Try to match to a known company
        company_name = None
        for name in known_companies:
            if name in subject.lower() or name in snippet.lower() or name in sender.lower():
                company_name = name.title()
                break

        if not company_name:
            company_name = _extract_company_from_email(sender)

        if not company_name:
            continue

        signal_type = _classify_signal(subject, snippet)

        signals.append(
            GmailSignal(
                company_name=company_name,
                signal_type=signal_type,
                subject=subject[:200],
                snippet=snippet[:300],
                date=date_str[:30],
                is_new_company=is_new and company_name.lower() not in known_companies,
                source="gmail",
            )
        )

    return signals
