import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class OperationalScriptTests(unittest.TestCase):
    def test_sqlite_backup_includes_committed_wal_data(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite3"
            destination = Path(directory) / "backup.sqlite3"
            connection = sqlite3.connect(source)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO events(value) VALUES('committed-in-wal')")
            connection.commit()
            subprocess.run([sys.executable, str(ROOT / "scripts/backup-sqlite.py"), str(source), str(destination)], check=True)
            with closing(sqlite3.connect(destination)) as restored:
                self.assertEqual("committed-in-wal", restored.execute("SELECT value FROM events").fetchone()[0])
            connection.close()

    @unittest.skipUnless(os.name == "nt", "PowerShell recovery script is Windows-specific")
    def test_restore_rejects_manifest_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            backup = base / "backup"
            target = base / "target"
            (target / "backend/TrafficCounter.Api").mkdir(parents=True)
            (target / "vision-worker").mkdir(parents=True)
            backup.mkdir()
            outside_source = base / "escape.txt"
            outside_source.write_text("do not copy", encoding="utf-8")
            manifest = {
                "SchemaVersion": 2,
                "Items": [{
                    "Path": "../escape.txt",
                    "Length": outside_source.stat().st_size,
                    "Sha256": hashlib.sha256(outside_source.read_bytes()).hexdigest().upper(),
                }],
            }
            (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run([
                "powershell", "-NoProfile", "-File", str(ROOT / "scripts/Restore-VideoBetTransit.ps1"),
                "-BackupPath", str(backup), "-TargetRoot", str(target), "-ConfirmOverwrite",
            ], capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("fora do escopo", result.stderr + result.stdout)

    @unittest.skipUnless(os.name == "nt", "PowerShell recovery script is Windows-specific")
    def test_restore_verifies_and_copies_valid_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            backup = base / "backup"
            target = base / "target"
            relative = Path("backend/TrafficCounter.Api/trafficcounter.db")
            (backup / relative).parent.mkdir(parents=True)
            (target / "backend/TrafficCounter.Api").mkdir(parents=True)
            (target / "vision-worker").mkdir(parents=True)
            content = b"verified backup"
            (backup / relative).write_bytes(content)
            (backup / "manifest.json").write_text(json.dumps({
                "SchemaVersion": 2,
                "Items": [{"Path": relative.as_posix(), "Length": len(content),
                           "Sha256": hashlib.sha256(content).hexdigest().upper()}],
            }), encoding="utf-8")
            subprocess.run([
                "powershell", "-NoProfile", "-File", str(ROOT / "scripts/Restore-VideoBetTransit.ps1"),
                "-BackupPath", str(backup), "-TargetRoot", str(target), "-ConfirmOverwrite",
            ], check=True, capture_output=True, text=True)
            self.assertEqual(content, (target / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
