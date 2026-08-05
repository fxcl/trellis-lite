"""Tests for task create / start / finish / archive / cancel / list."""

from __future__ import annotations

import json
import unittest

from ._helpers import Harness, find_task, task_dirs


class TestTaskLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    # ---- create ----------------------------------------------------------

    def test_create_writes_files(self) -> None:
        r = self.h.run(["task", "create", "My task", "--slug", "my-task"])
        self.assertEqual(r.returncode, 0)
        d = find_task(self.h.tmpdir, "my-task")
        data = json.loads((d / "task.json").read_text())
        self.assertEqual(data["status"], "planning")
        self.assertEqual(data["title"], "My task")
        self.assertIn("Goal", (d / "prd.md").read_text())
        # .current-task should point to this task
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertTrue(ct.is_file())
        self.assertIn(d.name, ct.read_text())

    def test_create_auto_increments_on_collision(self) -> None:
        self.h.run(["task", "create", "S", "--slug", "dup"])
        self.h.run(["task", "finish"])
        self.h.run(["task", "create", "S", "--slug", "dup"])
        dup_names = [p.name for p in task_dirs(self.h.tmpdir) if "-dup" in p.name]
        self.assertEqual(len(dup_names), 2, f"expected 2 dup dirs, got {dup_names}")

    def test_create_cjk_slug_uses_hash(self) -> None:
        r = self.h.run(["task", "create", "中文任务"])
        self.assertEqual(r.returncode, 0)
        tasks = task_dirs(self.h.tmpdir)
        self.assertEqual(len(tasks), 1)
        # CJK -> "t-<6-hex>" per slugify
        self.assertRegex(tasks[0].name, r"-t-[0-9a-f]{6}$")

    def test_create_slug_sanitized(self) -> None:
        """Path traversal in --slug must be stripped by slugify()."""
        r = self.h.run(["task", "create", "X", "--slug", "../../evil"])
        self.assertEqual(r.returncode, 0)
        for t in task_dirs(self.h.tmpdir):
            self.assertNotIn("..", t.name)
            self.assertNotIn("/", t.name)

    def test_create_title_strips_paired_quotes(self) -> None:
        r = self.h.run(["task", "create", '"Quoted title"', "--slug", "qt"])
        self.assertEqual(r.returncode, 0)
        d = find_task(self.h.tmpdir, "qt")
        data = json.loads((d / "task.json").read_text())
        self.assertEqual(data["title"], "Quoted title")

    def test_create_warns_when_active_exists(self) -> None:
        self.h.run(["task", "create", "First", "--slug", "first"])
        r = self.h.run(["task", "create", "Second", "--slug", "second"])
        # Refuses (exit 1) by default to enforce "one task at a time".
        # Use --replace to explicitly take over.
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Refusing", r.stdout)
        self.assertIn("first", r.stdout)

    def test_create_replace_takeover_sets_new_current(self) -> None:
        self.h.run(["task", "create", "First", "--slug", "first"])
        r = self.h.run(["task", "create", "Second", "--slug", "second", "--replace"])
        self.assertEqual(r.returncode, 0)
        # Active pointer should now point to second, not first
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertIn("second", ct.read_text())
        self.assertNotIn("first", ct.read_text())

    # ---- start ------------------------------------------------------------

    def test_start_sets_in_progress(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        r = self.h.run(["task", "start", "t"])
        self.assertEqual(r.returncode, 0)
        d = find_task(self.h.tmpdir, "t")
        data = json.loads((d / "task.json").read_text())
        self.assertEqual(data["status"], "in_progress")
        self.assertIn("started", data)

    def test_start_warns_on_other_in_progress(self) -> None:
        self.h.run(["task", "create", "A", "--slug", "a"])
        self.h.run(["task", "start", "a"])
        # Take over via --replace to create B while A is still in_progress
        self.h.run(["task", "create", "B", "--slug", "b", "--replace"])
        r = self.h.run(["task", "start", "b"])
        # F20: single consolidated warning (not one line per task)
        self.assertEqual(r.stdout.count("Warning"), 1,
                         f"expected single consolidated warning, got:\n{r.stdout}")
        self.assertIn("1 other task", r.stdout)
        self.assertIn("a", r.stdout)

    def test_start_rejects_path_traversal(self) -> None:
        r = self.h.run(["task", "start", "../spec"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Invalid task name", r.stdout + r.stderr)

    def test_start_already_in_progress_is_idempotent(self) -> None:
        """Re-starting an in_progress task must not warn about corruption."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        r = self.h.run(["task", "start", "t"])
        # Exit 0 — this is a benign no-op, not an error.
        self.assertEqual(r.returncode, 0)
        # Must NOT claim the file is corrupted.
        self.assertNotIn("corrupted", r.stdout)
        self.assertNotIn("missing", r.stdout)
        # Should acknowledge the task is already active.
        self.assertIn("already in_progress", r.stdout)

    def test_start_rejects_done_terminal_state(self) -> None:
        """F27: starting a done task must explicitly reject (not silently succeed)."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])  # → done
        r = self.h.run(["task", "start", "t"])
        # Must reject (non-zero) — forward-only transitions.
        self.assertNotEqual(r.returncode, 0,
                            f"start on done task must reject, got:\n{r.stdout}")
        # Must mention the terminal state.
        self.assertIn("done", r.stdout)
        # Must NOT print the misleading "missing or corrupted" warning.
        self.assertNotIn("corrupted", r.stdout)
        # Must NOT print the misleading success line.
        self.assertNotIn("Task started", r.stdout)
        # CRITICAL: .current-task must NOT have been switched.
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertFalse(ct.exists(),
                         "failed start must not switch the active pointer")

    def test_start_rejects_cancelled_terminal_state(self) -> None:
        """F27: starting a cancelled task must reject (no forward re-entry)."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "cancel", "t"])  # → cancelled
        r = self.h.run(["task", "start", "t"])
        self.assertNotEqual(r.returncode, 0,
                            f"start on cancelled task must reject, got:\n{r.stdout}")
        self.assertIn("cancelled", r.stdout)
        self.assertNotIn("Task started", r.stdout)
        # Status must still be cancelled.
        d = find_task(self.h.tmpdir, "t")
        data = json.loads((d / "task.json").read_text())
        self.assertEqual(data["status"], "cancelled")

    # ---- finish -----------------------------------------------------------

    def test_finish_sets_done_and_clears_current(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        r = self.h.run(["task", "finish"])
        self.assertEqual(r.returncode, 0)
        d = find_task(self.h.tmpdir, "t")
        data = json.loads((d / "task.json").read_text())
        self.assertEqual(data["status"], "done")
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertFalse(ct.exists())

    def test_finish_no_active(self) -> None:
        # "no active task" when user asked to finish is a semantic error (return 1)
        r = self.h.run(["task", "finish"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("No active task", r.stdout)

    def test_finish_aborts_on_corrupted_task_json(self) -> None:
        """F1: corrupted task.json must abort cleanly without clearing the active pointer."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        # Corrupt the task.json by writing garbage
        d = find_task(self.h.tmpdir, "t")
        (d / "task.json").write_text("{not valid json", encoding="utf-8")
        r = self.h.run(["task", "finish"])
        # Must reject (non-zero) and explicitly mention the corruption
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("corrupted", r.stdout)
        # CRITICAL: active pointer must NOT have been cleared
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertTrue(ct.exists(), "finish on corrupted task.json must not clear active pointer")
        self.assertIn("t", ct.read_text())

    def test_finish_handles_missing_task_json(self) -> None:
        """F1 variant: missing task.json must also abort cleanly."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        d = find_task(self.h.tmpdir, "t")
        (d / "task.json").unlink()
        r = self.h.run(["task", "finish"])
        self.assertNotEqual(r.returncode, 0)
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertTrue(ct.exists(), "finish on missing task.json must not clear active pointer")

    # ---- archive ----------------------------------------------------------

    def test_archive_moves_to_archive_dir(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        r = self.h.run(["task", "archive", "t"])
        self.assertEqual(r.returncode, 0)
        archive_root = self.h.tmpdir / ".trellis-lite/tasks/archive"
        months = list(archive_root.iterdir())
        self.assertEqual(len(months), 1)
        self.assertRegex(months[0].name, r"^\d{4}-\d{2}$")
        archived = list(months[0].iterdir())
        self.assertEqual(len(archived), 1)
        self.assertTrue(archived[0].name.endswith("-t"))
        # Active tasks dir should be empty
        self.assertEqual(len(task_dirs(self.h.tmpdir)), 0)

    def test_archive_rejects_own_container(self) -> None:
        r = self.h.run(["task", "archive", "archive"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Invalid task name", r.stdout + r.stderr)

    def test_archive_auto_increments_on_collision(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        self.h.run(["task", "archive", "t"])
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        self.h.run(["task", "archive", "t"])
        # Should land as -t and -t-2 inside the same month dir
        months = list((self.h.tmpdir / ".trellis-lite/tasks/archive").iterdir())
        self.assertEqual(len(months), 1)
        archived = sorted(p.name for p in months[0].iterdir())
        self.assertEqual(len(archived), 2)

    # ---- cancel -----------------------------------------------------------

    def test_cancel_keeps_directory(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        r = self.h.run(["task", "cancel", "t"])
        self.assertEqual(r.returncode, 0)
        d = find_task(self.h.tmpdir, "t")
        data = json.loads((d / "task.json").read_text())
        self.assertEqual(data["status"], "cancelled")
        self.assertIn("cancelled", data)
        self.assertTrue(d.is_dir(), "cancel should not delete the directory")

    def test_cancel_clears_active_pointer(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "cancel", "t"])
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertFalse(ct.exists())

    # ---- list -------------------------------------------------------------

    def test_list_active_only_by_default(self) -> None:
        self.h.run(["task", "create", "Active", "--slug", "act"])
        self.h.run(["task", "create", "Archived", "--slug", "arc"])
        self.h.run(["task", "start", "arc"])
        self.h.run(["task", "finish"])
        self.h.run(["task", "archive", "arc"])
        r = self.h.run(["task", "list"])
        self.assertIn("act", r.stdout)
        self.assertNotIn("arc", r.stdout)

    def test_list_all_includes_archive(self) -> None:
        self.h.run(["task", "create", "Active", "--slug", "act"])
        self.h.run(["task", "create", "Archived", "--slug", "arc"])
        self.h.run(["task", "start", "arc"])
        self.h.run(["task", "finish"])
        self.h.run(["task", "archive", "arc"])
        r = self.h.run(["task", "list", "--all"])
        self.assertIn("act", r.stdout)
        self.assertIn("arc", r.stdout)

    def test_list_empty(self) -> None:
        r = self.h.run(["task", "list"])
        self.assertIn("No active tasks", r.stdout)

    # ---- delete -----------------------------------------------------------

    def _task_path(self, slug_suffix: str) -> Path | None:
        """Return path of task dir ending in -<slug_suffix>, or None if not found."""
        from ._helpers import task_dirs
        matches = [
            p for p in task_dirs(self.h.tmpdir)
            if p.name.endswith(f"-{slug_suffix}")
        ]
        if len(matches) == 0:
            return None
        self.assertEqual(len(matches), 1,
                         f"expected 1 task, got {len(matches)}: {[p.name for p in matches]}")
        return matches[0]

    def test_delete_removes_cancelled_task(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "cancel", "t"])
        r = self.h.run(["task", "delete", "t"])
        self.assertEqual(r.returncode, 0)
        self.assertIsNone(self._task_path("t"), "task dir should be gone after delete")

    def test_delete_refuses_non_cancelled_without_force(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        r = self.h.run(["task", "delete", "t"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Refusing to delete", r.stdout)
        self.assertIsNotNone(self._task_path("t"), "task dir must survive a refused delete")

    def test_delete_force_overrides_status(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        r = self.h.run(["task", "delete", "t", "--force"])
        self.assertEqual(r.returncode, 0)
        self.assertIsNone(self._task_path("t"), "task dir should be gone after --force delete")

    def test_delete_clears_active_pointer(self) -> None:
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "cancel", "t"])
        self.h.run(["task", "delete", "t"])
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertFalse(ct.exists())

    def test_delete_missing_task_returns_error(self) -> None:
        r = self.h.run(["task", "delete", "ghost"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", r.stdout)

    def test_archive_rejects_cancelled_terminal_state(self) -> None:
        """F32: archiving a cancelled task must explicitly reject (not split-brain)."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "cancel", "t"])
        r = self.h.run(["task", "archive", "t"])
        # Must reject (non-zero) — cancelled is terminal.
        self.assertNotEqual(r.returncode, 0,
                            f"archive on cancelled must reject, got:\n{r.stdout}")
        self.assertIn("Refusing to archive", r.stdout)
        self.assertIn("cancelled", r.stdout)
        # Must NOT print the misleading "Task archived" success line.
        self.assertNotIn("Task archived", r.stdout)
        # CRITICAL: directory must still be in tasks/, NOT moved to archive/.
        d = self._task_path("t")
        self.assertIsNotNone(d, "cancelled task dir must stay in tasks/")
        self.assertNotIn("archive", str(d),
                         "cancelled task must NOT be moved to archive/")
        # Status must still be cancelled (unchanged).
        data = json.loads((d / "task.json").read_text())
        self.assertEqual(data["status"], "cancelled")

    def test_archive_done_task_succeeds(self) -> None:
        """F32 control: archiving a done task is the happy path and must succeed."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        r = self.h.run(["task", "archive", "t"])
        self.assertEqual(r.returncode, 0,
                         f"archive on done must succeed, got:\n{r.stdout}")
        self.assertIn("Task archived", r.stdout)
        # Task dir must be in archive/ now.
        archive = self.h.tmpdir / ".trellis-lite/tasks/archive"
        self.assertTrue(archive.is_dir(),
                        "archive dir must exist after first archive")
        # find a month dir containing the task
        months = [p for p in archive.iterdir() if p.is_dir()]
        self.assertEqual(len(months), 1, f"expected 1 month, got {months}")
        self.assertTrue((months[0] / "08-05-t").is_dir(),
                        "task dir must be moved to archive/<month>/")

    def test_delete_refused_shows_tip_when_pointer_still_active(self) -> None:
        """F41: refused delete on the active task must hint about stale .current-task."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        r = self.h.run(["task", "delete", "t"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Refusing to delete", r.stdout)
        # The tip must appear since .current-task still points to 't'.
        self.assertIn("Tip", r.stdout)
        self.assertIn("task current", r.stdout)

    def test_delete_refused_no_tip_when_not_active(self) -> None:
        """F41: refused delete on a non-active task must NOT print the active-pointer tip."""
        self.h.run(["task", "create", "First", "--slug", "f"])
        self.h.run(["task", "finish"])  # 'f' is now done, not active
        self.h.run(["task", "create", "Second", "--slug", "s"])  # 's' is active
        r = self.h.run(["task", "delete", "f"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Refusing to delete", r.stdout)
        # Tip must NOT appear since .current-task points to 's', not 'f'.
        self.assertNotIn("Tip", r.stdout)

    def test_start_rejects_corrupted_task_json(self) -> None:
        """F48: starting a task with missing/corrupted task.json must refuse
        cleanly (exit 1, red error) instead of falling through to set_current_task
        + "✓ Task started". Previously left `.current-task` pointing at an
        unreadable task (split-brain)."""
        # Build two tasks so we can observe whether .current-task switches.
        # Task "good" is the active baseline; "bad" is the one we will corrupt.
        self.h.run(["task", "create", "Good", "--slug", "good"])
        self.h.run(["task", "start", "good"])
        # Finish releases the active pointer so we can create another task.
        self.h.run(["task", "finish"])
        self.h.run(["task", "create", "Bad", "--slug", "bad"])
        from ._helpers import find_task
        bad = find_task(self.h.tmpdir, "bad")
        (bad / "task.json").write_text("garbage not json", encoding="utf-8")
        # .current-task now points at "bad" (set by task create).
        # We want to verify that after a refused start, .current-task has NOT
        # been moved to a different state and that no "Task started" line
        # was emitted. (Pre-F48 the corrupted task.json would have been
        # accepted with a Warning and "Task started" line.)
        ct_path = self.h.tmpdir / ".trellis-lite/.current-task"
        before = ct_path.read_text() if ct_path.exists() else ""
        r = self.h.run(["task", "start", "bad"])
        self.assertNotEqual(r.returncode, 0, "corrupted task.json must refuse start")
        self.assertIn("missing or corrupted", r.stdout)
        self.assertIn("refusing to start", r.stdout)
        self.assertNotIn("Task started", r.stdout)
        # Pointer must not have been cleared by a refused start
        after = ct_path.read_text() if ct_path.exists() else ""
        self.assertEqual(before, after, ".current-task pointer must be unchanged after refused start")

    def test_archive_rejects_corrupted_task_json(self) -> None:
        """F47: archiving a task with corrupted task.json must refuse (exit 1)
        instead of moving the directory to archive/ and leaving an unreadable
        task.json there (orphan)."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        task_dir = self.h.tmpdir / ".trellis-lite/tasks"
        d = None
        for x in task_dir.iterdir():
            if x.is_dir() and x.name != "archive":
                d = x
                break
        assert d is not None
        (d / "task.json").write_text("garbage", encoding="utf-8")
        r = self.h.run(["task", "archive", "t"])
        self.assertNotEqual(r.returncode, 0, "corrupted task.json must refuse archive")
        self.assertIn("missing or corrupted", r.stdout)
        self.assertIn("Refusing to archive", r.stdout)
        self.assertNotIn("Task archived", r.stdout)
        # Directory must still be under tasks/ (not moved to archive/)
        self.assertTrue(d.is_dir(), "task dir must not have moved")
        archive_dir = task_dir / "archive"
        self.assertFalse(
            any(archive_dir.rglob(d.name)),
            "no copy should have been moved to archive/",
        )

    def test_cancel_rejects_archived_terminal_state(self) -> None:
        """F52: cancelling an already-archived task must refuse explicitly.
        Previously: warning "missing or corrupted" (misleading) + clear pointer
        + "✓ Task cancelled" while task.json stayed archived (split-brain)."""
        task_dir = self.h.tmpdir / ".trellis-lite/tasks/MM-DD-archived"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            '''{"title": "a", "slug": "a", "status": "archived", "created": "2026-08-05T00:00:00"}
''',
            encoding="utf-8",
        )
        r = self.h.run(["task", "cancel", "MM-DD-archived"])
        self.assertNotEqual(r.returncode, 0, "cancel on archived must refuse")
        self.assertIn("Refusing to cancel", r.stdout)
        self.assertIn("archived", r.stdout.lower())
        self.assertIn("terminal state", r.stdout)
        self.assertNotIn("Task cancelled", r.stdout)
        import json as _json
        status = _json.loads((task_dir / "task.json").read_text())["status"]
        self.assertEqual(status, "archived", "status must not have changed")

    def test_cancel_rejects_corrupted_task_json(self) -> None:
        """F52: cancelling a task with corrupted task.json must refuse cleanly."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        task_dir = self.h.tmpdir / ".trellis-lite/tasks"
        d = None
        for x in task_dir.iterdir():
            if x.is_dir() and x.name != "archive":
                d = x
                break
        assert d is not None
        (d / "task.json").write_text("garbage", encoding="utf-8")
        r = self.h.run(["task", "cancel", "t"])
        self.assertNotEqual(r.returncode, 0, "corrupted task.json must refuse cancel")
        self.assertIn("missing or corrupted", r.stdout)
        self.assertIn("Refusing to cancel", r.stdout)
        self.assertNotIn("Task cancelled", r.stdout)


