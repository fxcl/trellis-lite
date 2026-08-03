"""Tests for the context, specs, and help commands."""

from __future__ import annotations

import unittest
from pathlib import Path

from ._helpers import Harness


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