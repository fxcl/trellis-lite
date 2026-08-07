"""Tests for the `init` command and developer identity setup."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ._helpers import Harness, LITE_ROOT


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

    def test_recovers_from_file_in_init_path(self) -> None:
        """P3-2 (round 12): if .trellis-lite/tasks exists as a stray regular
        file (partial sync, previous broken init, accidental `touch`), running
        `init` must NOT raise FileExistsError on Python 3.12+. The stray file
        is transparently replaced with a directory, mirroring the doctor --fix
        path. Mirrors P3-3 / P3-4 of round 11 (same family of fixes)."""
        # Fresh tmpdir with no .trellis-lite/, then partial-init pollution.
        fresh = Path(tempfile.mkdtemp(prefix="trellis-init-stray-"))
        try:
            tdir = fresh / ".trellis-lite"
            tdir.mkdir()
            # tasks/ must be a regular file — this is the failure case.
            (tdir / "tasks").write_text("not a directory\n", encoding="utf-8")
            r = subprocess.run(  # noqa: S603 — controlled test invocation
                ["python3", str(LITE_ROOT / ".trellis-lite/scripts/trellis.py"),
                 "init", "tester"],
                cwd=str(fresh),
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(r.returncode, 0,
                             f"init must recover from stray tasks file:\n"
                             f"{r.stdout}\n{r.stderr}")
            # All three required subdirs must exist after init.
            self.assertTrue((tdir / "tasks/archive").is_dir(),
                            "tasks/archive must be created after stray-file recovery")
            self.assertTrue((tdir / "spec").is_dir())
            self.assertTrue((tdir / "workspace/tester").is_dir())
        finally:
            shutil.rmtree(fresh, ignore_errors=True)