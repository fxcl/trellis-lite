"""Tests for the install.sh and uninstall.sh lifecycle."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ._helpers import INSTALL_SH, LITE_ROOT

UNINSTALL_SH = LITE_ROOT / "uninstall.sh"


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


class TestUninstall(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="trellis-uninstall-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_uninstall(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(UNINSTALL_SH), *args],
            cwd=str(self.tmpdir),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _install_all(self) -> None:
        subprocess.run(
            ["bash", str(INSTALL_SH), str(self.tmpdir), "tester", "--platforms", "all"],
            capture_output=True, text=True, timeout=30, check=True,
        )

    def test_uninstall_removes_runtime_and_entries(self) -> None:
        self._install_all()
        # Sanity: install populated everything
        for p in (".trellis-lite", "AGENTS.md", "CLAUDE.md", ".clinerules"):
            self.assertTrue((self.tmpdir / p).exists(), f"{p} should exist post-install")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")

        # Runtime and platform entries must be gone
        for p in (".trellis-lite", "AGENTS.md", "CLAUDE.md", ".clinerules"):
            self.assertFalse((self.tmpdir / p).exists(), f"{p} should be removed post-uninstall")

    def test_uninstall_refuses_when_nothing_installed(self) -> None:
        """Empty dir with no Trellis artifacts must be rejected, not silently OK."""
        r = self._run_uninstall(str(self.tmpdir))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not appear to have Trellis Lite installed", r.stdout + r.stderr)

    def test_uninstall_default_target_is_cwd(self) -> None:
        """When called without args, uninstall operates on cwd."""
        self._install_all()
        # Run uninstall from inside the project, with no args
        r = subprocess.run(
            ["bash", str(UNINSTALL_SH)],
            cwd=str(self.tmpdir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.tmpdir / ".trellis-lite").exists())

    def test_uninstall_keeps_other_files(self) -> None:
        """Uninstall must not touch unrelated files."""
        self._install_all()
        # Create a marker file
        marker = self.tmpdir / "user_data.txt"
        marker.write_text("important data")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        self.assertTrue(marker.exists(), "uninstall must not delete unrelated files")
        self.assertEqual(marker.read_text(), "important data")