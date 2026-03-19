---
name: supabase-migration
description: >
  Guided workflow for creating a new Supabase Postgres migration file with proper
  naming conventions, RLS policies, and schema consistency. Use this skill whenever
  the user says "add migration", "new migration", "supabase migration", "add table",
  "create table", "alter table", "database migration", or any similar phrase about
  modifying the Supabase database schema.
---

# Supabase Migration

Create a new numbered migration file for the Supabase Postgres database.

## Steps

### 1. Review existing schema

Read the existing migrations to understand the current schema:

```bash
ls -la /Users/sakshambhatla/workplace/JobFinder/supabase/migrations/
```

Read the most recent migration to understand the current state. Key tables:
- `profiles` — user profile (FK auth.users)
- `resumes`, `companies`, `roles` — core data (user_id scoped)
- `company_registry`, `roles_cache`, `api_profiles` — metadata
- `checkpoints` — pipeline state (one per user)
- `company_runs`, `job_runs` — run history
- `flagged_companies` — ATS failures

### 2. Determine migration number

Use timestamp-based naming: `YYYYMMDDHHMMSS_description.sql`

```bash
# Find the next number based on existing migrations
ls /Users/sakshambhatla/workplace/JobFinder/supabase/migrations/ | sort | tail -1
```

### 3. Write the migration

Create `supabase/migrations/<timestamp>_<description>.sql`:

**For new tables**, always include:
```sql
-- 1. Table with user_id foreign key
create table if not exists public.<table_name> (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  -- ... your columns ...
  created_at timestamptz default now()
);

-- 2. RLS policies (critical — never skip)
alter table public.<table_name> enable row level security;

create policy "<table_name>_select_own"
  on public.<table_name> for select
  using (auth.uid() = user_id);

create policy "<table_name>_insert_own"
  on public.<table_name> for insert
  with check (auth.uid() = user_id);

create policy "<table_name>_update_own"
  on public.<table_name> for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "<table_name>_delete_own"
  on public.<table_name> for delete
  using (auth.uid() = user_id);

-- 3. Index on user_id (always)
create index if not exists idx_<table_name>_user_id on public.<table_name>(user_id);
```

**For shared tables** (like `api_profiles`): no user_id column, readable by all, writable by authenticated:
```sql
create policy "<table_name>_select_all"
  on public.<table_name> for select using (true);

create policy "<table_name>_insert_authenticated"
  on public.<table_name> for insert
  with check (auth.role() = 'authenticated');
```

### 4. Update SupabaseStorageBackend (if needed)

If adding a new collection, update `jobfinder/storage/supabase_backend.py`:
- Add the collection → table mapping in the class docstring
- Add read/write handlers for the new collection

### 5. Update schemas (if needed)

If adding new data shapes, update `jobfinder/storage/schemas.py` with Pydantic models.

### 6. Verify

- Review the SQL for correctness
- Check that RLS policies are present and correct
- Ensure the migration is idempotent (`if not exists` / `or replace`)
- Run CLI tests to ensure nothing broke
