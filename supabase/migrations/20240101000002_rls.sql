-- Row Level Security policies
-- Every user-scoped table: SELECT/INSERT/UPDATE/DELETE restricted to own rows

-- ── Profiles ──────────────────────────────────────────────────────────────────
alter table public.profiles enable row level security;

create policy "Users can view own profile"
  on public.profiles for select using (auth.uid() = id);
create policy "Users can update own profile"
  on public.profiles for update using (auth.uid() = id);

-- ── Resumes ───────────────────────────────────────────────────────────────────
alter table public.resumes enable row level security;

create policy "Users can manage own resumes"
  on public.resumes for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Companies ─────────────────────────────────────────────────────────────────
alter table public.companies enable row level security;

create policy "Users can manage own companies"
  on public.companies for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Roles ─────────────────────────────────────────────────────────────────────
alter table public.roles enable row level security;

create policy "Users can manage own roles"
  on public.roles for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Company Registry ──────────────────────────────────────────────────────────
alter table public.company_registry enable row level security;

create policy "Users can manage own registry"
  on public.company_registry for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Roles Cache ───────────────────────────────────────────────────────────────
alter table public.roles_cache enable row level security;

create policy "Users can manage own cache"
  on public.roles_cache for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── API Profiles (shared — no user_id) ────────────────────────────────────────
alter table public.api_profiles enable row level security;

create policy "Anyone can read API profiles"
  on public.api_profiles for select using (true);
create policy "Authenticated users can insert API profiles"
  on public.api_profiles for insert with check (auth.role() = 'authenticated');
create policy "Authenticated users can update API profiles"
  on public.api_profiles for update using (auth.role() = 'authenticated');

-- ── Checkpoints ───────────────────────────────────────────────────────────────
alter table public.checkpoints enable row level security;

create policy "Users can manage own checkpoints"
  on public.checkpoints for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Flagged Companies ─────────────────────────────────────────────────────────
alter table public.flagged_companies enable row level security;

create policy "Users can manage own flagged companies"
  on public.flagged_companies for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Job Queue ─────────────────────────────────────────────────────────────────
alter table public.job_queue enable row level security;

create policy "Users can manage own jobs"
  on public.job_queue for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ── Usage Events ──────────────────────────────────────────────────────────────
alter table public.usage_events enable row level security;

create policy "Users can view own usage"
  on public.usage_events for select using (auth.uid() = user_id);
create policy "Users can insert own usage"
  on public.usage_events for insert with check (auth.uid() = user_id);
