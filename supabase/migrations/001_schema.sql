-- VerdantMe database schema
-- All user-scoped tables include user_id with RLS (see 002_rls.sql)

-- ── Profiles (auto-created on signup) ─────────────────────────────────────────
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  tier        text not null default 'free',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ── Resumes ───────────────────────────────────────────────────────────────────
create table if not exists public.resumes (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  filename    text not null,
  full_text   text not null default '',
  skills      text[] not null default '{}',
  job_titles  text[] not null default '{}',
  parsed_at   timestamptz not null default now(),
  created_at  timestamptz not null default now(),
  constraint  uq_resumes_user unique (user_id)
);

-- ── Companies ─────────────────────────────────────────────────────────────────
create table if not exists public.companies (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  name            text not null,
  career_page_url text,
  ats_type        text,
  ats_board_token text,
  reason          text,
  discovered_at   timestamptz not null default now(),
  created_at      timestamptz not null default now(),
  constraint      uq_companies_user_name unique (user_id, name)
);
create unique index if not exists idx_companies_user_name_lower on public.companies (user_id, lower(name));

-- ── Roles ─────────────────────────────────────────────────────────────────────
create table if not exists public.roles (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  company_name    text not null,
  title           text not null,
  location        text,
  url             text,
  department      text,
  ats_type        text,
  relevance_score real,
  summary         text,
  is_filtered     boolean not null default false,
  fetched_at      timestamptz not null default now(),
  created_at      timestamptz not null default now(),
  constraint      uq_roles_user_url unique (user_id, url)
);

-- ── Company Registry ──────────────────────────────────────────────────────────
create table if not exists public.company_registry (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  name            text not null,
  ats_type        text,
  ats_board_token text,
  career_page_url text,
  searchable      boolean not null default false,
  created_at      timestamptz not null default now(),
  constraint      uq_registry_user_name unique (user_id, name)
);
create unique index if not exists idx_registry_user_name_lower on public.company_registry (user_id, lower(name));

-- ── Roles Cache ───────────────────────────────────────────────────────────────
create table if not exists public.roles_cache (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  company_name  text not null,
  ats_type      text not null,
  cached_at     timestamptz not null default now(),
  roles         jsonb not null default '[]'::jsonb,
  created_at    timestamptz not null default now(),
  constraint    uq_roles_cache unique (user_id, company_name, ats_type)
);

-- ── API Profiles (shared across users — no user_id) ──────────────────────────
create table if not exists public.api_profiles (
  id        uuid primary key default gen_random_uuid(),
  domain    text not null unique,
  endpoints jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- ── Checkpoints ───────────────────────────────────────────────────────────────
create table if not exists public.checkpoints (
  id        uuid primary key default gen_random_uuid(),
  user_id   uuid not null references auth.users(id) on delete cascade,
  data      jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_checkpoints_user unique (user_id)
);

-- ── Flagged Companies ─────────────────────────────────────────────────────────
create table if not exists public.flagged_companies (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  name            text not null,
  ats_type        text,
  career_page_url text,
  reason          text,
  created_at      timestamptz not null default now(),
  constraint      uq_flagged_user_name unique (user_id, name)
);

-- ── Future: Job Queue ─────────────────────────────────────────────────────────
create table if not exists public.job_queue (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  type        text not null,
  status      text not null default 'pending',
  params      jsonb not null default '{}'::jsonb,
  result      jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ── Future: Usage Events ──────────────────────────────────────────────────────
create table if not exists public.usage_events (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  event_type  text not null,
  tokens_in   int not null default 0,
  tokens_out  int not null default 0,
  model       text,
  created_at  timestamptz not null default now()
);

-- ── Auto-create profile on signup ─────────────────────────────────────────────
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'display_name', new.email));
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
