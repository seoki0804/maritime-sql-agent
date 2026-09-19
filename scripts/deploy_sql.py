#!/usr/bin/env python3
"""Apply project SQL files to Neon.

Required environment variable:
    NEON_DSN

Usage:
    python scripts/deploy_sql.py
    python scripts/deploy_sql.py --verify-only
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQL_FILES = [
    PROJECT_ROOT / "sql" / "01_schema.sql",
    PROJECT_ROOT / "sql" / "02_seed.sql",
]
VERIFY_SQL = PROJECT_ROOT / "sql" / "03_verify.sql"


def get_connection(dsn: str):
    try:
        import psycopg

        return psycopg.connect(dsn)
    except ImportError:
        import psycopg2

        return psycopg2.connect(dsn)


def execute_sql_files(dsn: str, sql_files: Iterable[Path]) -> None:
    with get_connection(dsn) as conn:
        with conn.cursor() as cur:
            for sql_file in sql_files:
                sql = sql_file.read_text(encoding="utf-8")
                print(f"Applying {sql_file.relative_to(PROJECT_ROOT)}")
                cur.execute(sql)
        conn.commit()


def run_verify(dsn: str) -> None:
    with get_connection(dsn) as conn:
        with conn.cursor() as cur:
            verify_sql = "\n".join(
                line
                for line in VERIFY_SQL.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("--")
            )
            statements = [
                stmt.strip()
                for stmt in verify_sql.split(";")
                if stmt.strip()
            ]
            for idx, stmt in enumerate(statements, start=1):
                print(f"\nVerification query {idx}")
                cur.execute(stmt)
                if cur.description is None:
                    print("OK")
                    continue
                rows = cur.fetchall()
                colnames = [desc[0] for desc in cur.description]
                print("\t".join(colnames))
                for row in rows:
                    print("\t".join("" if value is None else str(value) for value in row))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true", help="Run verification SQL without applying schema/seed.")
    args = parser.parse_args()

    dsn = os.getenv("NEON_DSN")
    if not dsn:
        raise SystemExit("NEON_DSN is not set. Put it in Colab Secrets or export it locally before running.")

    if not args.verify_only:
        execute_sql_files(dsn, DEFAULT_SQL_FILES)

    run_verify(dsn)


if __name__ == "__main__":
    main()
