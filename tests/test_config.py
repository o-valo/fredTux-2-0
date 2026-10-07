import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fredtux.config import Config


class QuickConfigTests(unittest.TestCase):
    def test_config_nd_loads_endpoint_and_skips_native_ollama_check(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.nd"
            path.write_text(
                "FREDTUX_BASE_URL=http://192.168.50.20:8000/v1\n"
                "FREDTUX_OLLAMA_URL=http://192.168.50.20:8000\n"
                "FREDTUX_MODEL=llm-bahnhof\n"
                "FREDTUX_SKIP_OLLAMA_CHECK=1\n"
                "FREDTUX_API_HOST=0.0.0.0\n"
                "FREDTUX_API_PORT=8765\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FREDTUX_CONFIG_FILE": str(path)}, clear=True):
                config = Config.from_env()
            self.assertEqual(config.base_url, "http://192.168.50.20:8000/v1")
            self.assertEqual(config.model, "llm-bahnhof")
            self.assertTrue(config.skip_ollama_check)
            self.assertEqual(config.api_host, "0.0.0.0")
            self.assertEqual(config.api_port, 8765)
            self.assertEqual(config.api_model, "fredtux-2-0")

    def test_environment_overrides_quick_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.nd"
            path.write_text("FREDTUX_MODEL=from-file\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"FREDTUX_CONFIG_FILE": str(path), "FREDTUX_MODEL": "from-environment"},
                clear=True,
            ):
                config = Config.from_env()
            self.assertEqual(config.model, "from-environment")

    def test_invalid_quick_config_has_location(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.nd"
            path.write_text("not a setting\n", encoding="utf-8")
            with patch.dict(os.environ, {"FREDTUX_CONFIG_FILE": str(path)}, clear=True):
                with self.assertRaisesRegex(ValueError, "config.nd:1"):
                    Config.from_env()

    def test_extra_roots_are_parsed_from_shell_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            backup_dir = base / "BACKUP"
            backup_dir.mkdir()
            path = base / "shell.nd"
            path.write_text(
                f"FREDTUX_SHELL_EXTRA_ROOTS={backup_dir}, ~/BACKUP\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FREDTUX_SHELL_CONFIG_FILE": str(path)}, clear=True):
                config = Config.from_env()
            self.assertEqual(config.shell_extra_roots[0], backup_dir.resolve())
            self.assertEqual(len(config.shell_extra_roots), 2)

    def test_extra_roots_default_to_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shell.nd"
            path.write_text("", encoding="utf-8")
            with patch.dict(os.environ, {"FREDTUX_SHELL_CONFIG_FILE": str(path)}, clear=True):
                config = Config.from_env()
            self.assertEqual(config.shell_extra_roots, ())


if __name__ == "__main__":
    unittest.main()
