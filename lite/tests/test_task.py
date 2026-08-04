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
        self.assertIn("Warning", r.stdout)
        self.assertIn("a", r.stdout)

    def test_start_rejects_path_traversal(self) -> None:
        r = self.h.run(["task", "start", "../spec"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Invalid task name", r.stdout + r.stderr)

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