#!/usr/bin/env python3
"""
Run visibility DB migrations in order (for Windows/CI where psql may be unavailable).
Usage: from repo root, run: python scripts/run_migrations.py
Requires: DATABASE_URL in env or .env; psycopg.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root = parent of scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "scripts" / "sql"
MIGRATIONS = [
    "visibility_schema.sql",
    "visibility_schema_v2.sql",
    "visibility_schema_query_runs.sql",
]


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass

    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print("ERROR: DATABASE_URL is not set. Set it in .env or your environment.", file=sys.stderr)
        return 1

    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg is not installed. pip install 'psycopg[binary]'", file=sys.stderr)
        return 1

    for name in MIGRATIONS:
        path = SQL_DIR / name
        if not path.exists():
            print(f"ERROR: {path} not found.", file=sys.stderr)
            return 1
        sql = path.read_text(encoding="utf-8")
        print(f"Applying {name}...")
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
    print("Migration completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
