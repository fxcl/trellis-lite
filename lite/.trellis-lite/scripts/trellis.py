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
    python3 trellis.py task list
    python3 trellis.py session --title "Title" --summary "Summary" [--commit <hash>]
    python3 trellis.py context
    python3 trellis.py specs
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
MAX_JOURNAL_LINES = 2000

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

def get_repo_root() -> Path:
    """Find nearest ancestor containing .trellis-lite/."""
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / TRELLIS_DIR).is_dir():
            return current
        current = current.parent
    return Path.cwd().resolve()


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
        import subprocess
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def git_log_oneline(n: int = 5) -> str:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def git_branch() -> str:
    try:
        import subprocess
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
    tasks_dir = get_tasks_dir()
    # Try direct: tasks/<input>
    candidate = tasks_dir / task_input
    if candidate.is_dir():
        return candidate
    # Try with date prefix: tasks/MM-DD-<input>
    matches = list(tasks_dir.glob(f"*-{task_input}"))
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
    if not args:
        print(colored("Usage: trellis.py init <your-name>", C_RED))
        return 1

    name = args[0]

    # Validate name: must be filesystem-safe
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        print(colored("Error: name must contain only letters, digits, hyphens, or underscores", C_RED))
        return 1

    tdir = get_trellis_dir()

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
    if not args:
        print(colored("Usage: trellis.py task <create|start|current|finish|archive|list>", C_RED))
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
        print(colored(f"Unknown task subcommand: {sub}", C_RED))
        return 1


def _task_create(args: list[str]) -> int:
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

    title = " ".join(title_parts).strip('"\'')
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

    # Auto-set as current task
    rel = f"{TRELLIS_DIR}/{DIR_TASKS}/{dir_name}"
    set_current_task(rel)

    print(colored(f"✓ Task created: {dir_name}", C_GREEN))
    print(f"  Path: {task_dir}")
    print(f"  Status: planning")
    print(f"  Active: yes (auto-set)")
    return 0


def _task_start(args: list[str]) -> int:
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
    current = get_current_task()
    if current is None:
        print(colored("No active task to finish.", C_YELLOW))
        return 0

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

    import shutil
    shutil.move(str(task_dir), str(dest))

    # Clear current if it was this task (exact match on directory name)
    current = get_current_task()
    if current and Path(current).name == task_dir.name:
        clear_current_task()

    print(colored(f"✓ Task archived: {task_dir.name}", C_GREEN))
    print(f"  → {dest}")
    return 0


def _task_cancel(args: list[str]) -> int:
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
    tasks_dir = get_tasks_dir()
    if not tasks_dir.is_dir():
        print(colored("No tasks directory.", C_DIM))
        return 0

    tasks = sorted(tasks_dir.iterdir())
    tasks = [t for t in tasks if t.is_dir() and t.name != DIR_ARCHIVE]

    if not tasks:
        print(colored("No active tasks.", C_DIM))
        return 0

    current = get_current_task()
    print(colored("Active Tasks:", C_CYAN))
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


# ============================================================================
# Commands: session
# ============================================================================

def cmd_session(args: list[str]) -> int:
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

    print(colored("=" * 60, C_DIM))
    return 0


# ============================================================================
# Commands: specs (list available spec files)
# ============================================================================

def cmd_specs(args: list[str]) -> int:
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
# Spec template
# ============================================================================

SPEC_TEMPLATE = """# Coding Specs

Write your project's coding conventions and patterns here. The AI reads these
before implementing any code.

## How to structure specs

Create one `.md` file per topic. Keep them short and actionable.

### Example: `conventions.md`

```markdown
# Conventions

- Use 2-space indentation
- Prefer named exports over default exports
- Error messages must include context for debugging
- All public functions need JSDoc comments
```

### Example: `api-patterns.md`

```markdown
# API Patterns

- REST endpoints use kebab-case: /api/user-profiles
- All responses wrapped in { data, error, meta }
- Pagination via cursor, not offset
- Rate limit: 100 req/min per token
```

## When to update specs

- You discover a new pattern worth repeating
- A bug fix reveals a convention that should be enforced
- You make a technical decision that affects future code
"""


# ============================================================================
# Main entry
# ============================================================================

def print_help() -> None:
    print(colored("Trellis Lite", C_CYAN))
    print(colored("Single-file task & session manager for agile solo developers.\n", C_DIM))
    print("Commands:")
    print(f"  {colored('init', C_GREEN)} <name>                    Initialize developer identity")
    print(f"  {colored('task create', C_GREEN)} \"<title>\" [--slug <s>]  Create a new task")
    print(f"  {colored('task start', C_GREEN)} <name>               Activate a task (status → in_progress)")
    print(f"  {colored('task current', C_GREEN)}                   Show active task")
    print(f"  {colored('task finish', C_GREEN)}                    Deactivate current task")
    print(f"  {colored('task archive', C_GREEN)} <name>            Archive a completed task")
    print(f"  {colored('task cancel', C_GREEN)} <name>            Cancel an abandoned task (keeps directory)")
    print(f"  {colored('task list', C_GREEN)}                      List all active tasks")
    print(f"  {colored('session', C_GREEN)} --title \"T\" --summary \"S\"  Record a session journal entry")
    print(f"  {colored('context', C_GREEN)}                       Print full session context")
    print(f"  {colored('specs', C_GREEN)}                         List available spec files")
    print(f"  {colored('help', C_GREEN)}                          Show this help")
    print(f"\nWorkflow: {colored('init', C_DIM)} → {colored('task create', C_DIM)} → {colored('task start', C_DIM)} → code → {colored('task archive', C_DIM)} → {colored('session', C_DIM)}")


def main() -> int:
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
    }

    handler = dispatch.get(cmd)
    if handler is None:
        print(colored(f"Unknown command: {cmd}", C_RED))
        print_help()
        return 1

    return handler(rest)


if __name__ == "__main__":
    sys.exit(main())
