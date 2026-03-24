-- Migration: per-user Google OAuth token storage via Supabase Vault
--
-- Stores Google access + refresh tokens for Gmail/Calendar integration.
-- Vault secrets use the naming convention: user_{uuid}_google_access_token
-- and user_{uuid}_google_refresh_token.
-- All functions are SECURITY DEFINER and granted only to service_role.

-- ── store_google_tokens ───────────────────────────────────────────────────
-- Upsert: removes any existing tokens, then creates new vault secrets.
CREATE OR REPLACE FUNCTION store_google_tokens(
    p_user_id uuid,
    p_access_token text,
    p_refresh_token text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault
AS $$
DECLARE
    v_access_name  text := 'user_' || p_user_id::text || '_google_access_token';
    v_refresh_name text := 'user_' || p_user_id::text || '_google_refresh_token';
    v_existing_id  uuid;
BEGIN
    -- Delete existing access token if present
    SELECT id INTO v_existing_id FROM vault.secrets WHERE name = v_access_name LIMIT 1;
    IF v_existing_id IS NOT NULL THEN
        DELETE FROM vault.secrets WHERE id = v_existing_id;
    END IF;

    -- Delete existing refresh token if present
    SELECT id INTO v_existing_id FROM vault.secrets WHERE name = v_refresh_name LIMIT 1;
    IF v_existing_id IS NOT NULL THEN
        DELETE FROM vault.secrets WHERE id = v_existing_id;
    END IF;

    -- Store new tokens
    PERFORM vault.create_secret(p_access_token, v_access_name, 'Google access token for user ' || p_user_id::text);
    PERFORM vault.create_secret(p_refresh_token, v_refresh_name, 'Google refresh token for user ' || p_user_id::text);
END;
$$;

-- ── get_google_tokens ─────────────────────────────────────────────────────
-- Returns {access_token, refresh_token} JSONB, or NULL if not stored.
CREATE OR REPLACE FUNCTION get_google_tokens(
    p_user_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault
AS $$
DECLARE
    v_access_name  text := 'user_' || p_user_id::text || '_google_access_token';
    v_refresh_name text := 'user_' || p_user_id::text || '_google_refresh_token';
    v_access  text;
    v_refresh text;
BEGIN
    SELECT decrypted_secret INTO v_access
    FROM vault.decrypted_secrets
    WHERE name = v_access_name
    LIMIT 1;

    SELECT decrypted_secret INTO v_refresh
    FROM vault.decrypted_secrets
    WHERE name = v_refresh_name
    LIMIT 1;

    IF v_access IS NULL AND v_refresh IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN jsonb_build_object('access_token', v_access, 'refresh_token', v_refresh);
END;
$$;

-- ── delete_google_tokens ──────────────────────────────────────────────────
-- Removes both stored tokens. No-op if not present.
CREATE OR REPLACE FUNCTION delete_google_tokens(
    p_user_id uuid
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault
AS $$
DECLARE
    v_access_name  text := 'user_' || p_user_id::text || '_google_access_token';
    v_refresh_name text := 'user_' || p_user_id::text || '_google_refresh_token';
BEGIN
    DELETE FROM vault.secrets WHERE name = v_access_name;
    DELETE FROM vault.secrets WHERE name = v_refresh_name;
END;
$$;

-- ── has_google_tokens ─────────────────────────────────────────────────────
-- Returns true/false without decrypting.
CREATE OR REPLACE FUNCTION has_google_tokens(
    p_user_id uuid
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault
AS $$
DECLARE
    v_refresh_name text := 'user_' || p_user_id::text || '_google_refresh_token';
    v_exists boolean;
BEGIN
    SELECT EXISTS(
        SELECT 1 FROM vault.secrets WHERE name = v_refresh_name
    ) INTO v_exists;
    RETURN v_exists;
END;
$$;

-- ── Permissions ───────────────────────────────────────────────────────────
-- Only the service_role (backend) can call these functions.
REVOKE ALL ON FUNCTION store_google_tokens(uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION store_google_tokens(uuid, text, text) TO service_role;

REVOKE ALL ON FUNCTION get_google_tokens(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION get_google_tokens(uuid) TO service_role;

REVOKE ALL ON FUNCTION delete_google_tokens(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION delete_google_tokens(uuid) TO service_role;

REVOKE ALL ON FUNCTION has_google_tokens(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION has_google_tokens(uuid) TO service_role;
