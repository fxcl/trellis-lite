"""Tests for the install.sh multi-platform installer."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ._helpers import INSTALL_SH, LITE_ROOT


class TestInstall(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="trellis-install-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_install(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(INSTALL_SH), str(self.tmpdir), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_install_default_creates_runtime_and_agents(self) -> None:
        r = self._run_install("tester")
        self.assertEqual(r.returncode, 0, f"install failed: {r.stdout}\n{r.stderr}")
        self.assertTrue((self.tmpdir / ".trellis-lite").is_dir())
        self.assertTrue((self.tmpdir / "AGENTS.md").is_file())
        # init should have been called — .developer present
        self.assertTrue((self.tmpdir / ".trellis-lite/.developer").is_file())

    def test_install_claude_only(self) -> None:
        r = self._run_install("tester", "--platforms", "claude")
        self.assertEqual(r.returncode, 0)
        self.assertTrue((self.tmpdir / "CLAUDE.md").is_file())
        self.assertFalse((self.tmpdir / "AGENTS.md").exists())
        self.assertFalse((self.tmpdir / ".clinerules").exists())

    def test_install_qoder_and_cline(self) -> None:
        r = self._run_install("tester", "--platforms", "qoder,cline")
        self.assertEqual(r.returncode, 0)
        self.assertTrue((self.tmpdir / "AGENTS.md").is_file())
        self.assertTrue((self.tmpdir / ".clinerules/trellis-lite.md").is_file())
        self.assertFalse((self.tmpdir / "CLAUDE.md").exists())

    def test_install_cleans_template_runtime_files(self) -> None:
        """If the template was committed with stray runtime state, install must wipe it."""
        template_runtime = LITE_ROOT / ".trellis-lite"
        # Plant a stale .developer — install should remove it before init rewrites
        stale = template_runtime / ".developer"
        had_stale = stale.is_file()
        if not had_stale:
            stale.write_text("name=stale\n")
        try:
            r = self._run_install("tester")
            self.assertEqual(r.returncode, 0)
            # After install, .developer must reflect the new init (tester), not stale
            installed_dev = self.tmpdir / ".trellis-lite/.developer"
            self.assertTrue(installed_dev.is_file())
            self.assertIn("tester", installed_dev.read_text())
        finally:
            if not had_stale:
                stale.unlink(missing_ok=True)