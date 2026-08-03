"""Tests for the `init` command and developer identity setup."""

from __future__ import annotations

import unittest
from pathlib import Path

from ._helpers import Harness


class TestInit(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    def test_creates_runtime_directories(self) -> None:
        t = self.h.tmpdir / ".trellis-lite"
        self.assertTrue((t / "tasks/archive").is_dir(), "tasks/archive missing")
        self.assertTrue((t / "spec").is_dir(), "spec/ missing")
        self.assertTrue((t / "workspace/tester").is_dir(), "workspace/tester missing")

    def test_writes_developer_file(self) -> None:
        dev = self.h.tmpdir / ".trellis-lite/.developer"
        self.assertTrue(dev.is_file())
        self.assertEqual(dev.read_text().strip(), "name=tester")

    def test_creates_index_and_journal(self) -> None:
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        self.assertTrue((ws / "index.md").is_file())
        self.assertTrue((ws / "journal-1.md").is_file())

    def test_creates_spec_readme_template(self) -> None:
        spec_readme = self.h.tmpdir / ".trellis-lite/spec/README.md"
        self.assertTrue(spec_readme.is_file())
        self.assertIn("Coding Specs", spec_readme.read_text())

    def test_invalid_name_rejected(self) -> None:
        r = self.h.run(["init", "../evil"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("name must contain only", r.stdout + r.stderr)

    def test_name_with_dot_rejected(self) -> None:
        r = self.h.run(["init", "evil.name"])
        self.assertNotEqual(r.returncode, 0)

    def test_idempotent(self) -> None:
        """Re-running init on the same dir must not clobber existing data."""
        ws = self.h.tmpdir / ".trellis-lite/workspace/tester"
        ws.joinpath("index.md").write_text("KEEP ME")
        r = self.h.run(["init", "tester"])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(ws.joinpath("index.md").read_text(), "KEEP ME")