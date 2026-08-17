---
description: List all active Trellis tasks with status and health markers
---

List the tasks:

```bash
python3 .trellis-lite/scripts/trellis.py task list
```

In your reply:

1. Reproduce the list as a table (task, status, health markers, title).
2. Highlight the active task (marked with →) and any ⚠ health warnings.
3. Recommend next steps per task: `planning` → finish PRD + `/trellis-start`; `in_progress` → continue CODE; `done` with ⚠ → `/trellis-finish` record-keeping; stale/cancelled entries → suggest cleanup.
