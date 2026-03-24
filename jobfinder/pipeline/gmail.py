"""Gmail integration for pipeline sync.

Searches the user's Gmail for interview-related signals using stored
Google OAuth tokens.  Two-pass search:
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


@dataclass
class GmailSignal:
    company_name: str
    signal_type: str  # scheduling | confirmation | rejection | offer | recruiter_outreach
    subject: str
    snippet: str
    date: str
    is_new_company: bool = False

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


def scan_gmail(
    tokens: dict[str, str],
    pipeline_entries: list[dict],
    lookback_days: int = 3,
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

    # ── Pass 1: Known companies ──────────────────────────────────────────
    if known_companies:
        company_names = list(known_companies)
        # Gmail OR query has limits; batch if needed
        for i in range(0, len(company_names), 20):
            batch = company_names[i : i + 20]
            or_clause = " OR ".join(f'"{name}"' for name in batch)
            query = f"after:{since} ({or_clause})"
            signals.extend(_search_and_extract(service, query, known_companies, is_new=False))

    # ── Pass 2: Broad recruiter signal search ────────────────────────────
    broad_query = (
        f"after:{since} "
        '(recruiter OR "hiring manager" OR "next steps" OR "move forward" '
        'OR "schedule a call" OR interview OR screening OR application OR offer '
        'OR "excited to connect" OR "opportunity at")'
    )
    broad_signals = _search_and_extract(service, broad_query, known_companies, is_new=True)

    # Only keep truly new companies (not already in known set or pass 1 results)
    existing_names = {s.company_name.lower() for s in signals}
    for sig in broad_signals:
        if sig.company_name.lower() not in existing_names and sig.company_name.lower() not in known_companies:
            signals.append(sig)

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
            )
        )

    return signals
