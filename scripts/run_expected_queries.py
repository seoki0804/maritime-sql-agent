#!/usr/bin/env python3
"""Run expected SQL queries and print row counts.

Required environment variable:
    NEON_DSN
"""

from __future__ import annotations

import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUERY_FILE = PROJECT_ROOT / "queries" / "evaluation_questions.sql"


def get_connection(dsn: str):
    try:
        import psycopg

        return psycopg.connect(dsn)
    except ImportError:
        import psycopg2

        return psycopg2.connect(dsn)


def load_query_blocks() -> list[tuple[str, str]]:
    text = QUERY_FILE.read_text(encoding="utf-8")
    blocks: list[tuple[str, str]] = []
    current_label: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        label_match = re.match(r"^--\s*(Q\d+\s+\w+):\s*(.+)$", line)
        if label_match:
            if current_label and current_lines:
                blocks.append((current_label, "\n".join(current_lines).strip().rstrip(";")))
            current_label = f"{label_match.group(1)} - {label_match.group(2)}"
            current_lines = []
            continue

        if line.lstrip().startswith("--"):
            continue

        if current_label:
            current_lines.append(line)

    if current_label and current_lines:
        blocks.append((current_label, "\n".join(current_lines).strip().rstrip(";")))

    return blocks


def main() -> None:
    dsn = os.getenv("NEON_DSN")
    if not dsn:
        raise SystemExit("NEON_DSN is not set.")

    query_blocks = load_query_blocks()
    with get_connection(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SET search_path TO maritime_sql_agent, public")
            for label, sql in query_blocks:
                cur.execute(sql)
                rows = cur.fetchall()
                print(f"{label}\trows={len(rows)}")


if __name__ == "__main__":
    main()

