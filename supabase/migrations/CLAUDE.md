# supabase/migrations — Claude Context

Numbered SQL migrations for the Supabase Postgres schema.

## Naming Convention
Format: `20240101000NNN_description.sql` — next available is `20240101000017_<name>.sql`.

## Current Migrations

| # | File | What it does |
|---|------|-------------|
| 001 | `_schema.sql` | Core tables: profiles, resumes, companies, roles, company_registry, roles_cache, api_profiles, external_job_cache; case-insensitive unique indices |
| 002 | `_rls.sql` | RLS policies for all user-scoped tables |
| 003 | `_vault_api_keys.sql` | SECURITY DEFINER functions for encrypted API key storage via supabase_vault |
| 004 | `_company_runs_and_job_runs.sql` | company_runs + job_runs tables for discovery run history |
| 005 | `_profile_pictures.sql` | profile_pictures table + RLS for avatar storage |
| 006 | `_roles_unique_with_is_filtered.sql` | unique(user_id, url) constraint on roles; is_filtered flag |
| 007 | `_api_profiles_audit.sql` | api_profiles table with audit trigger |
| 008 | `_external_job_cache.sql` | external_job_cache table for YC Jobs / external sources |
| 009 | `_user_motivations.sql` | user_motivations table |
| 010 | `_company_runs_focus.sql` | focus column on company_runs |
| 011 | `_waitlist.sql` | waitlist table |
| 012 | `_pipeline.sql` | pipeline tables |
| 013 | `_google_tokens.sql` | Vault storage for Google OAuth access/refresh tokens |
| 014 | `_linkedin_source.sql` | LinkedIn as a role source |
| 015 | `_offer_analyses.sql` | offer_analyses table |
| 016 | `_fix_google_oauth_profile.sql` | Fix handle_new_user() trigger to capture full_name/avatar_url from Google metadata; backfill existing users |

## Conventions

- Every user-scoped table has a `user_id` column (FK to `auth.users`) + RLS policy
- RLS pattern: `using (auth.uid() = user_id) with check (auth.uid() = user_id)`
- `supabase_vault` extension is **pre-installed** on Supabase — never add `CREATE EXTENSION`
- SECURITY DEFINER functions granted only to `service_role`
- Primary keys: `gen_random_uuid()`
- Timestamps: `timestamptz` with `default now()`
- **CRITICAL: Always use `public.` schema prefix** in `CREATE TABLE` and `ALTER TABLE` statements (e.g. `CREATE TABLE public.foo`, `ALTER TABLE public.foo ADD COLUMN bar`). The `test_schema_sync.py` parser requires this prefix — omitting it causes columns to be silently invisible to the test

## Adding a New Migration

1. Create `20240101000NNN_<name>.sql` (next sequential number)
2. Include RLS policy if the table is user-scoped
3. Apply via Supabase SQL Editor or `python scripts/apply_vault_migration.py`
4. Update this file's migration table
5. **Run `pytest tests/test_schema_sync.py`** — must pass before committing

## Adding a New Column to an Existing Table

When adding a column, three files must be updated in lockstep:
1. `supabase/migrations/` — `ALTER TABLE public.<table> ADD COLUMN ...` (with `public.` prefix)
2. `jobfinder/storage/supabase_backend.py` — add to both the `row = {...}` write dict AND the `_row_to_<table>()` read method
3. `jobfinder/storage/schemas.py` — add the field to the corresponding Pydantic model

Run `pytest tests/test_schema_sync.py` after all three changes — it validates Python ↔ SQL column alignment.
