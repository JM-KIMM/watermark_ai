# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Read-only migration of the earlier SQLite sample to CSV; original stays untouched."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repository root
import argparse
from pathlib import Path
import sqlite3
from contextlib import closing

from csv_store import CSVStore


def migrate(source, destination):
    source = Path(source).resolve()
    store = CSVStore(destination)
    with closing(sqlite3.connect(source.as_uri()+"?mode=ro", uri=True)) as database:
        database.row_factory = sqlite3.Row
        with store._state(write=True) as state:
            if any(state[name] for name in ("campaigns", "tokens", "scans", "cases")):
                raise ValueError("대상 CSV 폴더가 비어 있지 않습니다. 다른 폴더를 지정하세요.")
            for name in ("campaigns", "tokens", "scans", "cases"):
                state[name] = [dict(row) for row in database.execute(f"SELECT * FROM {name}")]
            for row in state["campaigns"]:
                row.setdefault("starts", row["created"])
            state["counters"] = [dict(name=name, value=max((row["id"] for row in state[name]), default=0)) for name in ("scans", "cases")]
    return store


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="이전 SQLite를 읽기 전용으로 CSV에 이관")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = migrate(args.source, args.destination)
    print(f"CSV migration complete: {result.path}")
