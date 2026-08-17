---
description: Archive the active (done) Trellis task into tasks/archive/
allowed-tools: Bash(python3 .trellis-lite/scripts/trellis.py:*), Read
---

Archive the active task:

```bash
python3 .trellis-lite/scripts/trellis.py task archive
```

Preconditions to verify first (the command enforces them — if it refuses, report why):

1. The task status is `done` (run `/trellis-finish` first if not).
2. A session was recorded for the task.

After archiving, report the archive path and confirm no task is active. Suggest `/trellis-new <title>` for the next piece of work.
