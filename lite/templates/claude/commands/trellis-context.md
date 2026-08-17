---
description: Show current Trellis session context (active task, status, recent commits)
allowed-tools: Bash(python3 .trellis-lite/scripts/trellis.py:*)
---

Run the Trellis context command:

```bash
python3 .trellis-lite/scripts/trellis.py context
```

Then, in your reply:

1. Summarize the active task (name, status, artifacts) — or note that no task is active.
2. Surface any health warnings it printed (missing PRD, unchecked items, no session recorded).
3. Recommend the next workflow step:
   - No task → suggest `/trellis-new <title>` for anything non-trivial
   - Task in `planning` → suggest finishing the PRD, then `/trellis-start`
   - Task in `in_progress` → suggest continuing CODE, or `/trellis-check` when implementation is done
   - Task in `done` → suggest `/trellis-finish` record-keeping or `/trellis-archive`
