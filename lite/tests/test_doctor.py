"""Tests for the `doctor` diagnostic command."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ._helpers import Harness, SCRIPT


class TestDoctor(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return self.h.run(args)

    def test_doctor_healthy_returns_zero(self) -> None:
        r = self._run(["doctor"])
        self.assertEqual(r.returncode, 0, f"doctor failed: {r.stdout}\n{r.stderr}")
        self.assertIn("All checks passed", r.stdout)
        self.assertIn(".trellis-lite/ present", r.stdout)

    def test_doctor_shows_developer(self) -> None:
        r = self._run(["doctor"])
        self.assertIn("Developer: tester", r.stdout)

    def test_doctor_warns_on_missing_subdir(self) -> None:
        # Remove spec/ to trigger a warning
        spec_dir = self.h.tmpdir / ".trellis-lite/spec"
        shutil.rmtree(spec_dir)
        r = self._run(["doctor"])
        self.assertEqual(r.returncode, 0, "warnings should still exit 0")
        self.assertIn("warning(s)", r.stdout)
        self.assertIn("spec/ missing", r.stdout)

    def test_doctor_fixes_missing_subdir(self) -> None:
        spec_dir = self.h.tmpdir / ".trellis-lite/spec"
        shutil.rmtree(spec_dir)
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0)
        self.assertTrue(spec_dir.is_dir(), "--fix should recreate spec/")
        # Now run doctor again — should be clean
        r2 = self._run(["doctor"])
        self.assertIn("All checks passed", r2.stdout)

    def test_doctor_fix_clears_subdir_warning_from_summary(self) -> None:
        """F19: --fix repaired warning should NOT appear in the final summary list."""
        spec_dir = self.h.tmpdir / ".trellis-lite/spec"
        shutil.rmtree(spec_dir)
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0)
        # The summary at the bottom must NOT list "spec/ missing" — it was fixed.
        # Find the summary section (starts with empty line + "⚠" or "✓" or "✗")
        out = r.stdout
        # Locate the final summary block
        summary_idx = out.rfind("Run with --fix")
        if summary_idx == -1:
            summary_idx = out.rfind("All checks passed")
        self.assertNotEqual(summary_idx, -1, "no summary line found")
        summary_block = out[summary_idx:]
        self.assertNotIn(
            "spec/ missing", summary_block,
            f"F19 regression: fixed warning still listed\n{out}",
        )

    def test_doctor_fix_creates_journal_without_remaining_warning(self) -> None:
        """F19: --fix creates journal-1.md; no warning should remain in summary."""
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        for j in ws.glob("journal-*.md"):
            j.unlink()
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0)
        self.assertTrue((ws / "journal-1.md").is_file(), "--fix should create journal-1.md")
        # Summary must NOT list "no journal files" — the bullet list comes
        # AFTER "All checks passed" / "⚠ N warning(s):". Inline diagnostic
        # output (printed during the check) is allowed to mention the text.
        out = r.stdout
        summary_idx = out.rfind("All checks passed")
        if summary_idx == -1:
            summary_idx = out.rfind("warning(s):")
        self.assertNotEqual(summary_idx, -1, "expected a summary block")
        summary_block = out[summary_idx:]
        self.assertNotIn("no journal files", summary_block)

    def test_doctor_warns_on_internal_journal_gap(self) -> None:
        """F20: gap in journal numbering (e.g. 1, 3, 5) is a warning."""
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        for j in ws.glob("journal-*.md"):
            j.unlink()
        (ws / "journal-1.md").write_text("# Journal 1\n")
        (ws / "journal-3.md").write_text("# Journal 3\n")
        r = self._run(["doctor"])
        self.assertIn("journal numbering gap", r.stdout)
        self.assertIn("1 → 3", r.stdout)

    def test_doctor_errors_on_stale_current_pointer(self) -> None:
        # Create a task, then delete its directory out from under .current-task
        self.h.run(["task", "create", "T", "--slug", "t"])
        task_dir = self.h.tmpdir / ".trellis-lite/tasks"
        # Find the task dir and delete it
        for d in task_dir.iterdir():
            if d.is_dir() and d.name != "archive":
                shutil.rmtree(d)
                break
        r = self._run(["doctor"])
        self.assertEqual(r.returncode, 1)
        self.assertIn(".current-task points to missing", r.stdout)

    def test_doctor_fix_clears_stale_current_pointer(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        task_dir = self.h.tmpdir / ".trellis-lite/tasks"
        for d in task_dir.iterdir():
            if d.is_dir() and d.name != "archive":
                shutil.rmtree(d)
                break
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0)
        # .current-task should be gone
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertFalse(ct.exists())

    def test_doctor_errors_when_no_trellis_dir(self) -> None:
        # Run in an empty tmpdir (no .trellis-lite)
        empty = Path(tempfile.mkdtemp(prefix="trellis-empty-"))
        try:
            r = subprocess.run(
                ["python3", str(SCRIPT), "doctor"],
                cwd=str(empty),
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(r.returncode, 1)
            self.assertIn(".trellis-lite", r.stdout + r.stderr)
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_doctor_detects_orphan_task_dir(self) -> None:
        # Create a task directory without task.json
        orphan = self.h.tmpdir / ".trellis-lite/tasks/MM-DD-ghost"
        orphan.mkdir(parents=True)
        r = self._run(["doctor"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("orphan", r.stdout)


if __name__ == "__main__":
    unittest.main()