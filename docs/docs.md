# JobFinder — Learnings & Pitfalls

Human-written notes on things Claude (and future contributors) should know.
Add entries here when you discover non-obvious behavior, gotchas, or operational lessons.

## Template

### [Date] Topic
**Context**: What you were doing
**Issue**: What went wrong or was surprising
**Fix/Lesson**: What to do instead

---

### 2026-03-22 Supabase column additions require 3-file lockstep
**Context**: Adding `focus` field to `company_runs` for the startups feature.
**Issue**: Field was added to the API route and company_runs dict, but missed in `supabase_backend.py` (field mapping) and the migration used `ALTER TABLE company_runs` instead of `ALTER TABLE public.company_runs`. The `test_schema_sync.py` test would have caught both, but (a) the migration was invisible to the parser without `public.` prefix, and (b) the test wasn't run until after the UAT exposed the bug at runtime.
**Fix/Lesson**: When adding a column to any Supabase-backed table, always update three files in lockstep: (1) migration SQL with `public.` prefix, (2) `supabase_backend.py` read AND write handlers, (3) `schemas.py` Pydantic model. Run `pytest tests/test_schema_sync.py` immediately after — it takes 0.02s and catches mismatches between Python and SQL.

---

### 2026-03-24 Google OAuth quirks (Supabase + Google Cloud)

**Context**: Setting up Google OAuth sign-in via Supabase for managed mode, with extended scopes for Gmail and Calendar access.

**Google Cloud project**: VerdantMe, owned by `saksham.bhatla@gmail.com`.

**Issue 1 — "App not verified" 403 error**
Google OAuth apps start in "Testing" publishing status. Only users explicitly listed as test users can sign in. Everyone else gets `Error 403: access_denied` with the message "has not completed the Google verification process".
**Fix**: Go to Google Cloud Console → APIs & Services → OAuth consent screen → Test users → add the Google account(s) that need access. Currently only `saksham.bhatla@gmail.com` is added as a test user. To let other users sign in, either add them as test users (max 100) or submit the app for Google verification (required for production/public use).

**Issue 2 — Scopes must be configured in code, not the Supabase dashboard**
Supabase's Google provider config in the dashboard only takes Client ID and Client Secret. The OAuth scopes (e.g., `gmail.readonly`, `calendar.events.readonly`) and extra params (`access_type: "offline"`, `prompt: "consent"`) must be set in the frontend `signInWithOAuth` call. See `ui/src/components/AuthProvider.tsx`.

**Issue 3 — Refresh tokens require `access_type: "offline"` + `prompt: "consent"`**
Google only returns a `refresh_token` on the very first consent. If the user has already granted consent before, Google silently skips the refresh token. Setting `prompt: "consent"` forces the consent screen every time, ensuring we always get a refresh token. Without this, `session.provider_refresh_token` will be `null` on subsequent logins.

**Issue 4 — Provider tokens are ephemeral in Supabase**
`session.provider_token` and `session.provider_refresh_token` are only available on the `SIGNED_IN` auth event. They are NOT stored by Supabase and cannot be retrieved later. We capture them immediately on sign-in and store them in Supabase Vault (see migration `20240101000013_google_tokens.sql`). If they're missed, the user must sign out and sign back in to re-capture them.

**Issue 5 — Scopes must also be registered in Google Cloud Console**
Any OAuth scope requested in code must also be listed in the OAuth consent screen configuration in Google Cloud Console (APIs & Services → OAuth consent screen → Scopes). If a scope is requested but not registered, Google may silently ignore it or show a warning. Make sure `gmail.readonly` and `calendar.events.readonly` are both listed there.

---

### 2026-03-24 Supabase Vault migrations must be applied manually

**Context**: Adding any new SECURITY DEFINER vault function (e.g., Google token storage in migration 013).
**Issue**: There is no automated migration pipeline for Supabase. The `apply_vault_migration.py` script is hardcoded to migration 003, there's no `psql` or `supabase` CLI on the dev machine, and Render's deploy command doesn't run migrations. New vault functions are written to `supabase/migrations/` and pass CI (tests mock the DB), but fail at runtime in production because the SQL was never executed against the actual database.
**Fix/Lesson**: After creating any new vault migration file, you must manually paste the SQL into the Supabase SQL Editor (Dashboard → SQL Editor → New Query). This is a known limitation tracked in `todo/vault-migration-automation.md`. The runtime error looks like `RuntimeError: ... vault functions are not installed` and surfaces as a generic "Network Error" or 500 to the user.

---

### 2026-03-31 Supabase JWT expiry mid-stream kills role discovery silently

**Context**: Users hitting "Stream ended without a result" error when running Discover Jobs in managed mode.

**Issue**: Supabase access tokens (JWTs) expire after **1 hour**. The frontend grabs the current JWT via `supabase.auth.getSession()` once at the start of `discoverRolesStream`, then passes it to the backend in the `Authorization` header. The backend uses this single token for every Supabase read/write for the entire duration of the stream. If the token was already 58+ minutes old when discovery started, it expires mid-stream. When the backend then calls `store.write()` (e.g., writing `roles_unfiltered.json` or `roles.json`), PostgREST rejects it with `postgrest.exceptions.APIError: {'message': 'JWT expired', 'code': 'PGRST303'}`. Since this exception was not caught inside `event_generator()`, the generator terminated without emitting a `done` or `error` SSE event — the stream just closed silently and the frontend showed the generic "Stream ended without a result".

**This is NOT a logout issue**: the user's *session* lasts 60 days (refresh token). Only the short-lived access token expires. The Supabase JS client auto-refreshes it in the background, but once a JWT is embedded in an in-flight HTTP request, it cannot be updated mid-stream.

**Symptom**: User sees "Stream ended without a result" in the UI, with no other error detail. (After the fix in this commit, the error message is now "Your session has expired — please refresh the page and try again.")

**Workaround**: User refreshes the page (Supabase client issues a new access token) and re-runs discovery. The checkpoint system means roles already fetched are not re-fetched.

**Potential longer-term fixes**:
1. **Re-auth on `PGRST303`**: Backend catches `APIError` with code `PGRST303` and attempts to get a fresh token. Requires the frontend to also pass the refresh token (currently only the access token is sent) — non-trivial security consideration.
2. **Service role for writes**: Use the Supabase service role key for the stream's write operations, bypassing RLS. Requires careful scoping to avoid data bleed between users.
3. **Shorter-lived streams**: Break discovery into smaller chunks so each request completes in < 1 hour. Complex to implement given the current SSE architecture.
4. **Frontend keeps token fresh**: Frontend periodically sends a "refresh" signal over a side-channel while the stream is open. Not possible with a one-shot `fetch` stream; would need WebSocket or a separate polling endpoint.

---

### 2026-03-25 LLM routes must try all providers, not just the default
**Context**: Offer analysis button ("Get me Offer insights") silently failed in managed mode.
**Issue**: The `POST /pipeline/offer-analyses` route used `config.model_provider` (defaults to `"anthropic"`) to resolve the API key. User only had a Gemini key stored, so `resolve_api_key("anthropic", user_id)` threw a ValueError → 400 response. The mutation had no `onError` handler, so the error was swallowed with no UI feedback.
**Fix/Lesson**: Any API route that calls an LLM must iterate `SUPPORTED_PROVIDERS` to find an available key, not assume the default provider has one. Follow the pattern from `POST /pipeline/sync` (~line 361 in `pipeline.py`): try the configured provider first, then fall back. The pipeline sync route already did this correctly — the offer route was written separately and missed the pattern.
