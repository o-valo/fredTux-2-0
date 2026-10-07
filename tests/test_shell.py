import tempfile
import unittest
from pathlib import Path

from fredtux.config import Config
from fredtux.tools.shell import ShellError, ShellTools


class ShellToolsTests(unittest.TestCase):
    def make_tools(self, mode="standard", write=True, extra_roots=()):
        root = Path(tempfile.mkdtemp())
        return root, ShellTools(
            Config(
                home=root,
                base_url="http://unused/v1",
                model="fake",
                api_key=None,
                shell_mode=mode,
                shell_root=root,
                shell_write_root=root,
                shell_extra_roots=extra_roots,
                shell_allowed_commands="pwd, ls, grep",
                shell_write_enabled=write,
            )
        )

    def test_allowlist_executes_only_configured_command(self):
        root, tools = self.make_tools("allowlist", write=False)
        self.assertIn(str(root), tools.execute_command("pwd"))
        with self.assertRaises(ShellError):
            tools.execute_command("rm -rf .")
        with self.assertRaises(ShellError):
            tools.execute_command("pwd; echo nope")

    def test_standard_mode_writes_only_inside_scope_and_protects_config(self):
        root, tools = self.make_tools("standard", write=True)
        self.assertIn("Geschrieben", tools.write_file("notes/test.txt", "hallo"))
        with self.assertRaises(ShellError):
            tools.write_file("../outside.txt", "nope")
        (root / "config.nd").write_text("secret=keep\n", encoding="utf-8")
        with self.assertRaises(ShellError):
            tools.write_file("config.nd", "changed")
        self.assertIn("Rechte", tools.change_permissions("notes/test.txt", "0640"))

    def test_yolo_mode_runs_bash_pipeline(self):
        _, tools = self.make_tools("yolo", write=True)
        result = tools.execute_command("printf yolo-ok")
        self.assertIn("yolo-ok", result)

    def test_coding_mode_runs_development_commands_with_pipeline_and_redirection(self):
        root, tools = self.make_tools("coding", write=True)
        result = tools.execute_command("python3 -c \"print('coding-ok')\" | grep coding")
        self.assertIn("coding-ok", result)
        self.assertEqual(tools.config.coding_timeout, 300.0)
        tools.execute_command("python3 -c \"print('saved')\" > coding-output.txt")
        self.assertEqual((root / "coding-output.txt").read_text(encoding="utf-8"), "saved\n")

    def test_coding_mode_rejects_arbitrary_commands_and_path_escape(self):
        root, tools = self.make_tools("coding", write=True)
        self.assertIn("exit=0", tools.execute_command(f"ls -la {root}"))
        self.assertIn("coding-script-ok", tools.execute_command("bash -c \"printf coding-script-ok\""))
        (root / "scripts").mkdir()
        (root / "scripts" / "backup_fredtux.sh").write_text("KEEP=1\\nBACKUP_DIR=./backups\\n", encoding="utf-8")
        (root / "feed.xml").write_text("<title>Neueste Meldung</title>\\n", encoding="utf-8")
        self.assertIn("exit=0", tools.execute_command("grep -n 'keep\\|BACKUP_DIR' scripts/backup_fredtux.sh | head -1"))
        self.assertIn("Neueste Meldung", tools.execute_command("grep -o '<title>[^<]*</title>' feed.xml | head -1"))
        self.assertIn("quoted-ok", tools.execute_command("python3 -c \"print('quoted-ok')\""))
        self.assertIn("field-ok", tools.execute_command("awk '{print $1}' <<< 'field-ok rest'"))
        self.assertIn("title-ok", tools.execute_command("sed -n '/title-ok/p' <<< 'title-ok rest'"))
        structured = tools.run_structured_command(
            [
                {"program": "python3", "args": ["-c", "print('structured-ok')"]},
                {"program": "grep", "args": ["structured"]},
            ],
            redirect_stdout="structured-output.txt",
        )
        self.assertIn("structured-ok", structured)
        self.assertEqual((root / "structured-output.txt").read_text(encoding="utf-8"), "structured-ok\n")
        tools.run_structured_command(
            [{"program": "python3", "args": ["-c", "print('step-output')"], "redirect_stdout": "step-output.txt"}]
        )
        self.assertEqual((root / "step-output.txt").read_text(encoding="utf-8"), "step-output\n")
        stdin_result = tools.run_structured_command(
            [{"program": "cat", "args": []}], stdin="structured-stdin-ok\n"
        )
        self.assertIn("structured-stdin-ok", stdin_result)
        stderr_result = tools.run_structured_command(
            [{"program": "python3", "args": ["-c", "import sys; print('out'); print('err', file=sys.stderr)"]}]
        )
        self.assertIn("err", stderr_result)
        discarded = tools.run_structured_command(
            [{"program": "python3", "args": ["-c", "import sys; print('out'); print('err', file=sys.stderr)"]}],
            stderr="discard",
        )
        self.assertNotIn("\nerr\n", discarded)
        with self.assertRaises(ShellError):
            tools.execute_command("sudo rm -rf .")
        with self.assertRaises(ShellError):
            tools.execute_command("python3 -c \"print('x')\" > ../outside.txt")
        with self.assertRaises(ShellError):
            tools.execute_command("python3 -c \"print('x')\"; echo nope")
        with self.assertRaises(ShellError):
            tools.execute_command("bash -c \"printf nope\"", cwd=str(root.parent))

    def test_coding_mode_allows_devnull_and_extra_roots(self):
        root, tools = self.make_tools("coding", write=True)
        self.assertIn("exit=0", tools.execute_command("python3 -c \"print('noise')\" > /dev/null"))
        self.assertIn("exit=0", tools.execute_command("true"))
        structured = tools.run_structured_command(
            [{"program": "python3", "args": ["-c", "print('devnull-ok')"], "redirect_stdout": "/dev/null"}]
        )
        self.assertIn("exit=0", structured)
        backup_root = Path(tempfile.mkdtemp())
        _, tools_with_extra = self.make_tools("coding", write=True, extra_roots=(backup_root,))
        self.assertIn(
            "exit=0",
            tools_with_extra.run_structured_command(
                [{"program": "python3", "args": ["-c", "print('backup-ok')"]}],
                redirect_stdout=str(backup_root / "backup-output.txt"),
            ),
        )

    def test_coding_mode_allows_paths_under_extra_root_only(self):
        root, tools = self.make_tools("coding", write=True)
        backup_root = Path(tempfile.mkdtemp())
        _, tools_with_extra = self.make_tools("coding", write=True, extra_roots=(backup_root,))
        target = backup_root / "fredtux-2.0-backups" / "out.txt"
        self.assertIn(
            "exit=0",
            tools_with_extra.execute_command(f"mkdir -p {backup_root}/fredtux-2.0-backups"),
        )
        self.assertIn(
            "exit=0",
            tools_with_extra.execute_command(f"touch {backup_root}/fredtux-2.0-backups/out.txt"),
        )
        self.assertTrue(target.exists())
        self.assertIn(
            "exit=0",
            tools_with_extra.run_structured_command(
                [{"program": "python3", "args": ["-c", "print('backup-output')"]}],
                redirect_stdout=str(target),
            ),
        )
        self.assertEqual(target.read_text(encoding="utf-8"), "backup-output\n")
        with self.assertRaises(ShellError):
            tools.execute_command(f"touch {backup_root}/outside-roots.txt")


if __name__ == "__main__":
    unittest.main()
