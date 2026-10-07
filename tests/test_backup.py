import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = PROJECT_ROOT / "scripts" / "backup_fredtux.sh"


class BackupScriptKeepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.source_home = self.tmp / "source-home"
        (self.source_home / "fredTux-2-0").mkdir(parents=True)
        (self.source_home / ".fredtux-2.0").mkdir(parents=True)
        (self.source_home / "fredTux-2-0" / "hello.txt").write_text("welt\n", encoding="utf-8")
        self.dest = self.tmp / "backups"
        self.env = dict(os.environ)
        self.env["FREDTUX_HOME"] = str(self.source_home)
        self.env["HOME"] = str(self.source_home)

    def run_backup(self, *args):
        return subprocess.run(
            ["bash", str(BACKUP_SCRIPT), "--dest", str(self.dest), *args],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=120,
        )

    def backup_files(self):
        return sorted((self.dest).glob("fredtux-2.0-backup-*.tgz"))

    def test_keep_deletes_oldest_backups(self):
        # Drei Backups anlegen (ohne --keep wird nichts gelöscht).
        for _ in range(3):
            result = self.run_backup()
            self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(len(self.backup_files()), 3)

        # Viertes Backup mit --keep 2: älteste zwei müssen gelöscht werden.
        result = self.run_backup("--keep", "2")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(len(self.backup_files()), 2)

    def test_keep_above_total_keeps_all(self):
        for _ in range(2):
            self.run_backup()
        result = self.run_backup("--keep", "10")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(len(self.backup_files()), 3)

    def test_invalid_keep_value_fails(self):
        result = self.run_backup("--keep", "abc")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FEHLER", result.stderr)


if __name__ == "__main__":
    unittest.main()
