#!/usr/bin/env python3
"""
TASK 2b.5: Prune visibility_probes for runs older than retention_days.
Do not delete from visibility_runs; only from visibility_probes.
Run via cron e.g. daily: 0 2 * * * cd /path && python scripts/prune_old_probes.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_SRC = os.path.join(ROOT, "python", "src")
if PY_SRC not in sys.path:
    sys.path.insert(0, PY_SRC)

def main() -> None:
    try:
        import psycopg
    except ImportError:
        print("psycopg is required. pip install psycopg[binary]", file=sys.stderr)
        sys.exit(1)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)
    try:
        retention_days = int(os.getenv("RETENTION_DAYS", "30"))
    except ValueError:
        retention_days = 30
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM visibility_runs WHERE completed_at IS NOT NULL AND completed_at < %s",
                (cutoff,),
            )
            run_ids = [row[0] for row in cur.fetchall()]
            if not run_ids:
                print("No runs older than {} days to prune.".format(retention_days))
                return
            cur.execute(
                "DELETE FROM visibility_probes WHERE run_id = ANY(%s)",
                (run_ids,),
            )
            deleted = cur.rowcount
            conn.commit()
    print("Pruned {} probe rows for {} runs older than {} days.".format(deleted, len(run_ids), retention_days))


if __name__ == "__main__":
    main()
