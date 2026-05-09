#!/usr/bin/env python3
"""One-shot cleanup for doubled-phrase concept names.

Reads every row in ``concepts``, applies ``clean_concept_label``, and
writes back when the result differs. Idempotent — running it twice does
nothing on the second pass.

Use after pulling the phrase-dedup fix to scrub historical rows that
were ingested before the upstream fence was added in
``services/ingestion/orchestrator.py``.

Usage:
    .venv/bin/python script/clean_concept_names.py [--db PATH] [--dry-run]

Defaults to the SQLite path resolved by ``db.connect()`` for the
current environment.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from services.documents import clean_concept_label  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite path (defaults to db.DB_PATH from app_runtime).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    args = parser.parse_args()

    if args.db:
        conn = sqlite3.connect(args.db)
        conn.row_factory = sqlite3.Row
    else:
        conn = db.get_db()
    try:
        rows = conn.execute("SELECT id, name FROM concepts").fetchall()
        changed: list[tuple[str, str, str]] = []
        for row in rows:
            raw = str(row["name"] or "")
            cleaned = clean_concept_label(raw)
            if cleaned != raw:
                changed.append((row["id"], raw, cleaned))

        if not changed:
            print(f"No doubled-phrase rows found in {len(rows)} concepts.")
            return 0

        print(f"Found {len(changed)} concept(s) needing cleanup:")
        for _id, raw, cleaned in changed[:20]:
            print(f"  {raw!r} -> {cleaned!r}")
        if len(changed) > 20:
            print(f"  ... and {len(changed) - 20} more")

        if args.dry_run:
            print("Dry run; no rows written.")
            return 0

        conn.executemany(
            "UPDATE concepts SET name = ? WHERE id = ?",
            [(cleaned, _id) for _id, _raw, cleaned in changed],
        )
        conn.commit()
        print(f"Updated {len(changed)} row(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
