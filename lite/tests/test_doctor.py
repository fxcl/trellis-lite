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

    def test_doctor_fix_recovers_developer_from_single_workspace(self) -> None:
        """When .developer is missing but workspace/ has exactly one subdir,
        --fix must restore that name — NOT fall back to "developer" — so the
        user's existing journals stay reachable. Previously --fix wrote
        name=developer unconditionally, orphaning workspace/<real-name>/ and
        making `session`/`context` target a fresh empty workspace."""
        dev_file = self.h.tmpdir / ".trellis-lite/.developer"
        # tester/ is the real workspace (created by Harness). Wipe .developer
        # so doctor sees it missing but workspace/tester/ still has journals.
        dev_file.unlink()
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(dev_file.read_text().strip(), "name=tester",
                         f"--fix must recover developer name from the single "
                         f"workspace subdir, got:\n{dev_file.read_text()}")
        # Subsequent doctor must be healthy with developer=tester (journals intact).
        r2 = self._run(["doctor"])
        self.assertEqual(r2.returncode, 0)
        self.assertIn("Developer: tester", r2.stdout)

    def test_doctor_fix_defaults_developer_when_workspace_empty_or_ambiguous(self) -> None:
        """When .developer is missing AND workspace/ has zero or 2+ subdirs,
        --fix falls back to the generic 'developer' default (no single name
        to recover). Both branches must not crash and must write a valid file."""
        for n_subdirs in (0, 2):
            with self.subTest(n_subdirs=n_subdirs):
                # Fresh harness per subcase so we control workspace/ contents.
                h = Harness()
                try:
                    ws_root = h.tmpdir / ".trellis-lite/workspace"
                    # Remove the harness-created tester/ so we start clean.
                    shutil.rmtree(ws_root)
                    ws_root.mkdir()
                    if n_subdirs == 2:
                        (ws_root / "alice").mkdir()
                        (ws_root / "bob").mkdir()
                    # n_subdirs == 0: leave workspace/ empty
                    dev = h.tmpdir / ".trellis-lite/.developer"
                    self.assertTrue(dev.is_file())  # harness ran init
                    dev.unlink()
                    r = h.run(["doctor", "--fix"])
                    self.assertEqual(r.returncode, 0)
                    self.assertEqual(dev.read_text().strip(), "name=developer",
                                     f"expected fallback name=developer for "
                                     f"{n_subdirs} subdirs, got:\n{dev.read_text()}")
                finally:
                    h.cleanup()

    def test_doctor_fix_recovers_developer_name_line_when_file_half_written(self) -> None:
        """P2-1 (round 9): .developer exists but has no name= line (editor
        crash / partial sync). `session` recommends `doctor --fix` in this
        state, so --fix must actually repair it — previously the fix branch
        only existed for the missing-file case, making the recommended
        recovery path a dead end. Recovery must reuse the single-workspace
        subdir identity so journals stay reachable."""
        dev_file = self.h.tmpdir / ".trellis-lite/.developer"
        dev_file.write_text("garbage\n", encoding="utf-8")
        # Plain doctor surfaces the warning (exit 0, warning-level).
        r = self._run(["doctor"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("no name= line", r.stdout)
        # doctor --fix must actually repair it (recovering 'tester' from the
        # single workspace subdir created by the Harness).
        r2 = self._run(["doctor", "--fix"])
        self.assertEqual(r2.returncode, 0)
        self.assertEqual(dev_file.read_text().strip(), "name=tester",
                         f"--fix must recover the developer name from the "
                         f"single workspace subdir, got:\n{dev_file.read_text()}")
        # And the follow-up session-facing command works again.
        r3 = self._run(["doctor"])
        self.assertEqual(r3.returncode, 0)
        self.assertIn("Developer: tester", r3.stdout)
        self.assertNotIn("no name= line", r3.stdout)

    def test_doctor_fix_warns_about_orphaned_workspaces(self) -> None:
        """P3-5c (round 9): when --fix falls back to a developer name that
        doesn't cover every workspace subdir (2+ real workspaces → generic
        'developer'), the unmatched journals become unreachable from
        session/context. Previously this orphaning was silent; --fix must
        now surface one warning naming the dirs and how to switch."""
        dev_file = self.h.tmpdir / ".trellis-lite/.developer"
        dev_file.unlink()
        ws_root = self.h.tmpdir / ".trellis-lite/workspace"
        # tester/ exists from the Harness; add a second so there's no
        # single candidate and --fix falls back to 'developer'.
        (ws_root / "alice").mkdir(exist_ok=True)
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(dev_file.read_text().strip(), "name=developer")
        self.assertIn("unreachable", r.stdout)
        self.assertIn("alice", r.stdout)
        self.assertIn("tester", r.stdout)

    def test_doctor_fix_defaults_name_line_when_workspace_ambiguous(self) -> None:
        """P2-1 fallback: .developer half-written AND workspace/ has 2+
        subdirs → --fix writes the generic 'developer' default without
        crashing (no single identity to recover)."""
        dev_file = self.h.tmpdir / ".trellis-lite/.developer"
        dev_file.write_text("", encoding="utf-8")
        ws_root = self.h.tmpdir / ".trellis-lite/workspace"
        (ws_root / "alice").mkdir(exist_ok=True)  # tester/ already exists → 2 subdirs
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(dev_file.read_text().strip(), "name=developer")

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



    def test_doctor_fix_recovers_from_file_workspace(self) -> None:
        """F46: when workspace/<dev> is a regular file (stray touch), `doctor --fix`
        must unlink the file and recreate the directory instead of tracebacking.
        Previously `mkdir(exist_ok=True)` raised FileExistsError on Python 3.12+."""
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        shutil.rmtree(ws, ignore_errors=True)
        ws.write_text("not a directory\n", encoding="utf-8")
        self.assertTrue(ws.is_file())
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0, f"doctor --fix failed: {r.stdout}\n{r.stderr}")
        # workspace should now be a real directory
        self.assertTrue(ws.is_dir(), "workspace should be recreated as a directory")
        self.assertIn("created", r.stdout)
        # No traceback in output
        combined = r.stdout + r.stderr
        self.assertNotIn("Traceback", combined)

    def test_doctor_fix_recovers_from_file_subdir(self) -> None:
        """F46: same recovery pattern for required subdirs (tasks/, spec/, archive/)."""
        spec_dir = self.h.tmpdir / ".trellis-lite/spec"
        shutil.rmtree(spec_dir, ignore_errors=True)
        spec_dir.write_text("stray file\n", encoding="utf-8")
        self.assertTrue(spec_dir.is_file())
        r = self._run(["doctor", "--fix"])
        self.assertEqual(r.returncode, 0, f"doctor --fix failed: {r.stdout}\n{r.stderr}")
        self.assertTrue(spec_dir.is_dir(), "spec/ should be recreated as a directory")
        combined = r.stdout + r.stderr
        self.assertNotIn("Traceback", combined)
        self.assertNotIn("FileExistsError", combined)

    def test_doctor_detects_orphan_in_archive_subdir(self) -> None:
        """F54: doctor must flag orphan task dir under tasks/archive/<YYYY-MM>/.

        Previously only the active tasks/ tree was scanned — a deleted
        task.json inside the archive (e.g. `git rm` half-completed, stray
        `rm`) was invisible to doctor even though `task list --all`
        would still show it.
        """
        archive_task = self.h.tmpdir / ".trellis-lite/tasks/archive/2026-08/MM-DD-zombie"
        archive_task.mkdir(parents=True)
        self.assertTrue(archive_task.is_dir())
        r = self._run(["doctor"])
        self.assertEqual(r.returncode, 1, "doctor must flag orphan archived task as a problem")
        self.assertIn("orphan", r.stdout)
        # Scope prefix must indicate the archive/<month>/ location so the
        # user can locate the orphan without `find`.
        self.assertIn("archive/2026-08/", r.stdout)

    def test_doctor_detects_corrupted_task_json_in_archive_subdir(self) -> None:
        """F54: doctor must flag a present-but-unreadable task.json inside archive.

        Catches partial writes / manual edits / half-synced git checkouts
        where task.json exists but cannot be parsed by read_json_strict.
        Previously the existence check alone masked this — `task list
        --all` showed `[?]` with no doctor signal.
        """
        archive_task = self.h.tmpdir / ".trellis-lite/tasks/archive/2026-08/MM-DD-rotten"
        archive_task.mkdir(parents=True)
        (archive_task / "task.json").write_text("not json {", encoding="utf-8")
        r = self._run(["doctor"])
        self.assertEqual(r.returncode, 1,
                         f"corrupted archived task.json must flag, got:\n{r.stdout}")
        self.assertIn("corrupted", r.stdout)
        # The problem line must point at the actual archived task so the
        # user knows which one to inspect (vs the previous silent miss).
        self.assertIn("MM-DD-rotten", r.stdout)
        # The problem line must use the ✗ marker (problem severity), not
        # the ✓ marker (healthy check) — strip ANSI to find the marker.
        import re
        plain = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        problem_lines = [
            line for line in plain.splitlines()
            if "MM-DD-rotten" in line and line.lstrip().startswith(("✗", "⚠"))
        ]
        self.assertTrue(problem_lines,
                         f"expected at least one ✗ / ⚠ line pointing at the "
                         f"corrupted archive task, got:\n{r.stdout}")

    def test_doctor_warns_on_corrupted_active_task(self) -> None:
        """F55: when the active task (per .current-task) has corrupted task.json,
        doctor must surface a Warning / Problem, not a green ✓.

        `task start` / `task finish` / `task cancel` all refuse on
        corrupted metadata (F44/F47/F48/F52); doctor must agree so the
        user sees one consistent signal across commands.
        """
        self.h.run(["task", "create", "T", "--slug", "t"])
        # Locate the task dir that .current-task now points at.
        tasks_root = self.h.tmpdir / ".trellis-lite/tasks"
        bad = None
        for p in tasks_root.iterdir():
            if p.is_dir() and p.name != "archive" and (p / "task.json").exists():
                bad = p
                break
        assert bad is not None, "test setup: should have an active task"
        (bad / "task.json").write_text("garbage", encoding="utf-8")
        r = self._run(["doctor"])
        # doctor must report the active task as a problem (Warning red ✗ or yellow ⚠).
        # NOT a green ✓.
        combined = r.stdout + r.stderr
        self.assertEqual(r.returncode, 1,
                         f"corrupted active task.json must flag, got:\n{r.stdout}")
        self.assertIn("corrupted", combined)
        # The previously-misleading `✓ Active task:` line must be gone.
        self.assertNotIn("✓ Active task", combined,
                          "doctor must NOT report corrupted active task as green ✓")

    def test_doctor_does_not_silently_clear_corrupted_active_pointer(self) -> None:
        """F55: `doctor --fix` must NOT auto-clear a corrupted active task.

        The right path is explicit `task delete --force <name>` or manual
        task.json repair — both are user decisions. Auto-clearing would
        leave a state where the user thinks the task is gone but the
        directory is still in tasks/.
        """
        self.h.run(["task", "create", "T", "--slug", "t"])
        tasks_root = self.h.tmpdir / ".trellis-lite/tasks"
        bad = next(
            p for p in tasks_root.iterdir()
            if p.is_dir() and p.name != "archive"
        )
        (bad / "task.json").write_text("garbage", encoding="utf-8")
        ct_path = self.h.tmpdir / ".trellis-lite/.current-task"
        before = ct_path.read_text() if ct_path.exists() else ""
        r = self._run(["doctor", "--fix"])
        after = ct_path.read_text() if ct_path.exists() else ""
        # Pointer must be unchanged in --fix mode for corrupted-active path.
        self.assertEqual(before, after,
                          "doctor --fix must not auto-clear .current-task for corrupted active task")
        # Exit non-zero so the user has to act.
        self.assertNotEqual(r.returncode, 0,
                             "doctor must surface corrupted active task as a problem")


if __name__ == "__main__":
    unittest.main()