"""Tests for the centralized Usage dictionary.

The Usage contract:
- USAGE maps a command key to its canonical one-line usage.
- usage_for(key) prints "Usage: <line>" in red.
- Every command that handles bad-args should call usage_for(<key>) — never
  print a hand-rolled Usage line.

These tests lock the structure (key set, prefix, uniqueness) AND verify the
end-to-end behavior: running each command with no args actually prints the
matching USAGE[key] line. That guards against drift between the dict and the
in-line Usage strings in each command function.
"""

from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ._helpers import Harness

# Import the constants and helper directly from the script.
_SCRIPT = Path(__file__).resolve().parent.parent / ".trellis-lite/scripts/trellis.py"
_spec = importlib.util.spec_from_file_location("trellis_script", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
USAGE = _mod.USAGE
usage_for = _mod.usage_for


class TestUsageDictionary(unittest.TestCase):
    """Lock the structure of USAGE: keys, prefix, uniqueness, non-empty."""

    def test_usage_is_dict(self) -> None:
        self.assertIsInstance(USAGE, dict)

    def test_usage_keys_are_non_empty_strings(self) -> None:
        for k in USAGE:
            self.assertIsInstance(k, str)
            self.assertGreater(len(k), 0, f"empty key: {k!r}")

    def test_usage_values_start_with_trellis_py(self) -> None:
        # Every Usage line should name the program so users see what to type.
        for k, v in USAGE.items():
            self.assertTrue(
                v.startswith("trellis.py "),
                f"USAGE[{k!r}] = {v!r} does not start with 'trellis.py '",
            )

    def test_usage_values_are_unique(self) -> None:
        # Two commands sharing a Usage line is almost always a bug.
        values = list(USAGE.values())
        self.assertEqual(len(values), len(set(values)), "duplicate Usage values")

    def test_all_expected_command_keys_present(self) -> None:
        # If you add a new command, also add its Usage entry. This list is the
        # set of commands that currently print Usage lines.
        expected = {
            "init", "task", "task create", "task start",
            "task archive", "task cancel", "task delete", "session",
        }
        self.assertEqual(set(USAGE), expected)


class TestUsageForHelper(unittest.TestCase):
    """Verify usage_for(key) prints the expected line."""

    def test_usage_for_prints_red_usage_prefix(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            usage_for("init")
        out = buf.getvalue()
        # Strip ANSI color for assertion
        clean = out.replace("\033[0m", "").replace("\033[31m", "")
        self.assertEqual(clean, f"Usage: {USAGE['init']}\n")

    def test_usage_for_missing_key_raises(self) -> None:
        # Caller bug — should fail loudly, not silently print wrong text.
        with self.assertRaises(KeyError):
            usage_for("nonexistent_command")


class TestUsageEndToEnd(unittest.TestCase):
    """End-to-end: each command actually prints USAGE[key] on bad input.

    This is the contract that catches drift: if a developer adds a new command
    and forgets to route its bad-args path through usage_for(), this test fails.
    Uses Harness.run() subprocess invocation so cwd + .trellis-lite/ match real
    usage.
    """

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.cleanup()

    def _assert_usage(self, argv: list[str], key: str) -> None:
        r = self.h.run(argv)
        # Bad args → exit 1
        self.assertEqual(r.returncode, 1, f"{argv} should exit 1\nstdout: {r.stdout}")
        # Strip ANSI and compare against the dict
        out = r.stdout.replace("\033[0m", "").replace("\033[31m", "")
        expected = f"Usage: {USAGE[key]}"
        self.assertIn(
            expected, out,
            f"{argv} stdout missing expected Usage line.\n"
            f"expected substring: {expected!r}\ngot: {out!r}",
        )

    def test_init_no_args(self) -> None:
        self._assert_usage(["init"], "init")

    def test_task_no_args(self) -> None:
        self._assert_usage(["task"], "task")

    def test_task_create_no_args(self) -> None:
        self._assert_usage(["task", "create"], "task create")

    def test_task_start_no_args(self) -> None:
        self._assert_usage(["task", "start"], "task start")

    def test_task_archive_no_args(self) -> None:
        self._assert_usage(["task", "archive"], "task archive")

    def test_task_cancel_no_args(self) -> None:
        self._assert_usage(["task", "cancel"], "task cancel")

    def test_task_delete_no_args(self) -> None:
        self._assert_usage(["task", "delete"], "task delete")

    def test_session_no_title(self) -> None:
        self._assert_usage(["session"], "session")


if __name__ == "__main__":
    unittest.main()