"""Tests for the context, specs, and help commands."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ._helpers import Harness


class TestRepoRootGuard(unittest.TestCase):
    """Commands other than `init` must error when no .trellis-lite/ is found."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="trellis-noinit-"))
        self.script = Path(__file__).resolve().parent.parent / ".trellis-lite/scripts/trellis.py"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python3", str(self.script), *args],
            cwd=str(self.tmpdir),
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_task_create_errors_outside_project(self) -> None:
        r = self._run(["task", "create", "X"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not inside a Trellis Lite project", r.stdout + r.stderr)

    def test_context_errors_outside_project(self) -> None:
        r = self._run(["context"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not inside a Trellis Lite project", r.stdout + r.stderr)

    def test_session_errors_outside_project(self) -> None:
        r = self._run(["session", "--title", "T"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not inside a Trellis Lite project", r.stdout + r.stderr)

    def test_init_works_outside_project(self) -> None:
        # init is the only command that creates .trellis-lite/, so it must
        # succeed even when no project exists on disk.
        r = self._run(["init", "tester"])
        self.assertEqual(r.returncode, 0, msg=f"init failed: {r.stdout}\n{r.stderr}")
        self.assertTrue((self.tmpdir / ".trellis-lite").is_dir())





class TestContext(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    def test_context_shows_developer(self) -> None:
        r = self.h.run(["context"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("tester", r.stdout)

    def test_context_shows_specs(self) -> None:
        spec_dir = self.h.tmpdir / ".trellis-lite/spec"
        (spec_dir / "my-spec.md").write_text("# spec")
        r = self.h.run(["context"])
        self.assertIn("my-spec.md", r.stdout)

    def test_context_shows_last_session(self) -> None:
        self.h.run(["session", "--title", "Latest session"])
        r = self.h.run(["context"])
        self.assertIn("Latest session", r.stdout)


class TestSpecs(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    def test_specs_lists_files(self) -> None:
        spec_dir = self.h.tmpdir / ".trellis-lite/spec"
        (spec_dir / "api.md").write_text("# api")
        (spec_dir / "db.md").write_text("# db")
        r = self.h.run(["specs"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("api.md", r.stdout)
        self.assertIn("db.md", r.stdout)

    def test_specs_empty(self) -> None:
        # Remove the template README.md so the spec dir is truly empty
        (self.h.tmpdir / ".trellis-lite/spec/README.md").unlink()
        r = self.h.run(["specs"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("No specs", r.stdout)


class TestHelp(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    def test_help_lists_commands(self) -> None:
        r = self.h.run(["help"])
        self.assertEqual(r.returncode, 0)
        for cmd in ("init", "task create", "task start", "task finish",
                    "task archive", "task cancel", "session", "context", "specs"):
            self.assertIn(cmd, r.stdout, f"help missing command: {cmd}")