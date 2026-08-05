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
        # Initialize as a git repo so install.sh triggers the pre-commit hook
        # installation step (O9 fix path). Without .git/, install.sh silently
        # skips the hook step, leaving the uninstall cleanup code untested.
        subprocess.run(
            ["git", "init", "-q"],
            cwd=str(self.tmpdir), capture_output=True, text=True, timeout=10,
        )
        # Seed .gitignore so install.sh triggers the runtime-files step
        # (it checks existence of .gitignore before adding entries).
        (self.tmpdir / ".gitignore").write_text("node_modules/\n")

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

    # ---- O9 coverage: .gitignore cleanup + pre-commit hook removal ------

    def test_uninstall_removes_gitignore_entries(self) -> None:
        """O9: uninstall must clean up the Trellis block in .gitignore added by install.sh."""
        self._install_all()
        gitignore = self.tmpdir / ".gitignore"
        # Sanity: install populated the .gitignore block
        content_before = gitignore.read_text()
        self.assertIn("# Trellis Lite runtime", content_before)
        self.assertIn(".trellis-lite/.developer", content_before)
        self.assertIn(".trellis-lite/.current-task", content_before)

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")
        # Marker comment and Trellis entries must be gone
        content_after = gitignore.read_text()
        self.assertNotIn("# Trellis Lite runtime", content_after)
        self.assertNotIn(".trellis-lite/.developer", content_after)
        self.assertNotIn(".trellis-lite/.current-task", content_after)

    def test_uninstall_keeps_user_gitignore_entries(self) -> None:
        """Uninstall must preserve the user's own .gitignore entries."""
        self._install_all()
        gitignore = self.tmpdir / ".gitignore"
        # Append more user content AFTER the Trellis block
        with gitignore.open("a") as f:
            f.write("my-app/dist/\n")
            f.write("*.bak\n")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        content = gitignore.read_text()
        # User entries (before and after the Trellis block) must survive
        self.assertIn("node_modules/", content)
        self.assertIn("my-app/dist/", content)
        self.assertIn("*.bak", content)
        # Trellis block must be cleaned up
        self.assertNotIn("# Trellis Lite runtime", content)
        self.assertNotIn(".trellis-lite/.developer", content)
        self.assertNotIn(".trellis-lite/.current-task", content)

    def test_uninstall_removes_precommit_hook(self) -> None:
        """O9: uninstall must remove the pre-commit hook installed by install.sh."""
        self._install_all()
        hook = self.tmpdir / ".git/hooks/pre-commit"
        # Sanity: install populated the hook
        self.assertTrue(hook.is_file())
        self.assertIn("Trellis Lite", hook.read_text())

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        self.assertFalse(hook.exists(), "Trellis's pre-commit hook must be removed")

    def test_uninstall_keeps_user_precommit_hook(self) -> None:
        """Uninstall must not touch a pre-commit hook that's NOT Trellis's."""
        self._install_all()  # Installs the Trellis hook first
        # Then the user overwrites it with their own hook (no "Trellis Lite" marker)
        hook = self.tmpdir / ".git/hooks/pre-commit"
        hook.write_text("#!/usr/bin/env bash\necho 'user hook — runs my linter'\n")
        hook.chmod(0o755)

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        # User's hook must survive (uninstall only removes hooks containing "Trellis Lite")
        self.assertTrue(hook.exists(), "user's pre-commit hook must not be removed")
        self.assertNotIn("Trellis Lite", hook.read_text())

    # ---- O11 coverage: user-edited .gitignore block -------------------

    def test_uninstall_handles_user_edited_gitignore(self) -> None:
        """O11 regression: user comments/blanks between Trellis entries must NOT
        prevent cleanup of subsequent .trellis-lite/.X lines.

        Install normally first (so uninstall accepts the directory), then
        mutate the .gitignore to inject a user comment + blank line between
        the two runtime entries. The original awk reset `skip` on every
        non-matching line, which leaked the second entry. The fix keeps
        skip=1 across intervening user lines.
        """
        # Install normally — populates .gitignore block + runtime + platforms
        self._install_all()
        gitignore = self.tmpdir / ".gitignore"
        original = gitignore.read_text()
        # Sanity: install wrote both entries contiguously
        self.assertIn(".trellis-lite/.developer\n.trellis-lite/.current-task", original)

        # Simulate a user editing the block: insert a comment + blank line
        # between the two Trellis-managed entries.
        edited = original.replace(
            ".trellis-lite/.developer\n.trellis-lite/.current-task",
            ".trellis-lite/.developer\n# user-added note between entries\n\n.trellis-lite/.current-task",
        )
        self.assertNotEqual(edited, original, "test precondition: replacement should mutate content")
        gitignore.write_text(edited, encoding="utf-8")

        r = self._run_uninstall(str(self.tmpdir))
        self.assertEqual(r.returncode, 0, f"uninstall failed: {r.stdout}\n{r.stderr}")
        content = gitignore.read_text()
        # All Trellis runtime lines must be gone (the regression manifested here)
        self.assertNotIn(".trellis-lite/.developer", content)
        self.assertNotIn(".trellis-lite/.current-task", content)
        self.assertNotIn("# Trellis Lite runtime", content)
        # User content (before, between, and after the block) must survive
        self.assertIn("node_modules/", content)
        self.assertIn("user-added note between entries", content)