"""Tests for the context, specs, and help commands."""

from __future__ import annotations

import re
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

    def test_context_warns_on_corrupted_active_task(self) -> None:
        """A corrupted active task.json must surface as a warning in `context`
        (the AI's cross-session resume entry point), not silently print
        `Title: ?` / `Status: ?` which is indistinguishable from a legitimately
        untitled task. Matches the F55 signal doctor gives for the same state."""
        from ._helpers import find_task
        self.h.run(["task", "create", "T", "--slug", "t"])
        bad = find_task(self.h.tmpdir, "t")
        (bad / "task.json").write_text("garbage not json", encoding="utf-8")
        r = self.h.run(["context"])
        self.assertEqual(r.returncode, 0, "context is a read — must stay exit 0")
        self.assertIn("corrupted", r.stdout)
        self.assertIn("doctor", r.stdout)
        # Must NOT print the silent `Title: ?` / `Status: ?` fallback.
        self.assertNotIn("Title:  ?", r.stdout)
        self.assertNotIn("Status: ?", r.stdout)

    def test_context_shows_wrap_status_for_last_done_task(self) -> None:
        """Batch 2: context surfaces WRAP incompleteness of the most recent
        done task — the AI's resume entry point must see un-closed loops."""
        from ._helpers import find_task
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        tdir = find_task(self.h.tmpdir, "t")
        (tdir / "prd.md").write_text("# PRD\n\n- [ ] verify output\n", encoding="utf-8")
        self.h.run(["task", "finish"])
        r = self.h.run(["context"])
        self.assertEqual(r.returncode, 0, "context is a read — must stay exit 0")
        self.assertIn("Last done task", r.stdout)
        self.assertIn("unchecked", r.stdout)

    def test_context_no_wrap_warning_for_fully_wrapped_task(self) -> None:
        from ._helpers import find_task
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        tdir = find_task(self.h.tmpdir, "t")
        (tdir / "prd.md").write_text("# PRD\n\n- [x] done\n", encoding="utf-8")
        self.h.run(["task", "finish"])
        self.h.run(["session", "--title", "wrapped", "--summary", "all good"])
        r = self.h.run(["context"])
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("⚠", r.stdout)


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
        # P3-E (round 10): enumeration completed — previously missing
        # task current / task list / task delete / doctor / help / version.
        for cmd in ("init", "task create", "task start", "task current",
                    "task finish", "task archive", "task cancel",
                    "task list", "task delete", "session", "context",
                    "specs", "doctor", "help", "version"):
            self.assertIn(cmd, r.stdout, f"help missing command: {cmd}")

    def test_help_description_column_aligned(self) -> None:
        """P3-E (round 10): every command row's description must start at
        the same visual column. Previously rows drifted 31–39 with no test
        guard. Strip ANSI escapes first so colored() output doesn't skew
        the measurement."""
        r = self.h.run(["help"])
        plain = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        cols: set[int] = set()
        for line in plain.splitlines():
            # Command rows: 2-space indent, signature, ≥2-space gap, desc.
            m = re.match(r"^  (\S.*?)(\s{2,})(\S.*)$", line)
            if m:
                # Description start column = signature + gap widths; both
                # vary per row but their sum must be the fixed column.
                cols.add(len(m.group(1)) + len(m.group(2)))
        self.assertTrue(cols, "no command rows matched — help layout changed?")
        self.assertEqual(len(cols), 1,
                         f"description column drifted across rows: {sorted(cols)}")