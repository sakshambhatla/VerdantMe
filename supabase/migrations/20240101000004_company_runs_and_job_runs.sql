-- ── Company Runs (matches existing Python schema) ───────────────────────────
create table if not exists public.company_runs (
  id              uuid primary key,
  user_id         uuid not null references auth.users(id) on delete cascade,
  run_name        text not null,
  source_type     text not null default 'resume',
  source_id       text not null default '',
  seed_companies  text[],
  companies       jsonb not null default '[]'::jsonb,
  created_at      timestamptz not null default now()
);
create index if not exists idx_company_runs_user on public.company_runs (user_id, created_at desc);

alter table public.company_runs enable row level security;
create policy "Users can manage own company runs"
  on public.company_runs for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Job Runs (role-discovery run tracking + metrics) ────────────────────────
create table if not exists public.job_runs (
  id                  uuid primary key,
  user_id             uuid not null references auth.users(id) on delete cascade,
  run_name            text not null,
  company_run_id      uuid,
  parent_job_run_id   uuid references public.job_runs(id) on delete set null,
  run_type            text not null default 'api',
  status              text not null default 'running',
  companies_input     text[] not null default '{}',
  metrics             jsonb not null default '{}'::jsonb,
  created_at          timestamptz not null default now(),
  completed_at        timestamptz
);
create index if not exists idx_job_runs_user on public.job_runs (user_id, created_at desc);
create index if not exists idx_job_runs_parent on public.job_runs (parent_job_run_id)
  where parent_job_run_id is not null;

alter table public.job_runs enable row level security;
create policy "Users can manage own job runs"
  on public.job_runs for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
