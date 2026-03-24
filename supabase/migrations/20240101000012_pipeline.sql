-- Pipeline: per-user job application tracking (Kanban board)

-- ── Pipeline Entries ────────────────────────────────────────────────────────
create table if not exists public.pipeline_entries (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  company_name    text not null,
  role_title      text,
  stage           text not null default 'not_started',
  note            text not null default '',
  next_action     text,
  badge           text,
  tags            text[] not null default '{}',
  sort_order      int not null default 0,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists idx_pipeline_entries_user
  on public.pipeline_entries (user_id, stage, sort_order);

alter table public.pipeline_entries enable row level security;

create policy "Users can manage own pipeline entries"
  on public.pipeline_entries for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Pipeline Updates (changelog) ────────────────────────────────────────────
create table if not exists public.pipeline_updates (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  entry_id        uuid not null references public.pipeline_entries(id) on delete cascade,
  update_type     text not null default 'note',
  from_stage      text,
  to_stage        text,
  message         text not null default '',
  created_at      timestamptz not null default now()
);

create index if not exists idx_pipeline_updates_entry
  on public.pipeline_updates (entry_id, created_at desc);

create index if not exists idx_pipeline_updates_user
  on public.pipeline_updates (user_id, created_at desc);

alter table public.pipeline_updates enable row level security;

create policy "Users can manage own pipeline updates"
  on public.pipeline_updates for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
