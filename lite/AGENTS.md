# Trellis Lite — AI Agent Instructions

This project uses **Trellis Lite**, a lightweight engineering workflow for solo developers.

## What You Need to Know

### Workflow File

Read `.trellis-lite/workflow.md` for the full 3-phase workflow (PLAN → CODE → WRAP).

### Task Manager

All task operations go through one script:

```bash
python3 .trellis-lite/scripts/trellis.py <command>
```

Key commands: `init`, `task create/start/current/finish/archive/cancel/list/delete`, `session`, `context`, `specs`, `doctor`, `version`.

### Specs

Coding conventions live in `.trellis-lite/spec/*.md`. **Always read relevant specs before writing code.**

## How to Handle a User Request

1. **Check current state**:
   ```bash
   python3 .trellis-lite/scripts/trellis.py context
   ```

2. **Triage the request**:
   - Trivial (< 5 min)? Just do it.
   - Needs planning? Create a task and follow the workflow.

3. **Follow the 3-phase loop**:
   - **PLAN**: Create task → write PRD → get user approval → `task start`
   - **CODE**: Read specs → implement → quality check
   - **WRAP**: Update specs → commit → archive task → record session

## Rules

- **Plan before code**. Even a 3-bullet PRD is better than guessing.
- **Read specs first**. Don't recall from memory; read the files.
- **One task at a time**. Finish before starting the next.
- **No auto-commit**. Always ask the user before `git commit`.
- **Capture learnings**. If you discovered something, write it to specs.
- **Be efficient**. Don't over-ceremony small tasks. Agility means speed.

## Sub-Agent Usage

For larger tasks, you may dispatch sub-agents (if your AI tool supports it):

- **Implement**: Spawn a general-purpose agent. Tell it to read `prd.md` + specs, implement, run lint/typecheck.
- **Review**: Spawn a code-review agent. Tell it to review `git diff` against specs + PRD.

Always start sub-agent prompts with: `Active task: <path from 'trellis.py task current'>`

> Platform-specific sub-agent guidance is in the bridge file (e.g. `CLAUDE.md` for Claude Code).

## Quick Links

- Workflow: `.trellis-lite/workflow.md`
- Specs: `.trellis-lite/spec/`
- Tasks: `.trellis-lite/tasks/`
- Journal: `.trellis-lite/workspace/<your-name>/`
