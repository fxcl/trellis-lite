# Trellis Lite — Development Workflow

> For agile solo developers using Qoder. Simple. Efficient. No ceremony.

---

## Core Principles

1. **Plan before code** — write a PRD, even if it's 3 bullets
2. **Specs are injected, not remembered** — conventions live in `.trellis-lite/spec/`
3. **One task at a time** — finish what you start
4. **Capture learnings** — update specs after each task

---

## System Overview

### Developer Identity

```bash
python3 .trellis-lite/scripts/trellis.py init <your-name>
```

### Spec System

`.trellis-lite/spec/` holds your coding conventions as plain `.md` files. The AI reads them before writing code.

```bash
python3 .trellis-lite/scripts/trellis.py specs   # list specs
```

### Task System

Each task gets its own directory under `.trellis-lite/tasks/MM-DD-name/`.

```bash
python3 .trellis-lite/scripts/trellis.py task create "<title>" --slug <name>
python3 .trellis-lite/scripts/trellis.py task start <name>
python3 .trellis-lite/scripts/trellis.py task current
python3 .trellis-lite/scripts/trellis.py task finish
python3 .trellis-lite/scripts/trellis.py task archive <name>
python3 .trellis-lite/scripts/trellis.py task cancel <name>
python3 .trellis-lite/scripts/trellis.py task list
```

### Workspace Journal

Session logs are recorded automatically for cross-session memory.

```bash
python3 .trellis-lite/scripts/trellis.py session --title "Title" --summary "Summary"
```

---

## The 3-Phase Loop

```
Phase 1: PLAN    → clarify requirements, write PRD, then start
Phase 2: CODE    → implement with specs, then check quality
Phase 3: WRAP    → update specs, commit, record session
```

---

### Phase 1: PLAN

Goal: know what to build before writing a single line of code.

#### 1.1 Triage

- **Small task** (typo, rename, one-file fix): skip task creation, just do it.
- **Medium task** (new function, bug fix, small feature): create task, PRD-only.
- **Complex task** (new module, refactor, cross-file feature): create task with PRD + design notes.

#### 1.2 Create Task

```bash
python3 .trellis-lite/scripts/trellis.py task create "<short title>" --slug <name>
```

This creates the task directory with a starter `prd.md`. The task is auto-set as active.

#### 1.3 Write PRD

> **Read `.trellis-lite/skills/brainstorm.md` first** — it defines how to discover
> requirements (explore the codebase before asking; one question at a time).

Fill in `prd.md`:
- **Goal** — one sentence
- **Requirements** — bullet list
- **Acceptance Criteria** — verifiable checklist

For complex tasks, also write:
- **Design notes** (in `prd.md` or separate `design.md`) — boundaries, data flow, tradeoffs

#### 1.4 Review & Start

Review the PRD with the user. After confirmation:

```bash
python3 .trellis-lite/scripts/trellis.py task start <name>
```

This flips status to `in_progress`. Implementation can now begin.

---

### Phase 2: CODE

Goal: turn the PRD into working code that passes checks.

#### 2.1 Load Specs

> **Read `.trellis-lite/skills/before-dev.md` first** — mandatory pre-coding checklist.

Before writing code, read relevant specs:

```bash
python3 .trellis-lite/scripts/trellis.py specs
cat .trellis-lite/spec/<relevant-file>.md
```

#### 2.2 Implement

Write code following the PRD and specs. Options:

**Direct implementation** (small/medium tasks): write code in the main session.

**Sub-agent dispatch** (larger tasks): spawn a `GeneralPurpose` agent:
- Agent prompt MUST start with `Active task: <path from 'trellis.py task current'>`
- Tell the agent to read `prd.md` and relevant specs first
- Agent should run lint/typecheck after implementing

#### 2.3 Quality Check

> **Read `.trellis-lite/skills/check.md`** — it defines the full verification procedure
> and the report format.

After implementation, verify quality:

**Self-check** (small tasks): run lint, typecheck, tests manually.

**Sub-agent check** (larger tasks): spawn a `CodeReview` agent:
- Tell it to review `git diff` against specs and `prd.md`
- It should auto-fix mechanical issues and report findings

```bash
git status --porcelain
# Run your project's lint/typecheck/test commands
```

Fix any issues, re-check until green.

---

### Phase 3: WRAP

Goal: capture learnings, commit clean work, record the session.

#### 3.0 Finish (optional)

If you've completed implementation but want to commit and archive separately:

```bash
python3 .trellis-lite/scripts/trellis.py task finish
```

This marks the task status as `done` and clears the active pointer. You can skip this and go straight to archive if you prefer.

#### 3.1 Update Specs

> **Read `.trellis-lite/skills/update-spec.md`** — how to write executable specs.

Did you learn something worth keeping? Update `.trellis-lite/spec/`:
- New pattern or convention discovered
- Pitfall or gotcha hit during implementation
- Technical decision made

Even if "nothing to update", consciously decide.

#### 3.2 Commit

**Ask the user before committing — never auto-commit.** After confirmation:

```bash
git status --porcelain
git log --oneline -5   # learn commit style
git add <files>
git commit -m "<message>"
```

Group changes into logical commits. Follow existing commit conventions.

#### 3.3 Archive & Record

```bash
python3 .trellis-lite/scripts/trellis.py task archive <name>
python3 .trellis-lite/scripts/trellis.py session --title "Title" --summary "Summary" --commit <hash>
```

---

## Quick Reference

| What | Command |
|------|---------|
| See current state | `python3 .trellis-lite/scripts/trellis.py context` |
| Start a task | `task create` → write PRD → `task start` |
| Resume a task | `task current` → check PRD → continue |
| Mark done | `task finish` (status → done, clears active pointer) |
| Finish a task | commit → `task finish` → `task archive` → `session` |
| Abandon a task | `task cancel <name>` (status → cancelled, directory kept) |
| List specs | `specs` |

## Rules of Thumb

1. If the task takes < 5 minutes, just do it — no task creation needed
2. PRD is always the source of truth — update it when requirements change
3. Specs are for things you'll forget — write them when you learn something
4. One active task at a time — finish before starting the next
5. Journal entries are cheap — record every meaningful session
6. **No parallel trellis commands** — `.current-task` is an unsynchronized file pointer. Run commands sequentially; running multiple instances in parallel can corrupt the active pointer.

---

## Further Reading

These docs expand on the workflow above. Agents should read the ones relevant to their phase.

| Doc | What it covers |
|-----|----------------|
| [best-practices.md](docs/best-practices.md) | PRD quality, spec writing, state machine, exit codes, doctor semantics, install lifecycle |
| [workflow-checklist.md](docs/workflow-checklist.md) | Per-session AI checklist (section 6), copy-paste task template (section 7) |
| [design.md](docs/design.md) | Design principles, five tradeoffs, why Lite is shaped this way |
| [platforms.md](docs/platforms.md) | Platform support matrix (Qoder / OpenCode / Claude / Cline), install logic, sub-agent differences |
| [trellis-cli.md](docs/trellis-cli.md) | Complete `trellis.py` command reference with scenarios |
| [usage-guide.md](docs/usage-guide.md) | Full workflow walkthrough from install to archive |
| [installation-guide.md](docs/installation-guide.md) | Install / uninstall manual, macOS bash 4+ gate, troubleshooting |
| [exit-codes.md](docs/exit-codes.md) | POSIX exit code convention (0/1), when each applies, CI/pre-commit usage |
| [architecture-review.md](docs/architecture-review.md) | Debt log — past design decisions and the reasoning behind them |
