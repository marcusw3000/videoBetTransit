"""Create a consistent SQLite copy, including transactions currently in WAL."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument("source")
parser.add_argument("destination")
args = parser.parse_args()
source = Path(args.source).resolve(strict=True)
destination = Path(args.destination).resolve()
destination.parent.mkdir(parents=True, exist_ok=True)

with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30)) as source_db:
    if source_db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError(f"SQLite source failed quick_check: {source}")
    with closing(sqlite3.connect(destination, timeout=30)) as destination_db:
        source_db.backup(destination_db)
        if destination_db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError(f"SQLite backup failed quick_check: {destination}")
