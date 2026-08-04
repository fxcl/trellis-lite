"""Tests for the task status state machine.

The state machine is centralized in trellis.py:
- STATUSES: the set of valid status strings
- ALLOWED_TRANSITIONS: which status can follow which
- set_status(): the only function that mutates task.json status

These tests lock the contract so future status additions/changes are
intentional, not accidental drift.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ._helpers import Harness

# Import the constants and helper directly from the script.
import importlib.util
_SCRIPT = Path(__file__).resolve().parent.parent / ".trellis-lite/scripts/trellis.py"
_spec = importlib.util.spec_from_file_location("trellis_script", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
STATUSES = _mod.STATUSES
ALLOWED_TRANSITIONS = _mod.ALLOWED_TRANSITIONS
set_status = _mod.set_status
FILE_TASK_JSON = _mod.FILE_TASK_JSON


class TestStatusMachineConstants(unittest.TestCase):
    """Lock the public contract: STATUSES and ALLOWED_TRANSITIONS."""

    def test_statuses_contains_exactly_five_values(self) -> None:
        self.assertEqual(
            STATUSES,
            frozenset({"planning", "in_progress", "done", "archived", "cancelled"}),
        )

    def test_terminal_states_have_no_transitions(self) -> None:
        # archived and cancelled are terminal — once you reach them, you stop.
        self.assertEqual(ALLOWED_TRANSITIONS["archived"], frozenset())
        self.assertEqual(ALLOWED_TRANSITIONS["cancelled"], frozenset())

    def test_done_transitions_to_archived_or_cancelled(self) -> None:
        # done is "complete but not yet archived" — the next move is either
        # archive (typical) or cancel (user changed their mind).
        self.assertEqual(
            ALLOWED_TRANSITIONS["done"],
            frozenset({"archived", "cancelled"}),
        )

    def test_planning_can_go_to_any_active_or_terminal(self) -> None:
        # From planning, you can start work, finish directly, archive, or cancel.
        self.assertEqual(
            ALLOWED_TRANSITIONS["planning"],
            frozenset({"in_progress", "done", "archived", "cancelled"}),
        )

    def test_in_progress_can_finish_archive_or_cancel(self) -> None:
        self.assertEqual(
            ALLOWED_TRANSITIONS["in_progress"],
            frozenset({"done", "archived", "cancelled"}),
        )

    def test_every_status_has_a_transition_entry(self) -> None:
        # Defensive: every status in STATUSES must have an entry, even if empty.
        for s in STATUSES:
            self.assertIn(s, ALLOWED_TRANSITIONS, f"{s!r} missing from ALLOWED_TRANSITIONS")

    def test_no_rollback_to_planning(self) -> None:
        # Once you've started (in_progress, done, etc.) you cannot go back to planning.
        for s in ("in_progress", "done", "archived", "cancelled"):
            self.assertNotIn("planning", ALLOWED_TRANSITIONS[s])


class TestSetStatusHelper(unittest.TestCase):
    """Verify set_status() behavior: success path + 3 failure paths."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.run(["task", "create", "T", "--slug", "t"])
        # Locate the task dir created by Harness
        tasks_dir = self.h.tmpdir / ".trellis-lite/tasks"
        self.task_dir = next(p for p in tasks_dir.iterdir() if p.is_dir() and not p.name == "archive")

    def tearDown(self) -> None:
        self.h.cleanup()

    def test_set_status_writes_new_status(self) -> None:
        ok = set_status(self.task_dir, "in_progress", when="started")
        self.assertTrue(ok)
        data = json.loads((self.task_dir / FILE_TASK_JSON).read_text())
        self.assertEqual(data["status"], "in_progress")
        self.assertIn("started", data)

    def test_set_status_without_when_omits_timestamp(self) -> None:
        ok = set_status(self.task_dir, "in_progress")
        self.assertTrue(ok)
        data = json.loads((self.task_dir / FILE_TASK_JSON).read_text())
        self.assertEqual(data["status"], "in_progress")
        self.assertNotIn("when", data)

    def test_set_status_returns_false_on_missing_file(self) -> None:
        (self.task_dir / FILE_TASK_JSON).unlink()
        ok = set_status(self.task_dir, "done", when="finished")
        self.assertFalse(ok)

    def test_set_status_returns_false_on_corrupted_file(self) -> None:
        (self.task_dir / FILE_TASK_JSON).write_text("{not json", encoding="utf-8")
        ok = set_status(self.task_dir, "done", when="finished")
        self.assertFalse(ok)

    def test_set_status_returns_false_on_empty_file(self) -> None:
        (self.task_dir / FILE_TASK_JSON).write_text("", encoding="utf-8")
        ok = set_status(self.task_dir, "done", when="finished")
        self.assertFalse(ok)

    def test_set_status_returns_false_on_unknown_status(self) -> None:
        # Returns False (not raise) so callers can treat all failure modes
        # uniformly via `if not set_status(...): print Warning; continue`.
        self.assertFalse(set_status(self.task_dir, "paused"))

    def test_set_status_preserves_other_fields(self) -> None:
        # set_status must not nuke title/slug/created.
        set_status(self.task_dir, "in_progress", when="started")
        data = json.loads((self.task_dir / FILE_TASK_JSON).read_text())
        self.assertEqual(data["title"], "T")
        self.assertEqual(data["slug"], "t")
        self.assertIn("created", data)

    def test_set_status_enforces_forward_only_transitions(self) -> None:
        # done → in_progress must be blocked (no rollback).
        # Drive task to done via allowed transitions.
        self.assertTrue(set_status(self.task_dir, "in_progress", when="started"))
        self.assertTrue(set_status(self.task_dir, "done", when="finished"))
        # Now try rollback — must return False.
        self.assertFalse(set_status(self.task_dir, "in_progress"))

    def test_set_status_allows_done_to_cancelled(self) -> None:
        # User changed their mind after finishing but before archiving.
        self.assertTrue(set_status(self.task_dir, "in_progress", when="started"))
        self.assertTrue(set_status(self.task_dir, "done", when="finished"))
        self.assertTrue(set_status(self.task_dir, "cancelled", when="cancelled"))
        data = json.loads((self.task_dir / FILE_TASK_JSON).read_text())
        self.assertEqual(data["status"], "cancelled")

    def test_set_status_blocks_terminal_state_transitions(self) -> None:
        # archived/cancelled are terminal — no further transitions.
        self.assertTrue(set_status(self.task_dir, "in_progress", when="started"))
        self.assertTrue(set_status(self.task_dir, "done", when="finished"))
        self.assertTrue(set_status(self.task_dir, "archived", when="archived"))
        # archived → anything must fail
        self.assertFalse(set_status(self.task_dir, "in_progress"))
        self.assertFalse(set_status(self.task_dir, "done"))

    def test_set_status_skips_transition_check_when_status_missing(self) -> None:
        # Legacy tasks without `status` field — let the transition happen so we
        # don't break older data. Only enforce when a known status is recorded.
        data = json.loads((self.task_dir / FILE_TASK_JSON).read_text())
        del data["status"]
        (self.task_dir / FILE_TASK_JSON).write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(set_status(self.task_dir, "in_progress", when="started"))


if __name__ == "__main__":
    unittest.main()
