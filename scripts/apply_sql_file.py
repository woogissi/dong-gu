from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def database_url() -> str:
    load_env(ROOT / ".env")
    value = (os.getenv("DATABASE_URL") or os.getenv("CRAWLER_DATABASE_URL") or "").strip()
    if value.startswith("postgresql+psycopg2://"):
        return value.replace("postgresql+psycopg2://", "postgresql://", 1)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a SQL file to the configured Postgres database.")
    parser.add_argument("path", help="SQL file path relative to the repository root")
    args = parser.parse_args()

    sql_path = (ROOT / args.path).resolve()
    if not sql_path.is_relative_to(ROOT):
        raise SystemExit("SQL path must stay inside the repository")
    sql = sql_path.read_text(encoding="utf-8")

    dsn = database_url()
    if not dsn:
        raise SystemExit("DATABASE_URL or CRAWLER_DATABASE_URL is required")

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Applied {sql_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
