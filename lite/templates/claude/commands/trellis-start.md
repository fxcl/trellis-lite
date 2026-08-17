---
description: Start the active Trellis task (planning → in_progress) and load coding specs
allowed-tools: Bash(python3 .trellis-lite/scripts/trellis.py:*), Read
---

Start the active task:

```bash
python3 .trellis-lite/scripts/trellis.py task start
```

Then enter the CODE phase properly:

1. Run `python3 .trellis-lite/scripts/trellis.py specs` and read every spec file that applies to the code you will touch.
2. Read the task's `prd.md` (and `design.md` if present) from the path reported by `task start`.
3. Follow `.trellis-lite/skills/before-dev.md`: understand existing patterns in the files you will edit before writing code.
4. Implement the PRD. Do not git commit — ask the user first.

If the command refuses because another task is active, report the conflict instead of forcing it.
