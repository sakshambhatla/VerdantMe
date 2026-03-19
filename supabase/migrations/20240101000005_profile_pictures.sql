-- Profile pictures: add avatar_url to profiles table + Supabase Storage bucket

-- ── Schema ─────────────────────────────────────────────────────────────────────
alter table public.profiles
  add column if not exists avatar_url text;

-- ── Storage bucket ─────────────────────────────────────────────────────────────
-- Public bucket — avatar URLs are safe to share; no sensitive data in images
insert into storage.buckets (id, name, public)
  values ('avatars', 'avatars', true)
  on conflict (id) do nothing;

-- ── Storage RLS ────────────────────────────────────────────────────────────────
-- Anyone can read avatars (public URLs)
create policy "Public avatar read"
  on storage.objects for select
  using (bucket_id = 'avatars');

-- Authenticated users can upload to their own path only ({userId}/avatar.jpg)
create policy "Users can upload own avatar"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'avatars'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Authenticated users can overwrite their own avatar
create policy "Users can update own avatar"
  on storage.objects for update
  to authenticated
  using (
    bucket_id = 'avatars'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Authenticated users can delete their own avatar
create policy "Users can delete own avatar"
  on storage.objects for delete
  to authenticated
  using (
    bucket_id = 'avatars'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
