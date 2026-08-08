"""Tests for the session command and journal rotation."""

from __future__ import annotations

import re
import shutil
import unittest

from ._helpers import Harness


class TestSession(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    def test_session_appends_to_journal(self) -> None:
        r = self.h.run(["session", "--title", "Test session", "--summary", "Did stuff"])
        self.assertEqual(r.returncode, 0)
        j = self.h.tmpdir / ".trellis-lite/workspace/tester/journal-1.md"
        content = j.read_text()
        self.assertIn("Test session", content)
        self.assertIn("Did stuff", content)

    def test_session_with_valid_commit(self) -> None:
        r = self.h.run(["session", "--title", "T", "--commit", "abc1234"])
        self.assertEqual(r.returncode, 0)
        j = self.h.tmpdir / ".trellis-lite/workspace/tester/journal-1.md"
        self.assertIn("abc1234", j.read_text())

    def test_session_rejects_bad_commit(self) -> None:
        """Bad commit format → exit 1, no journal entry written."""
        r = self.h.run(["session", "--title", "T", "--commit", "BAD!"])
        self.assertNotEqual(r.returncode, 0, f"should exit non-zero on bad commit\n{r.stdout}")
        self.assertIn("Error", r.stdout)
        self.assertIn("git SHA", r.stdout)
        # Bad commit should NOT appear in journal (session must not be recorded)
        j = self.h.tmpdir / ".trellis-lite/workspace/tester/journal-1.md"
        if j.exists():
            self.assertNotIn("BAD!", j.read_text())
            self.assertNotIn("T\n", j.read_text())

    def test_session_accepts_various_valid_shas(self) -> None:
        """4-char short SHA through 64-char SHA-256 are all valid (covers
        git 2.42+ repositories that use SHA-256 by default)."""
        for sha in ("abcd", "abcdef12", "abcdef1234567890", "a" * 40, "a" * 64):
            with self.subTest(sha=sha):
                r = self.h.run(["session", "--title", f"sha-{sha[:6]}", "--commit", sha])
                self.assertEqual(r.returncode, 0, f"{sha} should be accepted\n{r.stdout}")

    def test_session_requires_developer(self) -> None:
        # Wipe the developer identity
        (self.h.tmpdir / ".trellis-lite/.developer").unlink()
        r = self.h.run(["session", "--title", "T"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Developer not initialized", r.stdout + r.stderr)

    def test_journal_rotation_skips_after_manual_deletion(self) -> None:
        """If journal-2 was deleted, journal-3 must not be overwritten on rotation."""
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        # Create journal-2 and journal-3 first; then delete journal-2 to create a gap
        (ws / "journal-2.md").write_text("# Journal 2\n")
        (ws / "journal-3.md").write_text("# Journal 3\n\n" + "precious history\n" * 2100)
        (ws / "journal-2.md").unlink()
        # Trigger a session — should rotate to journal-4 (max + 1), not overwrite journal-3
        r = self.h.run(["session", "--title", "rotation test"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("journal-4.md", r.stdout)
        self.assertTrue((ws / "journal-4.md").is_file())
        # journal-3 content must be intact
        self.assertEqual(
            (ws / "journal-3.md").read_text().count("precious history"), 2100
        )

    def test_session_total_ignores_non_numbered_journal_files(self) -> None:
        """F15: cmd_session must use list_journals (which filters by journal-N.md),
        so files like journal-draft.md with session-like headers do NOT inflate
        the reported total session count."""
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        # Drop a non-numbered file that mimics a session entry
        (ws / "journal-draft.md").write_text(
            "# Draft\n\n## Fake session 1\n\nstuff\n\n## Fake session 2\n\nstuff\n"
        )
        # Record one real session
        r = self.h.run(["session", "--title", "Real", "--summary", "S"])
        self.assertEqual(r.returncode, 0)
        # Total should be 1 (real), not 3 (real + 2 fake)
        m = re.search(r"Total sessions: (\d+)", r.stdout)
        self.assertIsNotNone(m, f"no total line in:\n{r.stdout}")
        self.assertEqual(m.group(1), "1", f"F15 regression: non-numbered journal counted\n{r.stdout}")

    def test_session_corrupt_developer_file_gives_specific_error(self) -> None:
        """F45: .developer exists but has no 'name=' line must produce a distinct
        error message that points at 'doctor --fix', NOT 'trellis.py init <name>'
        (which would mislead the user into overwriting a still-recoverable file).
        """
        dev_file = self.h.tmpdir / ".trellis-lite/.developer"
        dev_file.write_text("garbage no name line\n", encoding="utf-8")
        r = self.h.run(["session", "--title", "T"])
        self.assertNotEqual(r.returncode, 0)
        # Must mention doctor --fix AND must NOT tell the user to 'init <name>'.
        self.assertIn("doctor", r.stdout.lower(),
                      f"corrupt .developer must hint doctor --fix, got:\n{r.stdout}")
        self.assertNotIn("Developer not initialized", r.stdout,
                         "must not conflate corrupted file with uninitialized state")

    def test_session_workspace_is_a_file_does_not_traceback(self) -> None:
        """F44: when workspace/<dev>/ exists but is a regular file (stray touch,
        partial git sync, mid-init crash), `session` must NOT show a raw Python
        traceback. It must print a clean red error and return non-zero.
        """
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        # Replace the workspace dir with a regular file of the same name.
        import shutil
        shutil.rmtree(ws)
        ws.write_text("not a directory\n", encoding="utf-8")
        r = self.h.run(["session", "--title", "T"])
        self.assertNotEqual(r.returncode, 0)
        # No Python traceback (which would include 'File " or 'Traceback').
        combined = r.stdout + r.stderr
        self.assertNotIn("Traceback", combined,
                         f"F44 regression: raw traceback surfaced:\n{combined}")
        self.assertNotIn('File "', combined,
                         f"F44 regression: stack frames surfaced:\n{combined}")
        # Must mention doctor --fix (the actionable repair path).
        self.assertIn("doctor", combined.lower(),
                      f"F44 must hint at doctor --fix, got:\n{combined}")

    def test_session_workspace_missing_does_not_traceback(self) -> None:
        """P3-4 (round 11): when `.developer` exists but `workspace/<dev>/`
        was removed entirely (e.g. a person deleted it, or it's a fresh
        checkout of a project that only carries `.developer`), `session`
        used to raise FileNotFoundError on the first write_text and surface
        a raw Python traceback. Now rotate_if_full creates the workspace
        directory on the spot, mirroring cmd_init / _check_workspace_dir."""
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        shutil.rmtree(ws)
        self.assertFalse(ws.exists())
        r = self.h.run(["session", "--title", "T"])
        self.assertEqual(r.returncode, 0,
                         f"session must transparently create a missing workspace:\n"
                         f"{r.stdout}\n{r.stderr}")
        # Workspace must now exist with the journal written to it.
        self.assertTrue(ws.is_dir(), "workspace dir must be created on demand")
        self.assertTrue((ws / "journal-1.md").is_file(),
                        "first journal must be created on freshly-made workspace")

    def test_session_defaults_title_to_active_task(self) -> None:
        """Improvement 7: `session` without --title uses the active task's
        title and records a Task: link line in the journal."""
        self.h.run(["task", "create", "Fix login crash", "--slug", "fix"])
        r = self.h.run(["session", "--summary", "found root cause"])
        self.assertEqual(r.returncode, 0, f"must not require --title when a task is active\n{r.stdout}")
        self.assertIn("Fix login crash", r.stdout)
        j = self.h.tmpdir / ".trellis-lite/workspace/tester/journal-1.md"
        content = j.read_text()
        self.assertIn("Fix login crash", content)
        self.assertIn("**Task**: `.trellis-lite/tasks/", content)

    def test_session_still_requires_title_without_active_task(self) -> None:
        r = self.h.run(["session", "--summary", "orphan"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stdout + r.stderr)

    def test_session_explicit_title_no_task_line_without_active_task(self) -> None:
        """No active task → no Task: line injected (zero-behavior-change path)."""
        r = self.h.run(["session", "--title", "Solo", "--summary", "s"])
        self.assertEqual(r.returncode, 0)
        j = self.h.tmpdir / ".trellis-lite/workspace/tester/journal-1.md"
        self.assertNotIn("**Task**", j.read_text())

    def test_session_stale_pointer_no_dangling_task_link(self) -> None:
        """When .current-task points at a deleted task dir, session must NOT
        inject a dangling Task: link nor degrade the title to a bare dir name.
        With no --title it should fall back to requiring one (exit 1)."""
        import shutil as _shutil
        from ._helpers import find_task
        self.h.run(["task", "create", "Fix crash", "--slug", "fix"])
        tdir = find_task(self.h.tmpdir, "fix")
        _shutil.rmtree(tdir)  # simulate deleted task dir → stale pointer
        # No title → cannot derive from a dead task → usage error
        r = self.h.run(["session", "--summary", "x"])
        self.assertNotEqual(r.returncode, 0)
        # Explicit title → recorded, but NO Task: link to the dead path
        r2 = self.h.run(["session", "--title", "Manual", "--summary", "x"])
        self.assertEqual(r2.returncode, 0)
        j = self.h.tmpdir / ".trellis-lite/workspace/tester/journal-1.md"
        self.assertNotIn("**Task**", j.read_text())