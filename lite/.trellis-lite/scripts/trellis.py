#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trellis Lite — Single-file task & session manager for agile solo developers.

Replaces 20+ scripts with one. Zero external dependencies (Python 3.9+).

Usage:
    python3 trellis.py init <your-name>
    python3 trellis.py task create "<title>" [--slug <name>]
    python3 trellis.py task start <name>
    python3 trellis.py task current
    python3 trellis.py task finish
    python3 trellis.py task archive <name>
    python3 trellis.py task cancel <name>
    python3 trellis.py task list [--all]
    python3 trellis.py session --title "Title" --summary "Summary" [--commit <hash>]
    python3 trellis.py context
    python3 trellis.py specs
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ============================================================================
# Constants
# ============================================================================

TRELLIS_DIR = ".trellis-lite"
FILE_DEVELOPER = ".developer"
FILE_CURRENT_TASK = ".current-task"
FILE_CONFIG = "config.yaml"
DIR_TASKS = "tasks"
DIR_ARCHIVE = "archive"
DIR_SPEC = "spec"
DIR_WORKSPACE = "workspace"
FILE_TASK_JSON = "task.json"
JOURNAL_PREFIX = "journal-"
# A single journal file is rotated once it exceeds this line count to keep
# files small and to limit AI context-window consumption per read.
MAX_JOURNAL_LINES = 2000

# Task status state machine. Centralized so adding a new status (e.g. "paused")
# only requires updating this constant + the ALLOWED_TRANSITIONS map below.
# All writes to data["status"] must go through set_status(), which enforces
# both membership (STATUSES) AND transition legality (ALLOWED_TRANSITIONS) —
# see set_status() body.
STATUSES: frozenset[str] = frozenset({"planning", "in_progress", "done", "archived", "cancelled"})
# Forward-only transitions (no rollback). Terminal states (archived, cancelled)
# cannot transition further. `done → cancelled` is allowed so a user can change
# their mind after finishing but before archiving.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "planning":    frozenset({"in_progress", "done", "archived", "cancelled"}),
    "in_progress": frozenset({"done", "archived", "cancelled"}),
    "done":        frozenset({"archived", "cancelled"}),
    "archived":    frozenset(),  # terminal
    "cancelled":   frozenset(),  # terminal
}

# Version is the single source of truth for `version` output and diagnostics.
# Keep it in sync with lite/README.md and any release tag.
__version__ = "0.6.9"

# ANSI colors
C_RESET = "\033[0m"
C_RED = "\033[31m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_DIM = "\033[2m"


def colored(text: str, color: str) -> str:
    return f"{color}{text}{C_RESET}"


# Single source of truth for `Usage: ...` error lines. Every command that prints
# Usage routes through usage_for() so the prefix, color, and quote style stay
# consistent. To add a new command: add an entry here + use usage_for(<key>).
USAGE: dict[str, str] = {
    "init":         "trellis.py init <your-name>",
    "task":         "trellis.py task <create|start|current|finish|archive|cancel|list|delete>",
    "task create":  'trellis.py task create "<title>" [--slug <name>] [--replace]',
    "task start":   "trellis.py task start <name>",
    "task archive": "trellis.py task archive <name>",
    "task cancel":  "trellis.py task cancel <name>",
    "task delete":  "trellis.py task delete <name> [--force]",
    "session":      'trellis.py session --title "Title" --summary "Summary"',
}


def usage_for(key: str) -> None:
    """Print a red 'Usage: ...' line. KeyError if key is missing (caller bug)."""
    print(colored(f"Usage: {USAGE[key]}", C_RED))


# ============================================================================
# Path helpers
# ============================================================================

def get_repo_root(init_ok: bool = False) -> Path:
    """Find nearest ancestor containing .trellis-lite/.

    Args:
        init_ok: If True, return cwd when no .trellis-lite/ is found (for the
            init command itself, which creates the directory). If False (default),
            exit 1 with a clear message — silent fallback would cause other commands
            to write into the wrong directory.
    """
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / TRELLIS_DIR).is_dir():
            return current
        current = current.parent
    if init_ok:
        return Path.cwd().resolve()
    print(colored("Error: not inside a Trellis Lite project. Run 'init' first.", C_RED))
    sys.exit(1)


def get_trellis_dir() -> Path:
    return get_repo_root() / TRELLIS_DIR


def get_developer() -> str | None:
    dev_file = get_trellis_dir() / FILE_DEVELOPER
    if not dev_file.is_file():
        return None
    for line in dev_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("name="):
            return line.split("=", 1)[1].strip()
    return None


def get_workspace_dir() -> Path | None:
    dev = get_developer()
    if dev:
        return get_trellis_dir() / DIR_WORKSPACE / dev
    return None


def get_tasks_dir() -> Path:
    return get_trellis_dir() / DIR_TASKS


def get_spec_dir() -> Path:
    return get_trellis_dir() / DIR_SPEC


# ============================================================================
# Slugify
# ============================================================================

def slugify(text: str) -> str:
    """Convert text to URL-safe slug. Falls back to short hash for non-ASCII."""
    result = text.lower().strip()
    result = re.sub(r"[^a-z0-9]+", "-", result)
    result = result.strip("-")
    if result:
        return result
    # Non-ASCII title (e.g. CJK): use short hash for uniqueness
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:6]
    return f"t-{h}"


def date_prefix() -> str:
    return datetime.now().strftime("%m-%d")


# ============================================================================
# JSON helpers
# ============================================================================

def read_json(path: Path) -> dict:
    """Read JSON file. Returns {} on missing/corrupted (lossy — prefer read_json_strict for writes)."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def read_json_strict(path: Path) -> dict | None:
    """Read JSON file strictly. Returns None on missing/corrupted/non-dict/empty.

    Use for state-mutating operations (e.g. set_status) where 'file is bad'
    must be distinguished from 'file is missing'. For general reads where an
    empty dict is acceptable, prefer read_json() which returns {} on failure.
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or not data:
        return None
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe_mkdir(p: Path) -> bool:
    """mkdir p, transparently recovering from a stray file at the same path.

    Returns True if a new directory was created (or replaced over a file),
    False if `p` was already a directory.

    Why this exists: pathlib's `Path.mkdir(exist_ok=True)` only suppresses
    the "already exists" error when the path is **already a directory**.
    If the path is a regular file (stray `touch`, partial git sync of a
    half-initialised state, mid-init crash leaving a file where a dir
    should be), `mkdir` raises `FileExistsError` on Python 3.12+ —
    a raw traceback that defeats `doctor --fix`. Unlinking the stray file
    first lets the auto-repair path complete the user's intent
    (`mkdir` then succeeds).

    Use for all `mkdir(parents=True, exist_ok=True)` calls in repair paths.
    """
    if p.is_dir():
        return False
    if p.exists() and not p.is_dir():
        # Stray file at the path we need as a directory — remove it.
        # Doctor is opt-in via `trellis.py doctor --fix`, so this
        # deletion only happens when the user explicitly asked to repair.
        p.unlink()
    p.mkdir(parents=True, exist_ok=True)
    return True


# ============================================================================
# Git helpers
# ============================================================================

def git_status_porcelain() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def git_log_oneline(n: int = 5) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def git_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


# ============================================================================
# Current task management (file-based, no session complexity)
# ============================================================================

def get_current_task() -> str | None:
    """Return repo-relative path of active task, or None."""
    ct_file = get_trellis_dir() / FILE_CURRENT_TASK
    if not ct_file.is_file():
        return None
    val = ct_file.read_text(encoding="utf-8").strip()
    return val or None


def set_current_task(task_rel: str) -> None:
    ct_file = get_trellis_dir() / FILE_CURRENT_TASK
    ct_file.write_text(task_rel + "\n", encoding="utf-8")


def clear_current_task() -> None:
    ct_file = get_trellis_dir() / FILE_CURRENT_TASK
    if ct_file.is_file():
        ct_file.unlink()


def set_status(task_dir: Path, new_status: str, *, when: str | None = None) -> bool:
    """Set task.json status with optional timestamp. Returns True on success.

    Strict: rejects (returns False) on:
    - Unknown status (not in STATUSES)
    - Illegal transition (current → new_status not in ALLOWED_TRANSITIONS)
    - Missing file / corrupted JSON / empty dict / non-dict

    Idempotent: if the task is already at new_status, returns True without
    rewriting the file or updating timestamps. This keeps re-invoking a CLI
    command (e.g. `task start` on an in_progress task) a safe no-op.

    Returns False (not raise) so callers can treat all failure modes uniformly
    via the same `if not set_status(...): print Warning; continue` pattern.
    The `when` argument names the timestamp field (e.g. "started", "finished",
    "archived", "cancelled"); omit it for transitions that don't need a stamp.
    """
    if new_status not in STATUSES:
        return False
    task_json_path = task_dir / FILE_TASK_JSON
    data = read_json_strict(task_json_path)
    if data is None:
        return False
    current = data.get("status")
    # Idempotent: already at target status → success without side effects.
    # Re-running `task start` on an in_progress task must not look like failure.
    if current == new_status:
        return True
    # Enforce forward-only transition. Tasks without a recorded current status
    # (e.g. legacy or just-created planning task) skip this check.
    if current in STATUSES and new_status not in ALLOWED_TRANSITIONS[current]:
        return False
    data["status"] = new_status
    if when:
        data[when] = datetime.now().isoformat()
    write_json(task_json_path, data)
    return True


def list_journals(workspace: Path) -> list[tuple[int, Path]]:
    """Return [(number, path), ...] sorted by number for all journal files.

    Skips files that don't match `journal-N.md` (e.g. partial deletes, manual
    files). Returns [] if workspace is not a directory.
    """
    if not workspace.is_dir():
        return []
    journals: list[tuple[int, Path]] = []
    for j in workspace.glob(f"{JOURNAL_PREFIX}*.md"):
        m = re.match(rf"{JOURNAL_PREFIX}(\d+)\.md$", j.name)
        if m:
            journals.append((int(m.group(1)), j))
    journals.sort()
    return journals


def rotate_if_full(workspace: Path, journals: list[tuple[int, Path]]) -> Path:
    """Return the journal path to write to next, creating a new one if needed.

    If no journals exist, creates `journal-1.md`. If the latest journal is
    at or above MAX_JOURNAL_LINES lines, creates the next numbered file.

    Raises:
        NotADirectoryError: if `workspace` exists but is not a directory
            (e.g. a regular file was created at the path by accident, git
            sync of a half-initialised state, or a stray `touch`). Callers
            (cmd_session, doctor --fix) should translate this into a
            actionable error message; previously the FileNotFoundError or
            NotADirectoryError bubbled as a raw Python traceback.
    """
    if workspace.exists() and not workspace.is_dir():
        raise NotADirectoryError(
            f"workspace path is not a directory: {workspace} "
            f"(run 'trellis.py doctor --fix' to repair)"
        )
    if not journals:
        journal = workspace / f"{JOURNAL_PREFIX}1.md"
        journal.write_text("# Journal 1\n\n", encoding="utf-8")
        return journal
    max_num, journal = journals[-1]
    if len(journal.read_text(encoding="utf-8").splitlines()) >= MAX_JOURNAL_LINES:
        num = max_num + 1
        journal = workspace / f"{JOURNAL_PREFIX}{num}.md"
        journal.write_text(f"# Journal {num}\n\n", encoding="utf-8")
    return journal


class AmbiguousTaskName(Exception):
    """Raised when a task name resolves to multiple matching directories.

    Carries the input and the candidate paths so callers can present a
    helpful list instead of a generic "Task not found" message.
    """
    def __init__(self, task_input: str, matches: list[Path]) -> None:
        self.task_input = task_input
        self.matches = matches
        super().__init__(f"ambiguous task name: {task_input}")


def resolve_task_dir(task_input: str) -> Path:
    """Resolve task name to absolute directory path.

    Raises:
        FileNotFoundError: if no directory matches the input.
        AmbiguousTaskName: if multiple directories match (caller should
            present the candidate list rather than a generic not-found msg).
    """
    # Reject path separators and traversal (e.g. "../spec")
    if "/" in task_input or "\\" in task_input or ".." in task_input:
        raise FileNotFoundError(f"Invalid task name: {task_input}")
    # Reject the archive container itself (bare name, case-insensitive)
    if task_input.lower() == DIR_ARCHIVE:
        raise FileNotFoundError(f"Invalid task name: {task_input}")
    tasks_dir = get_tasks_dir()
    # Try direct: tasks/<input>
    candidate = tasks_dir / task_input
    if candidate.is_dir():
        return candidate
    # Try with date prefix: tasks/MM-DD-<input>
    # Literal endswith match (no glob semantics) so user input is matched exactly
    matches: list[Path] = []
    for t in tasks_dir.iterdir():
        if t.is_dir() and t.name.endswith(f"-{task_input}"):
            matches.append(t)
    matches.sort()
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AmbiguousTaskName(task_input, matches)
    raise FileNotFoundError(f"task not found: {task_input}")


def resolve_or_report(task_input: str) -> Path | None:
    """Call resolve_task_dir and translate exceptions into user-facing output.

    Returns the resolved directory, or None after printing an appropriate
    error message (red "Task not found" or yellow "Ambiguous" list). Callers
    should treat None as "already reported, just exit 1".
    """
    try:
        return resolve_task_dir(task_input)
    except AmbiguousTaskName as e:
        print(colored(f"Ambiguous: multiple matches for '{e.task_input}':", C_YELLOW))
        for m in e.matches:
            print(f"  {m.name}")
        return None
    except FileNotFoundError as e:
        print(colored(str(e), C_RED))
        return None


# ============================================================================
# Commands: init
# ============================================================================

def cmd_init(args: list[str]) -> int:
    """Initialize developer identity + scaffold .trellis-lite/ at repo root."""
    if not args:
        usage_for("init")
        return 1

    name = args[0]

    # Validate name: must be filesystem-safe
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        print(colored("Error: name must contain only letters, digits, hyphens, or underscores", C_RED))
        return 1

    # init is the only command allowed to run without an existing .trellis-lite/
    tdir = get_repo_root(init_ok=True) / TRELLIS_DIR

    # Create directories
    (tdir / DIR_TASKS / DIR_ARCHIVE).mkdir(parents=True, exist_ok=True)
    (tdir / DIR_SPEC).mkdir(parents=True, exist_ok=True)

    workspace = tdir / DIR_WORKSPACE / name
    workspace.mkdir(parents=True, exist_ok=True)

    # Write developer file
    dev_file = tdir / FILE_DEVELOPER
    dev_file.write_text(f"name={name}\n", encoding="utf-8")

    # Create index.md if not exists
    index_file = workspace / "index.md"
    if not index_file.exists():
        index_file.write_text(
            f"# {name}'s Workspace\n\n"
            f"Session journals are recorded here.\n",
            encoding="utf-8",
        )

    # Create first journal via rotate_if_full so header text/format stays in
    # sync with cmd_session's rotation and doctor's repair path.
    rotate_if_full(workspace, list_journals(workspace))

    # Create spec README if not exists
    spec_readme = get_spec_dir() / "README.md"
    if not spec_readme.exists():
        spec_readme.write_text(SPEC_TEMPLATE, encoding="utf-8")

    print(colored(f"✓ Trellis Lite initialized for '{name}'", C_GREEN))
    print(f"  Workspace: {workspace}")
    print(f"  Specs:     {get_spec_dir()}")
    print(f"  Tasks:     {get_tasks_dir()}")
    return 0


# ============================================================================
# Commands: task
# ============================================================================

def cmd_task(args: list[str]) -> int:
    """Dispatch to a task subcommand (create/start/current/finish/archive/cancel/list/delete)."""
    if not args:
        usage_for("task")
        return 1

    sub = args[0]
    rest = args[1:]

    if sub == "create":
        return _task_create(rest)
    elif sub == "start":
        return _task_start(rest)
    elif sub == "current":
        return _task_current(rest)
    elif sub == "finish":
        return _task_finish(rest)
    elif sub == "archive":
        return _task_archive(rest)
    elif sub == "cancel":
        return _task_cancel(rest)
    elif sub == "list":
        return _task_list(rest)
    elif sub == "delete":
        return _task_delete(rest)
    else:
        print(colored(f"Unknown task subcommand: {sub}", C_RED))
        return 1


def _task_create(args: list[str]) -> int:
    """Create a new task directory with prd.md, set as current.

    By default refuses to create if another task is active (the "one task at a time"
    rule). Pass --replace to take over an existing active task.
    """
    if not args:
        usage_for("task create")
        return 1

    # Parse: title + optional --slug + optional --replace
    slug = None
    replace = False
    title_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--slug" and i + 1 < len(args):
            slug = args[i + 1]
            i += 2
        elif args[i] == "--replace":
            replace = True
            i += 1
        else:
            title_parts.append(args[i])
            i += 1

    raw_title = " ".join(title_parts)
    # Strip a single pair of matching surrounding quotes ("" or ''), not each end independently
    title = raw_title
    if len(title) >= 2 and title[0] == title[-1] and title[0] in "\"'":
        title = title[1:-1]
    if not title:
        print(colored("Error: title cannot be empty", C_RED))
        return 1

    # Check for existing active task BEFORE any disk mutation.
    # This is the "one task at a time" rule (see docs/best-practices.md §7).
    existing = get_current_task()
    if existing and not replace:
        print(colored(
            f"Refusing to create: '{existing}' is still the active task. "
            f"Run 'task finish' or 'task cancel' first, "
            f"or pass --replace to take over.",
            C_RED,
        ))
        return 1

    slug = slugify(slug) if slug else slugify(title)
    dir_name = f"{date_prefix()}-{slug}"

    tasks_dir = get_tasks_dir()
    task_dir = tasks_dir / dir_name

    # Auto-increment if same-day slug already exists
    counter = 2
    while task_dir.exists():
        dir_name = f"{date_prefix()}-{slug}-{counter}"
        task_dir = tasks_dir / dir_name
        counter += 1

    task_dir.mkdir(parents=True)

    # Write task.json
    task_json = {
        "title": title,
        "slug": slug,
        "status": "planning",
        "created": datetime.now().isoformat(),
        "branch": git_branch() or "unknown",
    }
    write_json(task_dir / FILE_TASK_JSON, task_json)

    # Write default prd.md
    prd_content = f"""# {title}

## Goal
<!-- One-sentence description of what this task achieves -->

## Requirements
<!-- Bullet list of what needs to be done -->

## Acceptance Criteria
<!-- Checklist of verifiable conditions -->
- [ ] 

## Notes
<!-- Any constraints, context, or references -->
"""
    (task_dir / "prd.md").write_text(prd_content, encoding="utf-8")

    if existing and replace:
        # Take over means the old active task is no longer the focus. Close it
        # so `task list` doesn't show two tasks with in_progress / planning
        # alongside the new one — the "one task at a time" invariant that
        # _task_start itself warns about. Forward-only transitions make
        # done a safe target from both planning and in_progress; set_status
        # is idempotent (done→done returns True) and rejects terminal states
        # (archived/cancelled can't reach done) by returning False, which we
        # ignore — a terminal old task is left as-is and the user can clean
        # it up explicitly. We DO NOT clear .current-task here; set_current_task
        # below repoints it to the new task.
        old_dir = get_repo_root() / existing
        if old_dir.is_dir():
            set_status(old_dir, "done", when="finished")
        print(colored(
            f"Note: replaced active task '{existing}' with '{dir_name}'.",
            C_YELLOW,
        ))

    # Auto-set as current task
    rel = f"{TRELLIS_DIR}/{DIR_TASKS}/{dir_name}"
    set_current_task(rel)

    print(colored(f"✓ Task created: {dir_name}", C_GREEN))
    print(f"  Path: {task_dir}")
    print(f"  Status: planning")
    print(f"  Active: yes (auto-set)")
    return 0


def _task_start(args: list[str]) -> int:
    """Mark a task in_progress, set as current, warn if another task is in progress."""
    if not args:
        usage_for("task start")
        return 1

    task_dir = resolve_or_report(args[0])
    if task_dir is None:
        return 1

    # Warn when other tasks are still in_progress (one task at a time). Collect
    # all such tasks first so we emit a single concise warning instead of one
    # line per task — the user already has actionable info via `task list`.
    tasks_dir = get_tasks_dir()
    other_in_progress: list[str] = []
    if tasks_dir.is_dir():
        for t in sorted(tasks_dir.iterdir()):
            if not t.is_dir() or t.name in (DIR_ARCHIVE, task_dir.name):
                continue
            if read_json(t / FILE_TASK_JSON).get("status") == "in_progress":
                other_in_progress.append(t.name)
    if other_in_progress:
        names = ", ".join(other_in_progress)
        print(colored(
            f"Warning: {len(other_in_progress)} other task(s) still in_progress — "
            f"one task at a time ({names}). "
            f"Run 'task finish' or 'task cancel' to clean up.",
            C_YELLOW,
        ))

    # Update status via the central state-machine helper.
    # set_status is idempotent (returns True when already in_progress), so we
    # pre-check the current status to show an accurate message: a re-start on
    # an already-active task is a benign no-op, not a corrupted file.
    #
    # F48: pre-check with read_json_strict so missing/corrupted task.json
    # refuses cleanly. Previously the fallback `elif not set_status(...)`
    # branch printed a Warning but still called set_current_task + printed
    # "✓ Task started", leaving `.current-task` pointing at a task whose
    # metadata is unreadable — a split-brain state.
    #
    # Forward-only transitions (ALLOWED_TRANSITIONS) also reject re-entry
    # into in_progress from done / archived / cancelled. Without an explicit
    # guard here, set_status returns False on the illegal transition but the
    # user still sees "✓ Task started" — confusing.
    existing_data = read_json_strict(task_dir / FILE_TASK_JSON)
    if existing_data is None:
        print(colored(
            f"Error: '{task_dir.name}/task.json' is missing or corrupted; "
            f"refusing to start. Run 'trellis.py doctor --fix' to repair.",
            C_RED,
        ))
        return 1
    existing_status = existing_data.get("status")
    if existing_status == "in_progress":
        print(colored(f"Note: '{task_dir.name}' is already in_progress.", C_DIM))
    elif existing_status in ("done", "archived", "cancelled"):
        print(colored(
            f"Error: cannot start a task in terminal state '{existing_status}'. "
            f"Forward-only transitions are enforced (see ALLOWED_TRANSITIONS). "
            f"Use 'task archive <name>' to finalize, or create a new task.",
            C_RED,
        ))
        return 1
    elif not set_status(task_dir, "in_progress", when="started"):
        # Reachable only when the file passed the pre-check but became
        # unwritable mid-operation (concurrent edit, lost permissions).
        # Refuse rather than leaving .current-task switched but task.json
        # unchanged.
        print(colored(
            f"Error: failed to update '{task_dir.name}/task.json'; "
            f"refusing to start. Check file permissions and try again.",
            C_RED,
        ))
        return 1

    # Set as current (only reached for valid transitions / planning tasks)
    rel = f"{TRELLIS_DIR}/{DIR_TASKS}/{task_dir.name}"
    set_current_task(rel)

    print(colored(f"✓ Task started: {task_dir.name}", C_GREEN))
    print(f"  Status: in_progress")
    return 0


def _task_current(args: list[str]) -> int:
    """Print the active task, its status, and presence of prd.md/design.md."""
    current = get_current_task()
    if current is None:
        print(colored("No active task.", C_DIM))
        return 0

    print(f"Active task: {current}")

    # Show status. Use read_json_strict so a corrupted task.json surfaces as
    # an explicit warning instead of silently omitting Title/Status — the AI
    # calls `task current` to orient, and a silent drop hides the same
    # corrupted state that `doctor` flags as a problem (F55). Keep exit 0:
    # `task current` is a read (see exit-codes.md §"empty state returns 0").
    task_dir = get_repo_root() / current
    task_json = read_json_strict(task_dir / FILE_TASK_JSON)
    if task_json is None:
        print(colored(
            "  Warning: task.json is missing or corrupted — "
            "run 'trellis.py doctor --fix' to repair.",
            C_YELLOW,
        ))
    else:
        print(f"  Title:  {task_json.get('title', '?')}")
        print(f"  Status: {task_json.get('status', '?')}")

    # Show artifacts
    for f in ["prd.md", "design.md"]:
        if (task_dir / f).exists():
            print(f"  ✓ {f}")
        else:
            print(f"  {colored('—', C_DIM)} {f}")
    return 0


def _task_finish(args: list[str]) -> int:
    """Mark the current task done, warn if working tree is dirty, clear active pointer."""
    current = get_current_task()
    if current is None:
        # "no active task" when user asked to finish is a semantic error —
        # return non-zero so CI and shell scripts can detect it.
        print(colored("No active task to finish.", C_RED))
        return 1

    # Warn about uncommitted changes before finishing
    dirty = git_status_porcelain()
    if dirty:
        print(colored(f"Warning: {len(dirty.splitlines())} uncommitted change(s) in working tree", C_YELLOW))

    # Update task status via the central state-machine helper.
    # This refuses cleanly on missing/corrupted task.json so the active pointer
    # is never cleared on a downstream exception.
    task_dir = get_repo_root() / current
    if not set_status(task_dir, "done", when="finished"):
        print(colored(
            f"Error: task.json is missing or corrupted; refusing to finish. "
            f"Run 'trellis.py doctor --fix' to repair.",
            C_RED,
        ))
        return 1

    clear_current_task()
    print(colored(f"✓ Task finished: {current}", C_GREEN))
    print(colored("  Run 'task archive <name>' when ready to archive.", C_DIM))
    return 0


def _task_archive(args: list[str]) -> int:
    """Move a task to tasks/archive/YYYY-MM/, with auto-increment on collision."""
    if not args:
        usage_for("task archive")
        return 1

    task_dir = resolve_or_report(args[0])
    if task_dir is None:
        return 1

    # F32 + F47: pre-check with read_json_strict to refuse both terminal
    # (cancelled) and unreadable (missing/corrupted task.json) cases BEFORE
    # any disk mutation. Without this guard, set_status returns False but
    # shutil.move still physically moves the directory into archive/, producing
    # a split-brain state: directory is in archive/2026-MM/ but task.json
    # still reads status=cancelled or is unreadable. The user sees
    # '✓ Task archived' yet task list --all shows [cancelled] or [?], which
    # is confusing. Refuse explicitly with an actionable pointer.
    existing = read_json_strict(task_dir / FILE_TASK_JSON)
    if existing is None:
        print(colored(
            f"Refusing to archive: '{task_dir.name}/task.json' is missing or "
            f"corrupted. Run 'trellis.py doctor --fix' to repair, or "
            f"'task delete --force {task_dir.name}' to discard.",
            C_RED,
        ))
        return 1
    if existing.get("status") == "cancelled":
        print(colored(
            f"Refusing to archive: '{task_dir.name}' is cancelled. "
            f"Cancelled is a terminal state (ALLOWED_TRANSITIONS). "
            f"Use 'task delete --force {task_dir.name}' to remove it, "
            f"or create a new task if you want to redo the work.",
            C_RED,
        ))
        return 1

    # Update status via the central state-machine helper. Reachable only
    # when the file passed the pre-check; the remaining failure modes are
    # concurrent writes / lost permissions, which we treat as errors.
    if not set_status(task_dir, "archived", when="archived"):
        print(colored(
            f"Error: failed to update '{task_dir.name}/task.json' "
            f"before archiving; refusing. Check file permissions.",
            C_RED,
        ))
        return 1

    # Move to archive
    archive_dir = get_tasks_dir() / DIR_ARCHIVE
    month = datetime.now().strftime("%Y-%m")
    dest = archive_dir / month / task_dir.name

    # Auto-increment if destination already exists (prevents nesting)
    base_name = task_dir.name
    counter = 2
    while dest.exists():
        dest = archive_dir / month / f"{base_name}-{counter}"
        counter += 1

    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(task_dir), str(dest))

    # Clear current if it was this task (exact match on directory name)
    current = get_current_task()
    if current and Path(current).name == task_dir.name:
        clear_current_task()

    print(colored(f"✓ Task archived: {task_dir.name}", C_GREEN))
    print(f"  → {dest}")
    return 0


def _task_cancel(args: list[str]) -> int:
    """Mark a task cancelled in place; directory is kept for history."""
    if not args:
        usage_for("task cancel")
        return 1

    task_dir = resolve_or_report(args[0])
    if task_dir is None:
        return 1

    # F52: pre-check status before any mutation. set_status itself rejects
    # archived → cancelled (ALLOWED_TRANSITIONS["archived"] is frozenset())
    # and refuses on missing/corrupted task.json, but its caller fallback
    # was "print Warning + continue" — leaving a misleading
    # "✓ Task cancelled" message while task.json stayed archived, and
    # clearing `.current-task` even though no transition actually happened.
    # Refuse explicitly on illegal transitions / unreadable metadata.
    existing = read_json_strict(task_dir / FILE_TASK_JSON)
    if existing is None:
        print(colored(
            f"Refusing to cancel: '{task_dir.name}/task.json' is missing or "
            f"corrupted. Run 'trellis.py doctor --fix' to repair, or "
            f"'task delete --force {task_dir.name}' to discard.",
            C_RED,
        ))
        return 1
    cur_status = existing.get("status")
    if cur_status == "archived":
        print(colored(
            f"Refusing to cancel: '{task_dir.name}' is archived. "
            f"Archived is a terminal state (ALLOWED_TRANSITIONS). "
            f"Use 'task delete --force {task_dir.name}' to remove it.",
            C_RED,
        ))
        return 1
    if cur_status == "cancelled":
        # Idempotent: already cancelled, no-op success. Don't print the
        # warning that would suggest something went wrong.
        print(colored(f"Note: '{task_dir.name}' is already cancelled.", C_DIM))
        return 0
    # Forward transition (planning/in_progress → cancelled) plus the
    # explicit reverse (done → cancelled) are both allowed by the state
    # machine. Delegate to the central helper.
    if not set_status(task_dir, "cancelled", when="cancelled"):
        # Reachable only on concurrent-write / lost-permissions races.
        print(colored(
            f"Error: failed to update '{task_dir.name}/task.json'; "
            f"refusing to cancel. Check file permissions and try again.",
            C_RED,
        ))
        return 1

    # Clear current if it was this task
    current = get_current_task()
    if current and Path(current).name == task_dir.name:
        clear_current_task()

    print(colored(f"✓ Task cancelled: {task_dir.name}", C_GREEN))
    print(colored("  Directory kept in tasks/. Delete it manually if unneeded.", C_DIM))
    return 0


def _task_list(args: list[str]) -> int:
    """List active tasks (or all including archive with --all)."""
    show_all = "--all" in args
    tasks_dir = get_tasks_dir()
    if not tasks_dir.is_dir():
        print(colored("No tasks directory.", C_DIM))
        return 0

    active = sorted(t for t in tasks_dir.iterdir() if t.is_dir() and t.name != DIR_ARCHIVE)
    tasks = list(active)

    if show_all:
        archive = tasks_dir / DIR_ARCHIVE
        if archive.is_dir():
            for month_dir in sorted(archive.iterdir()):
                if month_dir.is_dir():
                    tasks.extend(sorted(t for t in month_dir.iterdir() if t.is_dir()))
        tasks.sort(key=lambda p: p.name)

    if not tasks:
        print(colored("No active tasks.", C_DIM))
        return 0

    title = "All Tasks (active + archive):" if show_all else "Active Tasks:"
    print(colored(title, C_CYAN))
    current = get_current_task()
    for t in tasks:
        data = read_json(t / FILE_TASK_JSON)
        status = data.get("status", "?")
        title = data.get("title", t.name)
        marker = colored("→", C_GREEN) if current and Path(current).name == t.name else " "
        if status == "in_progress":
            status_color = C_GREEN
        elif status in ("done", "archived", "cancelled"):
            status_color = C_DIM
        else:
            status_color = C_YELLOW
        print(f"  {marker} {t.name}  {colored(f'[{status}]', status_color)}  {title}")
    return 0


def _task_delete(args: list[str]) -> int:
    """Permanently delete a task directory. Defaults to cancelled-only; pass --force for any status."""
    if not args:
        usage_for("task delete")
        return 1

    # Parse --force flag
    force = False
    name_args: list[str] = []
    for a in args:
        if a == "--force":
            force = True
        else:
            name_args.append(a)
    if not name_args:
        usage_for("task delete")
        return 1

    task_dir = resolve_or_report(name_args[0])
    if task_dir is None:
        return 1

    # F53: pre-check with read_json_strict to refuse corrupted metadata
    # BEFORE any disk mutation (shutil.rmtree on a corrupted task is
    # irreversible — once the directory is gone, the only recovery is
    # `git reflog` or backups). Without this guard, read_json returns
    # {} for corrupted input, `data.get("status", "?")` falls back to
    # "?", and the user sees the misleading hint "Cancel it first
    # (task cancel X)" — but task cancel itself refuses on corrupted
    # (F52), trapping the user in a recovery loop. Detect corrupt
    # metadata explicitly and point at the right recovery path, matching
    # the symmetric pattern used in `_task_start` / `_task_archive` /
    # `_task_cancel`.
    #
    # F63: `--force` bypasses the corrupted-metadata guard. The non-force
    # refusal message itself recommends `task delete --force <name>` as
    # the recovery path; if --force also refused on corrupted metadata
    # (as F53 originally did), the user following that hint would hit the
    # same wall — `task cancel` refuses on corrupted (F52), `task delete`
    # refuses on corrupted (F53), and `task delete --force` refused too,
    # closing the only exit. --force is opt-in and the user has been told
    # it discards the task, so the irreversible rmtree is intentional.
    data = read_json_strict(task_dir / FILE_TASK_JSON)
    corrupted = data is None
    if corrupted and not force:
        print(colored(
            f"Refusing to delete: '{task_dir.name}/task.json' is missing or "
            f"corrupted. Run 'trellis.py doctor --fix' to repair, or "
            f"'task delete --force {task_dir.name}' to discard.",
            C_RED,
        ))
        return 1
    status = data.get("status", "?") if not corrupted else "?"
    if not force and status != "cancelled":
        print(colored(
            f"Refusing to delete task with status '{status}'. "
            f"Cancel it first (task cancel {task_dir.name}) or use --force.",
            C_RED,
        ))
        # Tip: .current-task still points at this task. Without this hint,
        # the user might miss that the pointer is stale after the refused
        # delete (we did NOT clear it because the deletion didn't happen).
        current = get_current_task()
        if current and Path(current).name == task_dir.name:
            print(colored(
                "  Tip: 'task current' still shows this task; "
                "run 'task cancel' first (or 'task finish' if in_progress).",
                C_DIM,
            ))
        return 1

    # Clear current pointer if it pointed here
    current = get_current_task()
    if current and Path(current).name == task_dir.name:
        clear_current_task()

    shutil.rmtree(task_dir)
    print(colored(f"✓ Task deleted: {task_dir.name}", C_GREEN))
    return 0


# ============================================================================
# Commands: session
# ============================================================================

def cmd_session(args: list[str]) -> int:
    """Append a session entry to the current journal; rotate when it exceeds the cap."""
    title = None
    summary = None
    commit = None

    i = 0
    while i < len(args):
        if args[i] == "--title" and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        elif args[i] == "--summary" and i + 1 < len(args):
            summary = args[i + 1]
            i += 2
        elif args[i] == "--commit" and i + 1 < len(args):
            commit = args[i + 1]
            i += 2
        else:
            i += 1

    if not title:
        usage_for("session")
        return 1

    # Validate commit hash format. Accept 4–64 hex chars to cover both SHA-1 (40)
    # and SHA-256 (64) — git 2.42+ may use SHA-256 by default. Reject (exit 1) so
    # a typo here doesn't silently produce a journal entry with a bogus hash.
    if commit and not re.match(r"^[0-9a-f]{4,64}$", commit):
        print(colored(
            f"Error: '{commit}' doesn't look like a git SHA (4-64 hex chars). "
            f"Refusing to record a session with a bogus commit hash.",
            C_RED,
        ))
        return 1

    workspace = get_workspace_dir()
    if workspace is None:
        # Distinguish "never initialized" from "file is corrupted" so the
        # error message points at the right repair (doctor --fix vs init).
        if (get_trellis_dir() / FILE_DEVELOPER).is_file():
            print(colored(
                "Error: .trellis-lite/.developer exists but has no 'name=' line. "
                "Run 'trellis.py doctor --fix' to repair, or re-init with "
                "'trellis.py init <name>' (will overwrite).",
                C_RED,
            ))
        else:
            print(colored("Developer not initialized. Run: trellis.py init <name>", C_RED))
        return 1

    # Find or create active journal. list_journals + rotate_if_full can raise
    # NotADirectoryError when workspace/<dev>/ was corrupted to a regular file
    # (stray touch, partial git sync, mid-init crash). Translate to a clean
    # red message instead of letting the Python traceback surface to the user.
    try:
        journals = list_journals(workspace)
        journal = rotate_if_full(workspace, journals)
    except NotADirectoryError as e:
        print(colored(f"Error: {e}", C_RED))
        return 1

    # Append session entry
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## {now} — {title}\n\n"
    if commit:
        entry += f"**Commits**: `{commit}`\n\n"
    if summary:
        entry += f"{summary}\n"
    else:
        entry += "(no summary)\n"

    with open(journal, "a", encoding="utf-8") as f:
        f.write(entry)

    # Count total sessions across all journals (list_journals skips non-numbered
    # files like journal-draft.md so this stays consistent with cmd_context).
    total = 0
    for _num, j in list_journals(workspace):
        total += len(re.findall(r"^## ", j.read_text(encoding="utf-8"), re.MULTILINE))

    print(colored(f"✓ Session recorded: {title}", C_GREEN))
    print(f"  Journal: {journal.name}")
    print(f"  Total sessions: {total}")
    return 0


# ============================================================================
# Commands: context
# ============================================================================

def cmd_context(args: list[str]) -> int:
    """Print full session context for AI consumption."""
    repo = get_repo_root()
    dev = get_developer()

    print(colored("=" * 60, C_DIM))
    print(colored("  Trellis Lite — Session Context", C_CYAN))
    print(colored("=" * 60, C_DIM))

    # Developer
    if dev:
        print(f"  Developer: {dev}")
    else:
        print(colored("  Developer: (not initialized — run 'trellis.py init <name>')", C_YELLOW))

    # Current task. read_json_strict so a corrupted active task surfaces as
    # a warning line instead of printing `Title: ?` / `Status: ?` — which is
    # indistinguishable from a legitimately untitled task and hides the same
    # corrupted state doctor flags as a problem (F55). `context` is the AI's
    # cross-session resume entry point; it must not silently degrade. Keep
    # exit 0: context is a read with no error path (exit-codes.md).
    current = get_current_task()
    if current:
        task_dir = repo / current
        data = read_json_strict(task_dir / FILE_TASK_JSON)
        print(f"  Active task: {current}")
        if data is None:
            print(colored(
                "    Warning: task.json is missing or corrupted — "
                "run 'trellis.py doctor --fix' to repair.",
                C_YELLOW,
            ))
        else:
            print(f"    Title:  {data.get('title', '?')}")
            print(f"    Status: {data.get('status', '?')}")

        artifacts = []
        for f in ["prd.md", "design.md"]:
            if (task_dir / f).exists():
                artifacts.append(f"✓ {f}")
            else:
                artifacts.append(colored(f"— {f}", C_DIM))
        print(f"    Artifacts: {' '.join(artifacts)}")
    else:
        print(colored("  Active task: none", C_DIM))

    # Git
    branch = git_branch()
    if branch:
        print(f"  Branch: {branch}")

    status = git_status_porcelain()
    if status:
        dirty = len(status.splitlines())
        print(f"  Dirty files: {dirty}")

    print(colored("-" * 60, C_DIM))

    # Recent commits
    log = git_log_oneline(5)
    if log:
        print(colored("  Recent commits:", C_DIM))
        for line in log.splitlines():
            print(f"    {line}")

    # Specs (top 5 + count)
    spec_dir = get_spec_dir()
    if spec_dir.is_dir():
        specs = sorted(spec_dir.rglob("*.md"))
        if specs:
            print(f"  Specs: {len(specs)} file(s)")
            for s in specs[:5]:
                print(f"    - {s.relative_to(spec_dir)}")
            if len(specs) > 5:
                print(colored(f"    ... +{len(specs) - 5} more (use 'specs' to list all)", C_DIM))

    # Latest journal entry (helps resume across sessions)
    workspace = get_workspace_dir()
    if workspace and workspace.is_dir():
        journals = list_journals(workspace)
        if journals:
            last_journal = journals[-1][1]
            content = last_journal.read_text(encoding="utf-8")
            titles = re.findall(r"^## (.+)$", content, re.MULTILINE)
            if titles:
                print(f"  Last session: {colored(titles[-1], C_DIM)}  ({last_journal.name})")

    print(colored("=" * 60, C_DIM))
    return 0


# ============================================================================
# Commands: specs (list available spec files)
# ============================================================================

def cmd_specs(args: list[str]) -> int:
    """List all .md files under spec/ that the AI can read."""
    spec_dir = get_spec_dir()
    if not spec_dir.is_dir():
        print(colored("No spec directory.", C_DIM))
        return 0

    specs = sorted(spec_dir.rglob("*.md"))
    if not specs:
        print(colored("No specs found. Write your first spec in spec/README.md", C_DIM))
        return 0

    print(colored("Available Specs:", C_CYAN))
    for s in specs:
        rel = s.relative_to(spec_dir)
        print(f"  {rel}")
    return 0


# ============================================================================
# Spec template (loaded from external file so it can evolve independently)
# ============================================================================

# Path to the bundled template shipped alongside this script. `init` writes
# it to spec/README.md on first install so users have something to edit.
# If the file is missing (e.g., someone deleted it after install), we fall
# back to a tiny inline copy so init never crashes.
SPEC_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "spec" / "TEMPLATE.md"
_SPEC_TEMPLATE_FALLBACK = (
    "# Coding Specs\n\n"
    "Write your project's coding conventions and patterns here. The AI reads these\n"
    "before implementing any code.\n\n"
    "See the [Trellis Lite docs](https://github.com/) for guidance.\n"
)


def load_spec_template() -> str:
    """Return the bundled SPEC template (or fallback if file is missing)."""
    try:
        return SPEC_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        return _SPEC_TEMPLATE_FALLBACK


SPEC_TEMPLATE = load_spec_template()


# ============================================================================
# Main entry
# ============================================================================

def print_help() -> None:
    print(colored("Trellis Lite", C_CYAN))
    print(colored(f"v{__version__} — Single-file task & session manager for agile solo developers.\n", C_DIM))
    print("Commands:")
    print(f"  {colored('init', C_GREEN)} <name>                    Initialize developer identity")
    print(f"  {colored('task create', C_GREEN)} \"<title>\" [--slug <s>]  Create a new task")
    print(f"  {colored('task start', C_GREEN)} <name>               Activate a task (status → in_progress)")
    print(f"  {colored('task current', C_GREEN)}                   Show active task")
    print(f"  {colored('task finish', C_GREEN)}                    Deactivate current task")
    print(f"  {colored('task archive', C_GREEN)} <name>            Archive a completed task")
    print(f"  {colored('task cancel', C_GREEN)} <name>            Cancel an abandoned task (keeps directory)")
    print(f"  {colored('task list', C_GREEN)} [--all]                   List tasks (--all includes archive)")
    print(f"  {colored('task delete', C_GREEN)} <name>            Delete a cancelled task permanently")
    print(f"  {colored('session', C_GREEN)} --title \"T\" --summary \"S\"  Record a session journal entry")
    print(f"  {colored('context', C_GREEN)}                       Print full session context")
    print(f"  {colored('specs', C_GREEN)}                         List available spec files")
    print(f"  {colored('doctor', C_GREEN)} [--fix]               Diagnose project state; --fix to repair")
    print(f"  {colored('help', C_GREEN)}                          Show this help")
    print(f"  {colored('version', C_GREEN)}                       Print version and exit")
    print(f"\nWorkflow: {colored('init', C_DIM)} → {colored('task create', C_DIM)} → {colored('task start', C_DIM)} → code → {colored('task archive', C_DIM)} → {colored('session', C_DIM)}")


def cmd_version(args: list[str]) -> int:
    """Print the trellis-lite version and exit."""
    print(f"trellis-lite {__version__}")
    return 0


def cmd_doctor(args: list[str]) -> int:
    """Diagnose Trellis Lite state. Pass --fix to repair common issues.

    Each numbered check is its own `_check_*()` helper below. The orchestrator
    chains them and forwards mutations on `problems`/`warnings` to the final
    summary. Splitting per-check makes it easy to add/remove/reorder a check
    and to test one in isolation later.
    """
    fix = "--fix" in args
    problems: list[str] = []
    warnings: list[str] = []

    print(colored(f"Trellis Lite Doctor (v{__version__})", C_CYAN))
    if fix:
        print(colored("  --fix mode: will repair what it can", C_YELLOW))
    print()

    # 1. .trellis-lite/ present (early-abort if not)
    # init_ok=True so get_repo_root() falls back to cwd when .trellis-lite/ is
    # missing; _check_trellis_present below handles the "missing" report.
    repo_root = get_repo_root(init_ok=True)
    tdir = repo_root / TRELLIS_DIR

    if not _check_trellis_present(tdir, problems):
        return _doctor_finish(problems, warnings)

    # 2. Developer file
    _check_developer_file(tdir, fix, problems, warnings)

    # 3. Required subdirs
    _check_required_subdirs(tdir, fix, warnings)

    # 4. Workspace (returns workspace for downstream checks)
    workspace = _check_workspace_dir(fix, warnings)

    # 5. .current-task pointer
    _check_current_task(tdir, fix, problems)

    # 6. Task integrity
    _check_task_integrity(tdir, problems)

    # 7. Journal numbering (only meaningful when workspace exists)
    if workspace is not None:
        _check_journal_numbering(workspace, warnings)

    # 8. Python version
    _check_python_version(problems)

    # 9. Working tree state (informational)
    _check_working_tree()

    return _doctor_finish(problems, warnings)


def _check_trellis_present(tdir: Path, problems: list[str]) -> bool:
    """Check #1: is .trellis-lite/ present? Returns False to abort doctor early."""
    if not tdir.is_dir():
        print(colored("  ✗", C_RED), f"{TRELLIS_DIR}/ not found")
        problems.append(f"{TRELLIS_DIR}/ missing — run 'init <name>' first")
        return False
    print(colored("  ✓", C_GREEN), f"{TRELLIS_DIR}/ present at {tdir}")
    return True


def _check_developer_file(tdir: Path, fix: bool, problems: list[str], warnings: list[str]) -> None:
    """Check #2: .developer must exist and contain name=..."""
    dev_file = tdir / FILE_DEVELOPER
    if not dev_file.is_file():
        problems.append(f"{FILE_DEVELOPER} missing")
        print(colored("  ✗", C_RED), f"{FILE_DEVELOPER} missing")
        if fix:
            dev_file.write_text("name=developer\n", encoding="utf-8")
            problems.pop()
            print(colored("    ↳", C_DIM), "wrote default developer=developer")
        return
    dev = get_developer()
    if dev:
        print(colored("  ✓", C_GREEN), f"Developer: {dev}")
    else:
        warnings.append(f"{FILE_DEVELOPER} exists but has no name= line")
        print(colored("  ⚠", C_YELLOW), f"{FILE_DEVELOPER} has no name= line")


def _check_required_subdirs(tdir: Path, fix: bool, warnings: list[str]) -> None:
    """Check #3: tasks/, tasks/archive/, spec/ must exist."""
    for sub in [(DIR_TASKS,), (DIR_TASKS, DIR_ARCHIVE), (DIR_SPEC,)]:
        d = tdir.joinpath(*sub)
        if not d.is_dir():
            warnings.append(f"{'/'.join(sub)}/ missing")
            # Remember index so we can pop this exact entry after fix, even if
            # multiple subdirs are missing (pop() removes only the last).
            idx = len(warnings) - 1
            print(colored("  ⚠", C_YELLOW), f"{'/'.join(sub)}/ missing")
            if fix:
                # _safe_mkdir unlinks a stray file at the same path so
                # `doctor --fix` recovers from `.trellis-lite/tasks` etc.
                # being a file (e.g. partial-install / stray touch). Plain
                # `mkdir(exist_ok=True)` would raise FileExistsError on
                # Python 3.12+.
                _safe_mkdir(d)
                print(colored("    ↳", C_DIM), f"created {d}")
                warnings.pop(idx)
        else:
            print(colored("  ✓", C_GREEN), f"{'/'.join(sub)}/ present")


def _check_workspace_dir(fix: bool, warnings: list[str]) -> Path | None:
    """Check #4: workspace/<dev>/ exists; auto-create journal-1.md if missing."""
    workspace = get_workspace_dir()
    dev = get_developer()
    if workspace is None:
        warnings.append("workspace/ not present (no developer or developer dir missing)")
        print(colored("  ⚠", C_YELLOW), "workspace/ missing")
        return None
    if not workspace.is_dir():
        warnings.append(f"workspace/{dev} missing")
        print(colored("  ⚠", C_YELLOW), f"workspace/{dev} missing")
        if fix:
            # _safe_mkdir unlinks a stray file at this workspace path so
            # `doctor --fix` recovers when the workspace path is a regular
            # file (e.g. stray touch, partial git sync of a half-initialised
            # state). Previously `mkdir(exist_ok=True)` raised FileExistsError
            # on Python 3.12+ and surfaced as a raw traceback — defeating
            # the repair tool that F44's cmd_session error message points at.
            _safe_mkdir(workspace)
            print(colored("    ↳", C_DIM), f"created {workspace}")
            warnings.pop()
    # Check journal exists (only meaningful now that workspace may have been created)
    if workspace.is_dir():
        journals = list_journals(workspace)
        if not journals:
            warnings.append("no journal files")
            print(colored("  ⚠", C_YELLOW), "no journal files")
            if fix:
                # Single source of truth for journal creation: defer to
                # rotate_if_full so header text/format stays consistent.
                rotate_if_full(workspace, list_journals(workspace))
                print(colored("    ↳", C_DIM), "created journal-1.md")
                warnings.pop()
        else:
            print(colored("  ✓", C_GREEN), f"workspace/{dev}/ has {len(journals)} journal(s)")
    return workspace


def _check_current_task(tdir: Path, fix: bool, problems: list[str]) -> None:
    """Check #5: .current-task pointer must resolve to a real task dir.

    F55: also flag corrupted task.json (was previously `✓ Active task: <name>
    (?)` which falsely implied health). `task start` / `task finish` /
    `task cancel` all refuse on corrupted metadata (F44/F47/F48/F52), so
    doctor must surface this as a Problem, not a green check. We do NOT
    auto-clear the pointer in --fix mode here because the right path is
    either manual repair or explicit `task delete --force <name>` — the
    user should consciously decide which.
    """
    current = get_current_task()
    if not current:
        print(colored("  ·", C_DIM), "No active task (informational)")
        return
    ct_path = tdir.parent / current
    if not ct_path.is_dir():
        problems.append(f".current-task points to missing dir: {current}")
        print(colored("  ✗", C_RED), f".current-task points to missing: {current}")
        if fix:
            clear_current_task()
            # After successful repair, drop the problem from the list so the
            # final summary doesn't report a fixed issue.
            problems.pop()
            print(colored("    ↳", C_DIM), "cleared stale .current-task pointer")
        return
    # F55: read_json_strict so corrupted metadata surfaces as Problem.
    # Previously `read_json` returned `{}` for corrupted input → status="?"
    # → printed `✓` (green check) — inconsistent with the F44/F47/F48/F52
    # refusal behaviour in `task` commands.
    data = read_json_strict(ct_path / FILE_TASK_JSON)
    if data is None:
        problems.append(
            f".current-task points to corrupted task: {ct_path.name}"
        )
        # Icon matches problem-level severity: this drives doctor's exit code
        # to 1 (problems → `✗ Found N problem(s)` in _doctor_finish), so the
        # inline marker must be `✗` + C_RED like the other problem branches
        # (missing .current-task target at line 1469, orphan/corrupted in
        # _check_task_integrity). Using `⚠`/C_YELLOW here mislabelled a
        # blocking problem as a non-blocking warning.
        print(colored("  ✗", C_RED),
              f"Active task '{ct_path.name}' has corrupted task.json — "
              f"`task start/finish/cancel` will refuse; run 'task delete "
              f"--force {ct_path.name}' or repair task.json manually.")
        return
    status = data.get("status", "?")
    print(colored("  ✓", C_GREEN), f"Active task: {ct_path.name} ({status})")


def _check_task_integrity(tdir: Path, problems: list[str]) -> None:
    """Check #6: every task dir under tasks/ must have task.json.

    F54: also recurses into tasks/archive/<YYYY-MM>/<name>/ to flag
    orphan or corrupted archived tasks. Previously only tasks/ top-level
    was scanned, so a corrupted task.json inside tasks/archive/2026-MM/
    was invisible to doctor — `task list --all` reported `[?]` but
    doctor gave no actionable signal. The fix uses `read_json_strict` so
    presence alone isn't enough: a file that exists but cannot be
    parsed (half-synced git checkout, manual edit gone wrong, partial
    write) is also surfaced as a Problem.
    """
    tasks_dir = tdir / DIR_TASKS
    if not tasks_dir.is_dir():
        return

    def _check_one(t: Path, scope: str) -> None:
        """Check a single task dir; append problems if missing or corrupt."""
        task_json = t / FILE_TASK_JSON
        if not task_json.is_file():
            problems.append(
                f"orphan task dir (no {FILE_TASK_JSON}): {scope}{t.name}"
            )
            print(colored("  ✗", C_RED),
                  f"orphan: {scope}{t.name} (no task.json)")
            return
        # F54: present-but-unreadable is also a Problem. Catches partial
        # writes / manual edits / partial git checkouts where the file
        # exists but read_json_strict returns None.
        if read_json_strict(task_json) is None:
            problems.append(
                f"corrupted task.json: {scope}{t.name}"
            )
            print(colored("  ✗", C_RED),
                  f"corrupted task.json: {scope}{t.name}")

    for t in tasks_dir.iterdir():
        if not t.is_dir():
            continue
        if t.name == DIR_ARCHIVE:
            # archive/ is a year-month container — recurse one level.
            for month_dir in t.iterdir():
                if not month_dir.is_dir():
                    continue
                scope = f"{DIR_ARCHIVE}/{month_dir.name}/"
                for task in month_dir.iterdir():
                    if task.is_dir():
                        _check_one(task, scope)
            continue
        _check_one(t, "")


def _check_journal_numbering(workspace: Path, warnings: list[str]) -> None:
    """Check #7: journal-N.md numbering should start at 1 and have no internal gaps."""
    journals = list_journals(workspace)
    if not journals:
        return
    nums = [n for n, _ in journals]
    if nums[0] != 1:
        warnings.append(f"journal numbering starts at {nums[0]} (expected 1)")
        print(colored("  ⚠", C_YELLOW), f"journals start at {nums[0]} (gaps before)")
    # Internal gaps (e.g. 1, 3, 5) suggest manual deletes / partial rotations.
    for i in range(len(nums) - 1):
        if nums[i + 1] != nums[i] + 1:
            msg = f"journal numbering gap: {nums[i]} → {nums[i + 1]}"
            warnings.append(msg)
            print(colored("  ⚠", C_YELLOW), msg)


def _check_python_version(problems: list[str]) -> None:
    """Check #8: Python 3.9+ required."""
    if sys.version_info < (3, 9):
        problems.append(f"Python {sys.version_info[0]}.{sys.version_info[1]} is below 3.9")
        print(colored("  ✗", C_RED), f"Python {sys.version_info[0]}.{sys.version_info[1]} < 3.9")
    else:
        print(colored("  ✓", C_GREEN), f"Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}")


def _check_working_tree() -> None:
    """Check #9: working tree dirty file count (informational only)."""
    dirty = git_status_porcelain()
    if dirty:
        print(colored("  ·", C_DIM), f"{len(dirty.splitlines())} dirty file(s) in working tree (informational)")


def _doctor_finish(problems: list[str], warnings: list[str]) -> int:
    """Print summary line and return exit code."""
    print()
    if problems:
        print(colored(f"✗ Found {len(problems)} problem(s):", C_RED))
        for p in problems:
            print(f"  - {p}")
        print()
        print("Run with --fix to auto-repair common issues, or fix manually.")
        return 1
    if warnings:
        print(colored(f"⚠ {len(warnings)} warning(s):", C_YELLOW))
        for w in warnings:
            print(f"  - {w}")
        print()
        print("Run with --fix to auto-repair where safe.")
        return 0
    print(colored("✓ All checks passed.", C_GREEN))
    return 0


def main() -> int:
    """Parse argv and dispatch to the selected command."""
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    cmd = args[0]
    rest = args[1:]

    dispatch = {
        "init": cmd_init,
        "task": cmd_task,
        "session": cmd_session,
        "context": cmd_context,
        "specs": cmd_specs,
        "version": cmd_version,
        "doctor": cmd_doctor,
    }

    handler = dispatch.get(cmd)
    if handler is None:
        print(colored(f"Unknown command: {cmd}", C_RED))
        print_help()
        return 1

    return handler(rest)


if __name__ == "__main__":
    sys.exit(main())
