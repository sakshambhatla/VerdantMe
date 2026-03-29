-- Add role-based access control to profiles.
-- Roles: superuser, devtest, customer (default), guest.
ALTER TABLE public.profiles
  ADD COLUMN role text NOT NULL DEFAULT 'customer'
  CONSTRAINT chk_profiles_role CHECK (role IN ('superuser', 'devtest', 'customer', 'guest'));
