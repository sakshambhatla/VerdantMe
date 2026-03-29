#!/usr/bin/env python3
"""Assign a role to a user in the JobFinder profiles table.

Requires ``SUPABASE_URL`` and ``SUPABASE_SECRET_KEY`` environment variables
(service-role key, NOT the publishable anon key).

Usage
-----
    python scripts/set_user_role.py --email alice@example.com --role superuser

If the env vars are missing, the script prints the equivalent SQL you can run
manually in the Supabase SQL Editor.

Manual SQL (Supabase SQL Editor)
--------------------------------
    -- Promote a user to superuser:
    UPDATE public.profiles SET role = 'superuser', updated_at = now()
    WHERE id = (SELECT id FROM auth.users WHERE email = 'alice@example.com');

    -- Demote back to customer:
    UPDATE public.profiles SET role = 'customer', updated_at = now()
    WHERE id = (SELECT id FROM auth.users WHERE email = 'alice@example.com');

    -- Check a user's current role:
    SELECT u.email, p.role
    FROM public.profiles p JOIN auth.users u ON u.id = p.id
    WHERE u.email = 'alice@example.com';
"""

from __future__ import annotations

import argparse
import os
import sys

VALID_ROLES = ("superuser", "devtest", "customer", "guest")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a user's role in JobFinder.")
    parser.add_argument("--email", required=True, help="User's email address")
    parser.add_argument(
        "--role",
        required=True,
        choices=VALID_ROLES,
        help="Role to assign",
    )
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")

    if not supabase_url or not secret_key:
        print("SUPABASE_URL and/or SUPABASE_SECRET_KEY not set.")
        print()
        print("Run this SQL in the Supabase SQL Editor instead:")
        print()
        print(f"  UPDATE public.profiles SET role = '{args.role}', updated_at = now()")
        print(f"  WHERE id = (SELECT id FROM auth.users WHERE email = '{args.email}');")
        sys.exit(1)

    try:
        from supabase import create_client
    except ImportError:
        print("Error: supabase-py is not installed.  Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    client = create_client(supabase_url, secret_key)

    # Look up user by email via auth.users (service role can read this)
    user_resp = client.auth.admin.list_users()
    user_match = None
    for u in user_resp:
        if hasattr(u, "email") and u.email == args.email:
            user_match = u
            break

    if not user_match:
        print(f"Error: No user found with email '{args.email}'.", file=sys.stderr)
        sys.exit(1)

    user_id = user_match.id
    print(f"Found user: {args.email} (id: {user_id})")

    # Update the role in profiles
    resp = (
        client.table("profiles")
        .update({"role": args.role, "updated_at": "now()"})
        .eq("id", str(user_id))
        .execute()
    )

    if resp.data:
        print(f"Successfully set role to '{args.role}' for {args.email}.")
    else:
        print(f"Warning: Update returned no data. The profile may not exist yet for user {user_id}.", file=sys.stderr)
        print("The user may need to log in once first to trigger profile creation.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
