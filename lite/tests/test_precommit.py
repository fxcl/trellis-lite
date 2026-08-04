"""Tests for the pre-commit hook script."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ._helpers import Harness, LITE_ROOT, SCRIPT

HOOK_SRC = LITE_ROOT / "hooks" / "pre-commit"


class TestPreCommitHook(unittest.TestCase):
    def setUp(self) -> None:
        # Initialize a Trellis project + git repo to simulate real env
        self.h = Harness()
        # install.sh copies the whole .trellis-lite/ into the target dir
        # (including scripts/trellis.py). The Harness runs `init` against the
        # canonical script in the Trellis repo, but for the hook to find a
        # script inside the test repo we must mirror that install step.
        target_scripts = self.h.tmpdir / ".trellis-lite/scripts"
        target_scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy(SCRIPT, target_scripts / "trellis.py")
        subprocess.run(
            ["git", "init", "-q"],
            cwd=str(self.h.tmpdir),
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(self.h.tmpdir), capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(self.h.tmpdir), capture_output=True, text=True, timeout=10,
        )
        # Some environments (including this dev's) set a global
        # core.hooksPath that points to ~/.config/git/hooks. Override it
        # locally so the hook installed under .git/hooks/ is actually run.
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath", str(self.h.tmpdir / ".git/hooks")],
            cwd=str(self.h.tmpdir), capture_output=True, text=True, timeout=10,
        )

    def tearDown(self) -> None:
        self.h.cleanup()

    def _install_hook(self) -> None:
        """Copy the bundled hook to .git/hooks/pre-commit."""
        hooks_dir = self.h.tmpdir / ".git/hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(HOOK_SRC, hooks_dir / "pre-commit")
        (hooks_dir / "pre-commit").chmod(0o755)

    def test_hook_passes_on_healthy_repo(self) -> None:
        self._install_hook()
        # Make a small commit to trigger the hook
        (self.h.tmpdir / "README.md").write_text("hello\n")
        r = subprocess.run(
            ["git", "add", "README.md"],
            cwd=str(self.h.tmpdir), capture_output=True, text=True,
        )
        r = subprocess.run(
            ["git", "commit", "-m", "test"],
            cwd=str(self.h.tmpdir), capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, f"commit failed: {r.stdout}\n{r.stderr}")

    def test_hook_blocks_on_orphan_task(self) -> None:
        self._install_hook()
        # Create an orphan task dir (no task.json) — doctor will complain
        (self.h.tmpdir / ".trellis-lite/tasks/MM-DD-ghost").mkdir(parents=True)
        (self.h.tmpdir / "README.md").write_text("hello\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=str(self.h.tmpdir), capture_output=True, text=True,
        )
        r = subprocess.run(
            ["git", "commit", "-m", "test"],
            cwd=str(self.h.tmpdir), capture_output=True, text=True,
        )
        self.assertNotEqual(r.returncode, 0, "hook should block on orphan task dir")
        self.assertIn("trellis", (r.stdout + r.stderr).lower())

    def test_hook_silent_when_trellis_not_installed(self) -> None:
        # No Trellis install — hook should exit 0 without doing anything
        empty = Path(tempfile.mkdtemp(prefix="trellis-no-hook-"))
        try:
            subprocess.run(
                ["git", "init", "-q"],
                cwd=str(empty), capture_output=True, text=True, timeout=10,
            )
            hooks_dir = empty / ".git/hooks"
            hooks_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(HOOK_SRC, hooks_dir / "pre-commit")
            (hooks_dir / "pre-commit").chmod(0o755)
            (empty / "x.txt").write_text("hi\n")
            subprocess.run(
                ["git", "add", "x.txt"],
                cwd=str(empty), capture_output=True, text=True,
            )
            r = subprocess.run(
                ["git", "commit", "-m", "test"],
                cwd=str(empty), capture_output=True, text=True,
            )
            # Hook should pass through (exit 0) without printing anything about trellis
            self.assertEqual(r.returncode, 0)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()