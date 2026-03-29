-- Fix Google OAuth profile metadata: capture full_name and avatar_url from Google
-- Raw metadata keys from Supabase+Google: full_name, name, avatar_url, picture
-- Old trigger only checked 'display_name' (a key Google never sends), falling back to email.

-- ── Fix handle_new_user() trigger ────────────────────────────────────────────
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, display_name, avatar_url)
  values (
    new.id,
    coalesce(
      new.raw_user_meta_data->>'full_name',
      new.raw_user_meta_data->>'name',
      new.raw_user_meta_data->>'display_name',
      new.email
    ),
    coalesce(
      new.raw_user_meta_data->>'avatar_url',
      new.raw_user_meta_data->>'picture'
    )
  );
  return new;
end;
$$ language plpgsql security definer;

-- ── Backfill existing Google OAuth users ─────────────────────────────────────
-- Only updates rows where display_name was auto-generated (null or equals email)
-- and Google metadata has a real name. Never overwrites user-uploaded avatars.
update public.profiles p
set
  display_name = coalesce(
    u.raw_user_meta_data->>'full_name',
    u.raw_user_meta_data->>'name'
  ),
  avatar_url = coalesce(
    p.avatar_url,
    u.raw_user_meta_data->>'avatar_url',
    u.raw_user_meta_data->>'picture'
  ),
  updated_at = now()
from auth.users u
where p.id = u.id
  and (p.display_name is null or p.display_name = u.email)
  and (
    u.raw_user_meta_data->>'full_name' is not null
    or u.raw_user_meta_data->>'name' is not null
  );
