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

    def test_session_warns_on_bad_commit_and_drops(self) -> None:
        r = self.h.run(["session", "--title", "T", "--commit", "BAD!"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("Warning", r.stdout)
        # Bad commit should NOT appear in journal
        j = self.h.tmpdir / ".trellis-lite/workspace/tester/journal-1.md"
        self.assertNotIn("BAD!", j.read_text())

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