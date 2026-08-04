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
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def resolve_task_dir(task_input: str) -> Path | None:
    """Resolve task name to absolute directory path."""
    # Reject path separators and traversal (e.g. "../spec")
    if "/" in task_input or "\\" in task_input or ".." in task_input:
        print(colored(f"Invalid task name: {task_input}", C_RED))
        return None
    # Reject the archive container itself (bare name, case-insensitive)
    if task_input.lower() == DIR_ARCHIVE:
        print(colored(f"Invalid task name: {task_input}", C_RED))
        return None
    tasks_dir = get_tasks_dir()
    # Try direct: tasks/<input>
    candidate = tasks_dir / task_input
    if candidate.is_dir():
        return candidate
    # Try with date prefix: tasks/MM-DD-<input>
    # Literal endswith match (no glob semantics) so user input is matched exactly
    matches = []
    for t in tasks_dir.iterdir():
        if t.is_dir() and t.name.endswith(f"-{task_input}"):
            matches.append(t)
    matches.sort()
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(colored(f"Ambiguous: multiple matches for '{task_input}':", C_YELLOW))
        for m in matches:
            print(f"  {m.name}")
        return None
    return None


# ============================================================================
# Commands: init
# ============================================================================

def cmd_init(args: list[str]) -> int:
    """Initialize developer identity + scaffold .trellis-lite/ at repo root."""
    if not args:
        print(colored("Usage: trellis.py init <your-name>", C_RED))
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

    # Create first journal
    journal = workspace / f"{JOURNAL_PREFIX}1.md"
    if not journal.exists():
        journal.write_text(f"# Journal 1\n\n", encoding="utf-8")

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
        print(colored("Usage: trellis.py task <create|start|current|finish|archive|cancel|list|delete>", C_RED))
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
    """Create a new task directory with prd.md, set as current, warn if active exists."""
    if not args:
        print(colored('Usage: trellis.py task create "<title>" [--slug <name>]', C_RED))
        return 1

    # Parse: title + optional --slug
    slug = None
    title_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--slug" and i + 1 < len(args):
            slug = args[i + 1]
            i += 2
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

    # Warn if another task is already active (one task at a time)
    existing = get_current_task()
    if existing:
        print(colored(f"Warning: '{existing}' is still the current task — one task at a time", C_YELLOW))

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
        print(colored("Usage: trellis.py task start <name>", C_RED))
        return 1

    task_dir = resolve_task_dir(args[0])
    if task_dir is None:
        print(colored(f"Task not found: {args[0]}", C_RED))
        return 1

    # Warn when other tasks are still in_progress (one task at a time)
    tasks_dir = get_tasks_dir()
    if tasks_dir.is_dir():
        for t in sorted(tasks_dir.iterdir()):
            if not t.is_dir() or t.name in (DIR_ARCHIVE, task_dir.name):
                continue
            if read_json(t / FILE_TASK_JSON).get("status") == "in_progress":
                print(colored(f"Warning: '{t.name}' is still in_progress — one task at a time", C_YELLOW))

    # Update status
    task_json_path = task_dir / FILE_TASK_JSON
    data = read_json(task_json_path)
    if not data:
        print(colored(f"Warning: {task_json_path.name} missing or corrupted", C_YELLOW))
    data["status"] = "in_progress"
    data["started"] = datetime.now().isoformat()
    write_json(task_json_path, data)

    # Set as current
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

    # Show status
    task_dir = get_repo_root() / current
    task_json = read_json(task_dir / FILE_TASK_JSON)
    if task_json:
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

    # Update task status to done
    task_dir = get_repo_root() / current
    task_json_path = task_dir / FILE_TASK_JSON
    data = read_json(task_json_path)
    if data:
        data["status"] = "done"
        data["finished"] = datetime.now().isoformat()
        write_json(task_json_path, data)

    clear_current_task()
    print(colored(f"✓ Task finished: {current}", C_GREEN))
    print(colored("  Run 'task archive <name>' when ready to archive.", C_DIM))
    return 0


def _task_archive(args: list[str]) -> int:
    """Move a task to tasks/archive/YYYY-MM/, with auto-increment on collision."""
    if not args:
        print(colored("Usage: trellis.py task archive <name>", C_RED))
        return 1

    task_dir = resolve_task_dir(args[0])
    if task_dir is None:
        print(colored(f"Task not found: {args[0]}", C_RED))
        return 1

    # Update status
    task_json_path = task_dir / FILE_TASK_JSON
    data = read_json(task_json_path)
    if not data:
        print(colored(f"Warning: {task_json_path.name} missing or corrupted", C_YELLOW))
    data["status"] = "archived"
    data["archived"] = datetime.now().isoformat()
    write_json(task_json_path, data)

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
        print(colored("Usage: trellis.py task cancel <name>", C_RED))
        return 1

    task_dir = resolve_task_dir(args[0])
    if task_dir is None:
        print(colored(f"Task not found: {args[0]}", C_RED))
        return 1

    # Update status
    task_json_path = task_dir / FILE_TASK_JSON
    data = read_json(task_json_path)
    if not data:
        print(colored(f"Warning: {task_json_path.name} missing or corrupted", C_YELLOW))
    data["status"] = "cancelled"
    data["cancelled"] = datetime.now().isoformat()
    write_json(task_json_path, data)

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
        print(colored("Usage: trellis.py task delete <name> [--force]", C_RED))
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
        print(colored("Usage: trellis.py task delete <name> [--force]", C_RED))
        return 1

    task_dir = resolve_task_dir(name_args[0])
    if task_dir is None:
        print(colored(f"Task not found: {name_args[0]}", C_RED))
        return 1

    # Status check: refuse to delete non-cancelled tasks unless --force
    data = read_json(task_dir / FILE_TASK_JSON)
    status = data.get("status", "?")
    if not force and status not in ("cancelled",):
        print(colored(
            f"Refusing to delete task with status '{status}'. "
            f"Cancel it first (task cancel {task_dir.name}) or use --force.",
            C_RED,
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
        print(colored("Usage: trellis.py session --title \"Title\" --summary \"Summary\"", C_RED))
        return 1

    # Validate commit hash format (warn rather than reject — typo only affects journal display)
    if commit and not re.match(r"^[0-9a-f]{4,40}$", commit):
        print(colored(f"Warning: '{commit}' doesn't look like a git SHA (4-40 hex chars)", C_YELLOW))
        commit = None

    workspace = get_workspace_dir()
    if workspace is None:
        print(colored("Developer not initialized. Run: trellis.py init <name>", C_RED))
        return 1

    # Find or create active journal (parse numbers so rotation is safe after manual deletions)
    journals: list[tuple[int, Path]] = []
    for j in workspace.glob(f"{JOURNAL_PREFIX}*.md"):
        m = re.match(rf"{JOURNAL_PREFIX}(\d+)\.md$", j.name)
        if m:
            journals.append((int(m.group(1)), j))
    journals.sort()

    if not journals:
        journal = workspace / f"{JOURNAL_PREFIX}1.md"
        journal.write_text("# Journal 1\n\n", encoding="utf-8")
    else:
        max_num, journal = journals[-1]
        # Check line count, rotate if needed
        lines = journal.read_text(encoding="utf-8").splitlines()
        if len(lines) >= MAX_JOURNAL_LINES:
            num = max_num + 1
            journal = workspace / f"{JOURNAL_PREFIX}{num}.md"
            journal.write_text(f"# Journal {num}\n\n", encoding="utf-8")

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

    # Count total sessions across all journals
    total = 0
    for j in sorted(workspace.glob(f"{JOURNAL_PREFIX}*.md")):
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

    # Current task
    current = get_current_task()
    if current:
        task_dir = repo / current
        data = read_json(task_dir / FILE_TASK_JSON)
        print(f"  Active task: {current}")
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
        journals: list[tuple[int, Path]] = []
        for j in workspace.glob(f"{JOURNAL_PREFIX}*.md"):
            m = re.match(rf"{JOURNAL_PREFIX}(\d+)\.md$", j.name)
            if m:
                journals.append((int(m.group(1)), j))
        if journals:
            journals.sort()
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
    """Diagnose Trellis Lite state. Pass --fix to repair common issues."""
    fix = "--fix" in args
    problems: list[str] = []
    warnings: list[str] = []

    print(colored(f"Trellis Lite Doctor (v{__version__})", C_CYAN))
    if fix:
        print(colored("  --fix mode: will repair what it can", C_YELLOW))
    print()

    # 1. Is .trellis-lite/ present?
    try:
        tdir = get_repo_root(init_ok=True) / TRELLIS_DIR
    except Exception:
        problems.append("Could not determine repo root")
        return _doctor_finish(problems, warnings)

    if not tdir.is_dir():
        print(colored("  ✗", C_RED), f"{TRELLIS_DIR}/ not found")
        problems.append(f"{TRELLIS_DIR}/ missing — run 'init <name>' first")
        return _doctor_finish(problems, warnings)
    print(colored("  ✓", C_GREEN), f"{TRELLIS_DIR}/ present at {tdir}")

    # 2. Developer file
    dev_file = tdir / FILE_DEVELOPER
    if not dev_file.is_file():
        problems.append(f"{FILE_DEVELOPER} missing")
        print(colored("  ✗", C_RED), f"{FILE_DEVELOPER} missing")
        if fix:
            dev_file.write_text("name=developer\n", encoding="utf-8")
            problems.pop()
            print(colored("    ↳", C_DIM), "wrote default developer=developer")
    else:
        dev = get_developer()
        if dev:
            print(colored("  ✓", C_GREEN), f"Developer: {dev}")
        else:
            warnings.append(f"{FILE_DEVELOPER} exists but has no name= line")
            print(colored("  ⚠", C_YELLOW), f"{FILE_DEVELOPER} has no name= line")

    # 3. Required subdirectories
    for sub in [(DIR_TASKS,), (DIR_TASKS, DIR_ARCHIVE), (DIR_SPEC,)]:
        d = tdir.joinpath(*sub)
        if not d.is_dir():
            warnings.append(f"{'/'.join(sub)}/ missing")
            print(colored("  ⚠", C_YELLOW), f"{'/'.join(sub)}/ missing")
            if fix:
                d.mkdir(parents=True, exist_ok=True)
                print(colored("    ↳", C_DIM), f"created {d}")
        else:
            print(colored("  ✓", C_GREEN), f"{'/'.join(sub)}/ present")

    # 4. Workspace
    workspace = get_workspace_dir()
    if workspace is None:
        warnings.append("workspace/ not present (no developer or developer dir missing)")
        print(colored("  ⚠", C_YELLOW), "workspace/ missing")
    elif not workspace.is_dir():
        warnings.append(f"workspace/{dev} missing")
        print(colored("  ⚠", C_YELLOW), f"workspace/{dev} missing")
        if fix:
            workspace.mkdir(parents=True, exist_ok=True)
            print(colored("    ↳", C_DIM), f"created {workspace}")
    else:
        # Check journal exists
        journals = sorted(workspace.glob(f"{JOURNAL_PREFIX}*.md"))
        if not journals:
            warnings.append("no journal files")
            print(colored("  ⚠", C_YELLOW), "no journal files")
            if fix:
                (workspace / f"{JOURNAL_PREFIX}1.md").write_text(
                    "# Journal 1\n\n", encoding="utf-8"
                )
                print(colored("    ↳", C_DIM), "created journal-1.md")
        else:
            print(colored("  ✓", C_GREEN), f"workspace/{dev}/ has {len(journals)} journal(s)")

    # 5. .current-task pointer
    current = get_current_task()
    if current:
        ct_path = tdir.parent / current
        if not ct_path.is_dir():
            problems.append(f".current-task points to missing dir: {current}")
            print(colored("  ✗", C_RED), f".current-task points to missing: {current}")
            if fix:
                clear_current_task()
                # After successful repair, drop the problem from the list
                # so the final summary doesn't report a fixed issue.
                problems.pop()
                print(colored("    ↳", C_DIM), "cleared stale .current-task pointer")
        else:
            data = read_json(ct_path / FILE_TASK_JSON)
            status = data.get("status", "?")
            print(colored("  ✓", C_GREEN), f"Active task: {ct_path.name} ({status})")
    else:
        print(colored("  ·", C_DIM), "No active task (informational)")

    # 6. Task integrity: every task dir must have task.json
    tasks_dir = tdir / DIR_TASKS
    if tasks_dir.is_dir():
        for t in tasks_dir.iterdir():
            if not t.is_dir() or t.name == DIR_ARCHIVE:
                continue
            if not (t / FILE_TASK_JSON).is_file():
                problems.append(f"orphan task dir (no {FILE_TASK_JSON}): {t.name}")
                print(colored("  ✗", C_RED), f"orphan: {t.name} (no task.json)")

        # 7. Journal number gaps
        if workspace and workspace.is_dir():
            nums = []
            for j in workspace.glob(f"{JOURNAL_PREFIX}*.md"):
                m = re.match(rf"{JOURNAL_PREFIX}(\d+)\.md$", j.name)
                if m:
                    nums.append(int(m.group(1)))
            if nums:
                nums.sort()
                if nums[0] != 1:
                    warnings.append(f"journal numbering starts at {nums[0]} (expected 1)")
                    print(colored("  ⚠", C_YELLOW), f"journals start at {nums[0]} (gaps before)")

    # 8. Python version
    if sys.version_info < (3, 9):
        problems.append(f"Python {sys.version_info[0]}.{sys.version_info[1]} is below 3.9")
        print(colored("  ✗", C_RED), f"Python {sys.version_info[0]}.{sys.version_info[1]} < 3.9")
    else:
        print(colored("  ✓", C_GREEN), f"Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}")

    # 9. Working tree state (informational)
    dirty = git_status_porcelain()
    if dirty:
        print(colored("  ·", C_DIM), f"{len(dirty.splitlines())} dirty file(s) in working tree (informational)")

    return _doctor_finish(problems, warnings)


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
