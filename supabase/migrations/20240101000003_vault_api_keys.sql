-- Migration: per-user LLM API key storage via Supabase Vault
--
-- Vault secrets use the naming convention: user_{uuid}_{provider}_key
-- All functions are SECURITY DEFINER and granted only to service_role.

-- Ensure the Vault extension is available (enabled by default on Supabase).
CREATE EXTENSION IF NOT EXISTS supabase_vault CASCADE;

-- ── store_user_api_key ──────────────────────────────────────────────────────
-- Upsert: removes any existing secret for (user, provider), then creates new.
CREATE OR REPLACE FUNCTION store_user_api_key(
    p_user_id uuid,
    p_provider text,
    p_api_key text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault
AS $$
DECLARE
    v_name text := 'user_' || p_user_id::text || '_' || p_provider || '_key';
    v_existing_id uuid;
BEGIN
    -- Delete existing secret if present (idempotent upsert).
    SELECT id INTO v_existing_id FROM vault.secrets WHERE name = v_name LIMIT 1;
    IF v_existing_id IS NOT NULL THEN
        DELETE FROM vault.secrets WHERE id = v_existing_id;
    END IF;

    -- Store the new secret.
    PERFORM vault.create_secret(p_api_key, v_name, 'LLM API key for user ' || p_user_id::text || ', provider ' || p_provider);
END;
$$;

-- ── get_user_api_key ────────────────────────────────────────────────────────
-- Returns the decrypted API key, or NULL if none is stored.
CREATE OR REPLACE FUNCTION get_user_api_key(
    p_user_id uuid,
    p_provider text
) RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault
AS $$
DECLARE
    v_name text := 'user_' || p_user_id::text || '_' || p_provider || '_key';
    v_key text;
BEGIN
    SELECT decrypted_secret INTO v_key
    FROM vault.decrypted_secrets
    WHERE name = v_name
    LIMIT 1;

    RETURN v_key;
END;
$$;

-- ── delete_user_api_key ─────────────────────────────────────────────────────
-- Removes the stored secret for (user, provider). No-op if not present.
CREATE OR REPLACE FUNCTION delete_user_api_key(
    p_user_id uuid,
    p_provider text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault
AS $$
DECLARE
    v_name text := 'user_' || p_user_id::text || '_' || p_provider || '_key';
BEGIN
    DELETE FROM vault.secrets WHERE name = v_name;
END;
$$;

-- ── has_user_api_keys ───────────────────────────────────────────────────────
-- Returns {"anthropic": true/false, "gemini": true/false} without decrypting.
CREATE OR REPLACE FUNCTION has_user_api_keys(
    p_user_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault
AS $$
DECLARE
    v_prefix text := 'user_' || p_user_id::text || '_';
    v_anthropic boolean;
    v_gemini boolean;
BEGIN
    SELECT EXISTS(
        SELECT 1 FROM vault.secrets WHERE name = v_prefix || 'anthropic_key'
    ) INTO v_anthropic;

    SELECT EXISTS(
        SELECT 1 FROM vault.secrets WHERE name = v_prefix || 'gemini_key'
    ) INTO v_gemini;

    RETURN jsonb_build_object('anthropic', v_anthropic, 'gemini', v_gemini);
END;
$$;

-- ── Permissions ─────────────────────────────────────────────────────────────
-- Only the service_role (backend) can call these functions.
REVOKE ALL ON FUNCTION store_user_api_key(uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION store_user_api_key(uuid, text, text) TO service_role;

REVOKE ALL ON FUNCTION get_user_api_key(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION get_user_api_key(uuid, text) TO service_role;

REVOKE ALL ON FUNCTION delete_user_api_key(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION delete_user_api_key(uuid, text) TO service_role;

REVOKE ALL ON FUNCTION has_user_api_keys(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION has_user_api_keys(uuid) TO service_role;
