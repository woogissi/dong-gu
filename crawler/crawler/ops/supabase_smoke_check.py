from __future__ import annotations

import argparse
import uuid

from psycopg2 import errors
from psycopg2.extras import RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.state.crawler_state_store import CrawlerStateStore


STATE_TABLES = ("crawler_documents", "crawler_dynamic_seeds", "crawler_retry_queue")


def table_status(loader: PGVectorLoader) -> list[dict]:
    with loader.conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
              c.relname AS table_name,
              c.relrowsecurity AS rls_enabled,
              c.relforcerowsecurity AS rls_forced
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = ANY(%s)
            ORDER BY c.relname;
            """,
            (list(STATE_TABLES),),
        )
        return [dict(row) for row in cur.fetchall()]


def run_write_smoke(loader: PGVectorLoader) -> None:
    token = uuid.uuid4().hex
    canonical_url = f"https://smoke.local/{token}"
    with loader.conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO crawler_dynamic_seeds (
              url, canonical_url, confidence, source_type, source_group, page_kind, pattern_reason, status
            )
            VALUES (%s, %s, 0.99, 'smoke', 'smoke', 'board_list', 'smoke_check', 'candidate')
            RETURNING id;
            """,
            (canonical_url, canonical_url),
        )
        seed_id = cur.fetchone()[0]

        cur.execute("SELECT status FROM crawler_dynamic_seeds WHERE id = %s;", (seed_id,))
        if cur.fetchone()[0] != "candidate":
            raise RuntimeError("select check returned unexpected dynamic seed status")

        cur.execute(
            "UPDATE crawler_dynamic_seeds SET status = 'smoke_updated', updated_at = now() WHERE id = %s;",
            (seed_id,),
        )
        if cur.rowcount != 1:
            raise RuntimeError("update check did not modify the smoke row")

        cur.execute("DELETE FROM crawler_dynamic_seeds WHERE id = %s;", (seed_id,))
        if cur.rowcount != 1:
            raise RuntimeError("delete check did not remove the smoke row")

    loader.commit()


def classify_db_error(exc: Exception) -> str:
    if isinstance(exc, errors.InsufficientPrivilege):
        return "permission_denied"
    if isinstance(exc, errors.UndefinedTable):
        return "missing_table"
    if isinstance(exc, errors.UniqueViolation):
        return "constraint_conflict"
    return exc.__class__.__name__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-check Supabase crawler state tables.")
    parser.add_argument(
        "--ensure-tables",
        action="store_true",
        help="Run idempotent crawler state table DDL before checking access.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    loader = PGVectorLoader(autocommit_writes=False)
    try:
        if args.ensure_tables:
            store = CrawlerStateStore(loader=loader)
            store.ensure_tables()

        statuses = table_status(loader)
        found = {row["table_name"] for row in statuses}
        missing = sorted(set(STATE_TABLES) - found)
        if missing:
            print(f"[SMOKE FAIL] missing_table tables={','.join(missing)}")
            raise SystemExit(2)

        for row in statuses:
            print(
                "[SMOKE TABLE] "
                f"name={row['table_name']} rls_enabled={row['rls_enabled']} "
                f"rls_forced={row['rls_forced']}"
            )

        try:
            run_write_smoke(loader)
        except Exception as exc:
            loader.rollback()
            reason = classify_db_error(exc)
            print(f"[SMOKE FAIL] write_check reason={reason} error={exc}")
            raise SystemExit(3)

        print("[SMOKE OK] crawler state tables are reachable and writable through the configured DB connection")
    finally:
        loader.close()


if __name__ == "__main__":
    main()
