---
description: Cancel the active Trellis task ($ARGUMENTS = optional task name)
---

Cancel a task:

```bash
python3 .trellis-lite/scripts/trellis.py task cancel $ARGUMENTS
```

Notes:

- With no argument this cancels the **active** task; with a name it cancels that task.
- Cancelling sets status to `cancelled` but **keeps the directory** — confirm with the user whether to also delete it manually if they want it gone.
- Ask for confirmation before running if the task is `in_progress` (work may be lost).

If $ARGUMENTS is empty and no task is active, report that instead of guessing a name.
