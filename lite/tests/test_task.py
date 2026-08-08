"""Tests for task create / start / finish / archive / cancel / list."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from ._helpers import Harness, find_task, task_dirs

# In-process load of trellis.py for tests that need to monkeypatch internals
# (e.g. intercepting shutil.move to assert the atomic-rename precondition).
# Mirrors the pattern in test_status_machine.py.
_SCRIPT = Path(__file__).resolve().parent.parent / ".trellis-lite/scripts/trellis.py"
_spec = importlib.util.spec_from_file_location("trellis_script", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


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

    def test_create_replace_closes_old_in_progress(self) -> None:
        """--replace must close the old active task so `task list` doesn't
        show two in_progress tasks — the "one task at a time" invariant that
        _task_start itself warns about. Previously --replace only repointed
        .current-task, leaving the old task stranded in in_progress."""
        self.h.run(["task", "create", "First", "--slug", "first"])
        self.h.run(["task", "start", "first"])  # first → in_progress
        self.h.run(["task", "create", "Second", "--slug", "second", "--replace"])
        first_dir = find_task(self.h.tmpdir, "first")
        first_data = json.loads((first_dir / "task.json").read_text())
        self.assertEqual(first_data["status"], "done",
                         f"--replace must close old task to done, got "
                         f"{first_data['status']}")
        self.assertIn("finished", first_data,
                      "closed old task must get a finished timestamp")
        # Second is the new active, in planning (not auto-started).
        second_dir = find_task(self.h.tmpdir, "second")
        second_data = json.loads((second_dir / "task.json").read_text())
        self.assertEqual(second_data["status"], "planning")

    def test_create_replace_closes_old_planning(self) -> None:
        """--replace on a planning old task (created but never started) must
        also close it to done — planning→done is a legal forward transition."""
        self.h.run(["task", "create", "First", "--slug", "first"])  # planning
        self.h.run(["task", "create", "Second", "--slug", "second", "--replace"])
        first_dir = find_task(self.h.tmpdir, "first")
        first_data = json.loads((first_dir / "task.json").read_text())
        self.assertEqual(first_data["status"], "done",
                         f"planning old task must close to done, got "
                         f"{first_data['status']}")

    def test_create_replace_tolerates_missing_old_task_dir(self) -> None:
        """P3-5a (round 9): --replace with a stale .current-task pointer
        (old dir deleted out from under it) must still succeed — the close
        step is guarded by old_dir.is_dir() and skipped, no partial state."""
        self.h.run(["task", "create", "First", "--slug", "first"])
        for d in task_dirs(self.h.tmpdir):
            if "first" in d.name:
                shutil.rmtree(d)
        r = self.h.run(["task", "create", "Second", "--slug", "second", "--replace"])
        self.assertEqual(r.returncode, 0,
                         f"--replace must tolerate a missing old task dir:\n{r.stdout}")
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertIn("second", ct.read_text())

    def test_create_replace_leaves_terminal_old_task_untouched(self) -> None:
        """P3-5a: --replace onto a cancelled old task — set_status(done) is
        rejected by the forward-only machine and intentionally ignored, so
        the terminal task stays untouched while create still succeeds."""
        self.h.run(["task", "create", "First", "--slug", "first"])
        self.h.run(["task", "cancel", "first"])  # cancel clears the pointer
        first_dir = find_task(self.h.tmpdir, "first")
        # Restore a stale pointer onto the cancelled task to exercise the
        # takeover path (only reachable via hand-edited .current-task).
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        ct.write_text(f".trellis-lite/tasks/{first_dir.name}\n", encoding="utf-8")
        r = self.h.run(["task", "create", "Second", "--slug", "second", "--replace"])
        self.assertEqual(r.returncode, 0,
                         f"--replace must succeed on a terminal old task:\n{r.stdout}")
        first_data = json.loads((first_dir / "task.json").read_text())
        self.assertEqual(first_data["status"], "cancelled",
                         "terminal old task must stay untouched by --replace")

    def test_create_replace_tolerates_corrupted_old_task(self) -> None:
        """P3-5a: --replace when the old task's task.json is corrupted —
        set_status returns False (strict read) and is intentionally ignored;
        create succeeds and the corrupted file is left intact for doctor."""
        self.h.run(["task", "create", "First", "--slug", "first"])
        first_dir = find_task(self.h.tmpdir, "first")
        (first_dir / "task.json").write_text("garbage", encoding="utf-8")
        r = self.h.run(["task", "create", "Second", "--slug", "second", "--replace"])
        self.assertEqual(r.returncode, 0,
                         f"--replace must not crash on corrupted old task:\n{r.stdout}")
        self.assertEqual((first_dir / "task.json").read_text(), "garbage",
                         "corrupted old task.json must be left intact")
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertIn("second", ct.read_text())

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
        # F20: _task_start emits a single consolidated warning when another
        # task is still in_progress. Set this up by manually writing A's
        # task.json to in_progress (a legacy/concurrent task that was started
        # but never closed), clearing the active pointer, creating B, then
        # starting B. We can't use --replace to leave A in_progress anymore
        # because --replace now closes the old task — that invariant is
        # covered by test_create_replace_closes_old_in_progress below.
        import json as _json
        self.h.run(["task", "create", "A", "--slug", "a"])
        a_dir = find_task(self.h.tmpdir, "a")
        (a_dir / "task.json").write_text(_json.dumps({
            "title": "A", "slug": "a", "status": "in_progress",
            "created": "2026-01-01T00:00:00", "branch": "main",
            "started": "2026-01-01T00:00:00",
        }), encoding="utf-8")
        # Clear the active pointer so B can be created without --replace.
        (self.h.tmpdir / ".trellis-lite/.current-task").unlink()
        self.h.run(["task", "create", "B", "--slug", "b"])
        r = self.h.run(["task", "start", "b"])
        # Single consolidated warning (not one line per task).
        self.assertEqual(r.stdout.count("Warning"), 1,
                         f"expected single consolidated warning, got:\n{r.stdout}")
        self.assertIn("1 other task", r.stdout)
        self.assertIn("a", r.stdout)

    def test_start_rejects_path_traversal(self) -> None:
        r = self.h.run(["task", "start", "../spec"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Invalid task name", r.stdout + r.stderr)

    def test_start_reports_missing_tasks_dir_friendly(self) -> None:
        """P3-1 (round 19): when tasks/ itself is missing, `task start` must
        print a friendly, actionable message (pointing at doctor --fix) rather
        than the raw FileNotFoundError("[Errno 2] ...") errno text."""
        shutil.rmtree(self.h.tmpdir / ".trellis-lite/tasks")
        r = self.h.run(["task", "start", "anything"])
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        # Friendly message, not raw errno text.
        self.assertIn("tasks/ missing", out)
        self.assertIn("doctor --fix", out)
        self.assertNotIn("[Errno 2]", out)

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

    def test_finish_reports_terminal_state_not_corrupted(self) -> None:
        """P3-4 (round 9): finishing a task whose recorded status is already
        terminal (only reachable via hand-edited .current-task) must report
        the real cause — previously every set_status False was reported as
        'missing or corrupted', sending users to doctor --fix for a problem
        doctor cannot fix."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "cancel", "t"])  # cancel clears the pointer
        d = find_task(self.h.tmpdir, "t")
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        ct.write_text(f".trellis-lite/tasks/{d.name}\n", encoding="utf-8")
        r = self.h.run(["task", "finish"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("terminal state 'cancelled'", r.stdout)
        self.assertNotIn("corrupted", r.stdout,
                         "terminal-state refusal must not misreport as corrupted")
        self.assertTrue(ct.exists(), "refusal must not clear the active pointer")

    def test_finish_reports_archived_terminal_state(self) -> None:
        """P3-H (round 10): the archived branch of the finish terminal-state
        guard. A genuinely archived task's dir lives under archive/, so this
        state needs a hand-crafted status=archived task.json under tasks/ —
        exactly the hand-edited-pointer scenario P3-4 targets."""
        tasks_dir = self.h.tmpdir / ".trellis-lite/tasks"
        fake = tasks_dir / "01-01-ghost"
        fake.mkdir()
        (fake / "task.json").write_text(
            '{"title": "G", "slug": "ghost", "status": "archived"}',
            encoding="utf-8",
        )
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        ct.write_text(f".trellis-lite/tasks/{fake.name}\n", encoding="utf-8")
        r = self.h.run(["task", "finish"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("terminal state 'archived'", r.stdout)
        self.assertTrue(ct.exists(), "refusal must not clear the active pointer")

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

    def test_archive_recovers_from_file_archive_dir(self) -> None:
        """P3-3 (round 11): when `.trellis-lite/tasks/archive` is a stray
        file (touch, partial sync, mid-init crash), `task archive` used to
        raise FileExistsError on Python 3.12+ and surface a raw traceback.
        Now _safe_mkdir transparently removes the file and replaces it with
        the directory, mirroring the doctor --fix path."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        # Replace the archive dir with a regular file of the same name.
        archive = self.h.tmpdir / ".trellis-lite/tasks/archive"
        shutil.rmtree(archive)
        archive.write_text("not a directory\n", encoding="utf-8")
        r = self.h.run(["task", "archive", "t"])
        self.assertEqual(r.returncode, 0,
                         f"archive must recover from stray file at archive/:\n"
                         f"{r.stdout}\n{r.stderr}")
        # Archive must now be a directory with the task under <month>/.
        self.assertTrue(archive.is_dir(), "archive file must be replaced by a directory")
        months = list(archive.iterdir())
        self.assertEqual(len(months), 1)

    def test_archive_precreates_month_dir_for_atomic_move(self) -> None:
        """P3-1 (round 13): `_task_archive` must mkdir dest.parent (the month
        subdir) BEFORE calling shutil.move, so shutil.move always takes the
        atomic os.rename path instead of falling back to copytree + rmtree
        (which leaves a narrow window where the task exists in both tasks/
        and archive/ if the process is killed mid-copy).

        We probe this in-process by swapping trellis.shutil for a recorder
        that captures whether dest.parent existed at the moment move() was
        called. If a future change reverts to mkdir-ing only archive_dir,
        the month dir won't exist at call time and this assertion fails."""
        # Subprocess setup: create + finish a task (keeps setup realistic).
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        slug = find_task(self.h.tmpdir, "t").name

        # In-process probe: chdir to the project so get_repo_root resolves,
        # then swap trellis.shutil for a recorder.
        orig_cwd = Path.cwd()
        orig_shutil = _mod.shutil

        class _Recorder:
            def __init__(self, real):
                self._real = real
                self.dest_parent_existed = None

            def move(self, src, dest):
                self.dest_parent_existed = Path(dest).parent.is_dir()
                return self._real.move(str(src), str(dest))

            def __getattr__(self, name):
                return getattr(self._real, name)

        recorder = _Recorder(orig_shutil)
        try:
            os.chdir(self.h.tmpdir)
            _mod.shutil = recorder  # type: ignore[attr-defined]
            rc = _mod._task_archive([slug])
        finally:
            _mod.shutil = orig_shutil  # type: ignore[attr-defined]
            os.chdir(orig_cwd)

        self.assertEqual(rc, 0, "_task_archive should succeed")
        self.assertIsNotNone(
            recorder.dest_parent_existed,
            "shutil.move was never called — test setup is wrong",
        )
        self.assertTrue(
            recorder.dest_parent_existed,
            "P3-1 regression: dest.parent (month dir) did not exist when "
            "shutil.move was called, so the move fell back to the non-atomic "
            "copytree + rmtree path.",
        )

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

    def test_current_warns_on_corrupted_active_task(self) -> None:
        """`task current` must warn when the active task.json is corrupted,
        not silently omit Title/Status — the AI calls this to orient and a
        silent drop hides the same state doctor flags (F55). Exit 0: it's a
        read."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        d = find_task(self.h.tmpdir, "t")
        (d / "task.json").write_text("garbage", encoding="utf-8")
        r = self.h.run(["task", "current"])
        self.assertEqual(r.returncode, 0, "task current is a read — must stay exit 0")
        self.assertIn("corrupted", r.stdout)
        self.assertIn("doctor", r.stdout)
        # Must NOT print the silent `Title: ?` fallback that hides corruption.
        self.assertNotIn("Title:  ?", r.stdout)

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

    def test_cancel_idempotent_clears_stale_pointer(self) -> None:
        """P3-A (round 10): the idempotent cancel branch must clear
        .current-task when it still points at the already-cancelled task —
        previously it early-returned before the pointer-cleanup code,
        trapping users with a pointer whose only exit was hand-editing."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "cancel", "t"])  # normal path clears the pointer
        d = find_task(self.h.tmpdir, "t")
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        ct.write_text(f".trellis-lite/tasks/{d.name}\n", encoding="utf-8")
        r = self.h.run(["task", "cancel", "t"])  # idempotent branch
        self.assertEqual(r.returncode, 0)
        self.assertIn("already cancelled", r.stdout)
        self.assertFalse(ct.exists(),
                         "idempotent cancel must clear a pointer onto the same task")

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
        # P3-5b (round 9): the created task is the active one — force-delete
        # must also clear .current-task (code path at _task_delete, asserted
        # here so a future refactor can't silently drop the cleanup).
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertFalse(ct.exists(),
                         "force-delete of the active task must clear .current-task")

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
        # Use today's date prefix (trellis.py generates `MM-DD-<slug>` names
        # via `date_prefix()` = `datetime.now().strftime("%m-%d")`). Hardcoding
        # "08-05" made this test a time bomb — it only ran green on the day it
        # was written. Make the assertion robust across midnight rollover too.
        from datetime import datetime
        today_prefix = datetime.now().strftime("%m-%d")
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
        self.assertTrue((months[0] / f"{today_prefix}-t").is_dir(),
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

    def test_delete_force_succeeds_on_corrupted_task_json(self) -> None:
        """F63: --force must bypass the corrupted-metadata guard.

        The non-force refusal message recommends `task delete --force` as the
        recovery path. If --force also refused on corrupted metadata, the user
        following that hint would hit the same wall: task cancel refuses on
        corrupted (F52), task delete refuses on corrupted (F53), and
        task delete --force would refuse too — closing the only exit.
        """
        self.h.run(["task", "create", "T", "--slug", "t"])
        d = self._task_path("t")
        assert d is not None
        (d / "task.json").write_text("garbage", encoding="utf-8")
        r = self.h.run(["task", "delete", "t", "--force"])
        # --force is the explicit recovery path → must succeed.
        self.assertEqual(r.returncode, 0,
                         f"--force must delete corrupted task, got:\n{r.stdout}")
        self.assertIn("Task deleted", r.stdout)
        self.assertIsNone(self._task_path("t"),
                          "corrupted task dir must be gone after --force delete")
        # P3-5b: same pointer-cleanup assertion on the corrupted path.
        ct = self.h.tmpdir / ".trellis-lite/.current-task"
        self.assertFalse(ct.exists(),
                         "--force delete of corrupted active task must clear .current-task")

    def test_delete_rejects_corrupted_task_json(self) -> None:
        """F53: deleting a task with corrupted task.json must refuse cleanly.

        Previously `_task_delete` used `read_json` (lossy), so corrupted
        input returned `{}` and fell through to `data.get("status", "?")`
        — printing the misleading "Refusing to delete with status '?'. Cancel
        it first (task cancel X)" hint. But task cancel itself refuses on
        corrupted (F52), so the user was sent in a recovery loop. The fix
        uses `read_json_strict` and prints an explicit "missing or corrupted"
        message pointing to `doctor --fix` or `--force`.
        """
        self.h.run(["task", "create", "T", "--slug", "t"])
        task_dir = self.h.tmpdir / ".trellis-lite/tasks"
        d = None
        for x in task_dir.iterdir():
            if x.is_dir() and x.name != "archive":
                d = x
                break
        assert d is not None
        (d / "task.json").write_text("garbage", encoding="utf-8")
        r = self.h.run(["task", "delete", "t"])
        # Must refuse (non-zero exit) on corrupted metadata.
        self.assertNotEqual(r.returncode, 0, "corrupted task.json must refuse delete")
        self.assertIn("missing or corrupted", r.stdout)
        self.assertIn("Refusing to delete", r.stdout)
        # Must NOT suggest the (now-broken) "Cancel it first" hint that would
        # trap the user — cancel itself refuses on corrupted (F52).
        self.assertNotIn("Cancel it first", r.stdout)
        # Must NOT silently go through with the delete.
        self.assertNotIn("Task deleted", r.stdout)
        # Directory must still exist (we refused BEFORE shutil.rmtree ran).
        self.assertIsNotNone(self._task_path("t"),
                             "task dir must survive refused delete on corrupted task.json")


class TestWrapPhaseWarnings(unittest.TestCase):
    """Batch 1: WRAP-phase completeness warnings (non-blocking)."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    # ---- _task_finish: prd.md unchecked criteria ----

    def test_finish_warns_on_unchecked_criteria(self) -> None:
        """task finish must warn (not block) when prd.md has '- [ ]' items."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        # Overwrite prd.md with unchecked criteria
        d = find_task(self.h.tmpdir, "t")
        (d / "prd.md").write_text(
            "# T\n\n## Acceptance Criteria\n- [ ] one\n- [ ] two\n",
            encoding="utf-8",
        )
        r = self.h.run(["task", "finish"])
        self.assertEqual(r.returncode, 0, "finish must still succeed (warning only)")
        self.assertIn("unchecked", r.stdout)
        self.assertIn("acceptance", r.stdout)
        self.assertIn("2", r.stdout)  # count appears in the warning

    def test_finish_silent_when_all_checked(self) -> None:
        """No warning when all criteria are checked '- [x]'."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        d = find_task(self.h.tmpdir, "t")
        (d / "prd.md").write_text(
            "# T\n\n## Acceptance Criteria\n- [x] done\n- [x] also done\n",
            encoding="utf-8",
        )
        r = self.h.run(["task", "finish"])
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("unchecked", r.stdout)

    def test_finish_silent_when_prd_missing(self) -> None:
        """No warning when prd.md is absent (nothing to check)."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        d = find_task(self.h.tmpdir, "t")
        (d / "prd.md").unlink()
        r = self.h.run(["task", "finish"])
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("unchecked", r.stdout)

    # ---- _task_archive: WRAP completeness ----

    def test_archive_warns_when_no_session(self) -> None:
        """task archive must warn when journal has no session entry."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        r = self.h.run(["task", "archive", "t"])
        self.assertEqual(r.returncode, 0, "archive must still succeed")
        self.assertIn("no session recorded", r.stdout)

    def test_archive_silent_after_session(self) -> None:
        """No 'no session' warning once a session entry exists."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        self.h.run(["session", "--title", "Done", "--summary", "Shipped"])
        r = self.h.run(["task", "archive", "t"])
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("no session recorded", r.stdout)

    def test_archive_warns_on_uncommitted_spec(self) -> None:
        """task archive must warn when spec/ has uncommitted changes."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        self.h.run(["task", "finish"])
        self.h.run(["session", "--title", "Done", "--summary", "Shipped"])
        # git_status_porcelain only reports changes in a git repo — init one
        subprocess.run(["git", "init"], cwd=self.h.tmpdir, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=self.h.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"],
            cwd=self.h.tmpdir, capture_output=True,
        )
        # Dirty the spec dir (uncommitted change)
        spec_dir = self.h.tmpdir / ".trellis-lite/spec"
        (spec_dir / "new-rule.md").write_text("# Rule\n", encoding="utf-8")
        r = self.h.run(["task", "archive", "t"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("spec/ has uncommitted changes", r.stdout)

    # ---- _task_list: health marker column ----

    def test_list_shows_health_marker_for_done_task(self) -> None:
        """task list must show ⚠ health marker for a WRAP-incomplete done task."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        d = find_task(self.h.tmpdir, "t")
        (d / "prd.md").write_text("# T\n\n- [ ] unchecked\n", encoding="utf-8")
        self.h.run(["task", "finish"])
        r = self.h.run(["task", "list"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("⚠", r.stdout)
        self.assertIn("unchecked", r.stdout)

    def test_list_health_ok_for_wrapped_done_task(self) -> None:
        """task list shows ✓ when a done task is fully wrapped."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        d = find_task(self.h.tmpdir, "t")
        (d / "prd.md").write_text("# T\n\n- [x] done\n", encoding="utf-8")
        self.h.run(["task", "finish"])
        self.h.run(["session", "--title", "S", "--summary", "ok"])
        r = self.h.run(["task", "list"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("✓", r.stdout)
        self.assertNotIn("⚠", r.stdout)

    # ---- _task_list --all: archived tasks keep an honest health marker ----

    def test_list_all_shows_health_marker_for_archived_incomplete_task(self) -> None:
        """task list --all must show ⚠ for a task archived with an incomplete
        WRAP phase — archiving is irreversible, but the signal stays honest
        instead of being masked by a hardcoded green check."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        d = find_task(self.h.tmpdir, "t")
        (d / "prd.md").write_text("# T\n\n- [ ] unchecked\n", encoding="utf-8")
        self.h.run(["task", "finish"])
        self.h.run(["task", "archive", "t"])
        r = self.h.run(["task", "list", "--all"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("[archived]", r.stdout)
        self.assertIn("⚠", r.stdout)
        self.assertIn("unchecked", r.stdout)

    def test_list_all_health_ok_for_fully_wrapped_archived_task(self) -> None:
        """task list --all shows ✓ for an archived task whose WRAP completed."""
        self.h.run(["task", "create", "T", "--slug", "t"])
        self.h.run(["task", "start", "t"])
        d = find_task(self.h.tmpdir, "t")
        (d / "prd.md").write_text("# T\n\n- [x] done\n", encoding="utf-8")
        self.h.run(["task", "finish"])
        self.h.run(["session", "--title", "S", "--summary", "ok"])
        self.h.run(["task", "archive", "t"])
        r = self.h.run(["task", "list", "--all"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("[archived]", r.stdout)
        self.assertIn("✓", r.stdout)
        self.assertNotIn("⚠", r.stdout)


class TestTaskTemplate(unittest.TestCase):
    """Batch 4 / improvement 8: task create --template bug|feature|refactor."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    def test_create_with_bug_template(self) -> None:
        r = self.h.run(["task", "create", "Fix crash", "--slug", "fix", "--template", "bug"])
        self.assertEqual(r.returncode, 0, f"bug template create failed:\n{r.stdout}\n{r.stderr}")
        d = find_task(self.h.tmpdir, "fix")
        prd = (d / "prd.md").read_text(encoding="utf-8")
        self.assertIn("## Reproduction", prd)
        self.assertIn("Root Cause Hypothesis", prd)
        self.assertIn("# Fix crash", prd)

    def test_create_with_feature_template(self) -> None:
        r = self.h.run(["task", "create", "Add export", "--template", "feature"])
        self.assertEqual(r.returncode, 0)
        d = find_task(self.h.tmpdir, "add-export")
        self.assertIn("## Requirements", (d / "prd.md").read_text(encoding="utf-8"))

    def test_create_with_refactor_template(self) -> None:
        r = self.h.run(["task", "create", "Cleanup", "--template", "refactor"])
        self.assertEqual(r.returncode, 0)
        d = find_task(self.h.tmpdir, "cleanup")
        self.assertIn("No behavior change", (d / "prd.md").read_text(encoding="utf-8"))

    def test_create_rejects_unknown_template(self) -> None:
        r = self.h.run(["task", "create", "X", "--template", "nope"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown template", r.stdout + r.stderr)
        # No task dir should be created on rejection (archive/ is pre-created
        # by init, so only assert no *task* directories appeared).
        tasks_dir = self.h.tmpdir / ".trellis-lite/tasks"
        leftovers = [p for p in tasks_dir.iterdir() if p.is_dir() and p.name != "archive"]
        self.assertEqual(leftovers, [])

    def test_create_without_template_uses_default_skeleton(self) -> None:
        r = self.h.run(["task", "create", "Plain", "--slug", "plain"])
        self.assertEqual(r.returncode, 0)
        d = find_task(self.h.tmpdir, "plain")
        prd = (d / "prd.md").read_text(encoding="utf-8")
        self.assertIn("One-sentence description", prd)
        self.assertNotIn("Reproduction", prd)


