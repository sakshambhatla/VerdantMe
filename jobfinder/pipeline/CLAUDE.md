# jobfinder/pipeline — Claude Context

Pipeline sync module: scans Gmail + Google Calendar for job interview signals, uses LLM (or rule-based fallback) to reason about stage transitions, and presents structured suggestions for user review.

## File Map

```
pipeline/
  __init__.py         # Module marker
  gmail.py            # Gmail API scanner — two-pass search (known + new companies)
  calendar.py         # Google Calendar scanner — interview detection + company matching
  reasoning.py        # LLM reasoning + rule_based_suggestions() fallback
```

## Architecture

### Signal Extraction Layer

**`gmail.py`** — `scan_gmail(tokens, entries, lookback_days=3) -> list[GmailSignal]`
- Pass 1: search for known pipeline companies in recent emails
- Pass 2: broad recruiter/interview keyword search for new companies
- Classifies signals: `offer`, `rejection`, `scheduling`, `confirmation`, `recruiter_outreach`
- Uses `google.oauth2.credentials.Credentials` with refresh token auto-refresh

**`calendar.py`** — `scan_calendar(tokens, entries, past_days=3, future_days=7) -> list[CalendarSignal]`
- Fetches events from primary calendar
- Filters by interview keywords in title/description
- Matches events to pipeline companies by name/domain/title pattern
- Classifies: `upcoming_interview`, `completed_interview`, `scheduled`

### Reasoning Layer (swappable)

**`reasoning.py`** has two paths:

1. **LLM path**: `reason_pipeline(entries, gmail_signals, calendar_signals, api_key, provider)`
   - Builds a prompt with current pipeline state + signals + stage transition rules
   - Calls Anthropic or Gemini (multi-provider via `_call_anthropic()` / `_call_gemini()`)
   - Parses structured JSON response into `ReasoningResult`
   - Returns `suggestions` (for existing entries) + `new_companies` + `summary`

2. **Rule-based fallback**: `rule_based_suggestions(gmail_signals, calendar_signals, entries)`
   - Maps signal types directly to stages/badges via lookup tables
   - No LLM needed — deterministic conversion
   - Used when no LLM API key is available or LLM returns nothing

**Both paths return `ReasoningResult`** — the sync endpoint doesn't care which path was used.

### Sync API (`api/routes/pipeline.py`)

- `POST /pipeline/sync` — orchestrates: load entries → scan Gmail/Calendar → LLM reasoning (try all `SUPPORTED_PROVIDERS`) → rule-based fallback → return signals + suggestions
- `POST /pipeline/sync/apply` — accepts selected suggestions, creates/updates `PipelineEntry` records + changelog `PipelineUpdate` entries

### Frontend View Model: JobUpdate

**`JobUpdate`** (defined in `ui/src/lib/api.ts`) is a frontend-only view model for the 3-column sync review modal. It maps 1:1 to `PipelineEntry` fields shown on Kanban cards.

Built from `PipelineSuggestion` + signal data via `buildJobUpdates()` in `PipelineSyncModal.tsx`. This is the **swappable conversion layer** — today it maps from backend suggestions, later it could use a different strategy.

Fields:
- `source` — "gmail" | "calendar" (signal origin)
- `company_name` → Card title
- `stage` → Kanban column
- `badge` → Card tag (New, Scheduled, Awaiting, etc.)
- `next_action` → Card "→ next action" text
- `note` → Expanded dialog notes (blank for now, future editable)
- `recommendation` — "add" | "update" | "ignore" (user-overridable dropdown)

### Data Flow

```
User clicks "Refresh Pipeline"
    ↓
POST /pipeline/sync
    ├── scan_gmail() → GmailSignal[]
    ├── scan_calendar() → CalendarSignal[]
    └── reason_pipeline() OR rule_based_suggestions() → ReasoningResult
        ├── suggestions: PipelineSuggestion[] (existing entries)
        ├── new_companies: PipelineSuggestion[]
        └── summary: string
    ↓
Frontend: buildJobUpdates() converts to JobUpdate[]
    ↓
3-column modal: Signal | Recommendation (dropdown) | Pipeline Entry Preview
    ↓
User reviews, overrides recommendations, clicks Apply
    ↓
POST /pipeline/sync/apply
    ├── Updates existing PipelineEntry records
    ├── Creates new PipelineEntry records
    └── Generates PipelineUpdate changelog entries
    ↓
Kanban board re-fetches → new/updated cards appear
```

## Key Patterns

- **Provider-agnostic LLM**: sync endpoint iterates `SUPPORTED_PROVIDERS` from `config.py`, not hardcoded provider names
- **Graceful degradation**: no Google tokens → skip scans; no LLM key → rule-based fallback; no signals → empty result
- **Two-step apply**: suggestions are never auto-applied — user reviews in modal first
- **Signal dedup**: `rule_based_suggestions()` keeps highest-priority signal per company
- **Token refresh**: Gmail/Calendar modules auto-refresh expired Google access tokens

## Adding a New Signal Source

1. Create `pipeline/<source>.py` with a `scan_<source>(tokens, entries) -> list[<Source>Signal]` function
2. Add the scan call in `POST /pipeline/sync` (wrap in `asyncio.to_thread()`)
3. Pass signals to `reason_pipeline()` and `rule_based_suggestions()`
4. Update `buildJobUpdates()` in `PipelineSyncModal.tsx` to handle the new signal type

## Modifying the Conversion Layer

The `buildJobUpdates()` function in `PipelineSyncModal.tsx` is the conversion layer from backend `PipelineSuggestion` → frontend `JobUpdate`. To swap the strategy:
- Modify `buildJobUpdates()` for frontend-only changes
- Or modify `reasoning.py` to change how suggestions are generated
- The `JobUpdate` interface is the stable contract between conversion and display
