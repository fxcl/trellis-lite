---
description: Create a new Trellis task and draft its PRD ($ARGUMENTS = task title)
allowed-tools: Bash(python3 .trellis-lite/scripts/trellis.py:*), Read, Write, Glob, Grep
---

Task title: $ARGUMENTS

Create the task:

```bash
python3 .trellis-lite/scripts/trellis.py task create "<title from $ARGUMENTS>" --slug <short-name>
```

Then draft the PRD following `.trellis-lite/skills/brainstorm.md`:

1. Explore the codebase for answers before asking the user anything.
2. Write `<task-dir>/prd.md` with Goal / Requirements / Acceptance Criteria / Notes.
3. Ask the user **one question at a time** — only about product intent, scope, or risk decisions that the codebase cannot answer.
4. Update `prd.md` after each answer; repeat until no user-owned decisions remain.
5. Present the final PRD summary and ask for confirmation to run `/trellis-start`.

If $ARGUMENTS is empty, ask the user what the task should achieve before creating anything.
