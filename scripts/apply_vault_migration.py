#!/usr/bin/env python3
"""Apply the Supabase vault migration (20240101000003_vault_api_keys.sql).

This script creates the four SECURITY DEFINER SQL functions that enable
per-user encrypted API key storage via Supabase Vault.

Usage
-----
If you have your Supabase DB password available:

    SUPABASE_DB_PASSWORD=your-db-password python scripts/apply_vault_migration.py

If you don't have the password handy, run without the env var and the script
will print the SQL for you to paste into the Supabase SQL editor instead.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POOLER_URL_FILE = REPO_ROOT / "supabase" / ".temp" / "pooler-url"
MIGRATION_FILE = REPO_ROOT / "supabase" / "migrations" / "20240101000003_vault_api_keys.sql"


def main() -> None:
    if not MIGRATION_FILE.exists():
        sys.exit(f"Migration file not found: {MIGRATION_FILE}")

    sql = MIGRATION_FILE.read_text()
    password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()

    if not password:
        # No password — print the SQL and a dashboard link so the user can
        # paste it into the Supabase SQL editor manually.
        project_ref = _read_project_ref()
        dashboard_url = f"https://supabase.com/dashboard/project/{project_ref}/sql/new"

        print("=" * 70)
        print("SUPABASE_DB_PASSWORD not set.")
        print()
        print("Option A — paste this SQL into the Supabase Dashboard SQL editor:")
        print(f"  {dashboard_url}")
        print()
        print("─" * 70)
        print(sql)
        print("─" * 70)
        print()
        print("Option B — set the password and re-run:")
        print("  SUPABASE_DB_PASSWORD=<your-db-password> python scripts/apply_vault_migration.py")
        print()
        print("Your DB password is in: Supabase Dashboard → Settings → Database → Database password")
        return

    # Build the connection URL with the password injected.
    base_url = POOLER_URL_FILE.read_text().strip()
    # base_url is like: postgresql://postgres.xxx@host:port/postgres
    # We need:           postgresql://postgres.xxx:PASSWORD@host:port/postgres
    if "@" not in base_url:
        sys.exit(f"Unexpected pooler URL format: {base_url}")

    user_part, host_part = base_url.split("@", 1)
    url_with_password = f"{user_part}:{password}@{host_part}"

    print(f"Applying vault migration to {host_part} ...")

    result = subprocess.run(
        ["psql", url_with_password, "-f", str(MIGRATION_FILE)],
        capture_output=False,
    )

    if result.returncode == 0:
        print()
        print("✓ Vault migration applied successfully.")
        print("  The following functions are now available:")
        print("    • store_user_api_key")
        print("    • get_user_api_key")
        print("    • delete_user_api_key")
        print("    • has_user_api_keys")
    else:
        sys.exit(f"\npsql exited with code {result.returncode}.")


def _read_project_ref() -> str:
    ref_file = REPO_ROOT / "supabase" / ".temp" / "project-ref"
    if ref_file.exists():
        return ref_file.read_text().strip()
    return "<your-project-ref>"


if __name__ == "__main__":
    main()
