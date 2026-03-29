-- TheirStack API credit tracking (JSONB blob, one row per user)

create table if not exists public.theirstack_credits (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_theirstack_credits_user unique (user_id)
);

alter table public.theirstack_credits enable row level security;

create policy "Users can manage own theirstack credits"
  on public.theirstack_credits for all using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create index if not exists idx_theirstack_credits_user_id
  on public.theirstack_credits(user_id);
