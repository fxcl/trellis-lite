---
description: Finish the active Trellis task (in_progress → done) and guide WRAP completeness
---

Finish the active task:

```bash
python3 .trellis-lite/scripts/trellis.py task finish
```

Before declaring WRAP complete, verify:

1. All PRD acceptance criteria are checked off (or deferred with a stated reason).
2. Doctor passes: `python3 .trellis-lite/scripts/trellis.py doctor`.
3. A session is recorded:
   ```bash
   python3 .trellis-lite/scripts/trellis.py session --title "<short title>" --summary "<what was done>" --commit <hash>
   ```
4. Specs were updated if this task produced a reusable lesson (edit files in `.trellis-lite/spec/`).

Then ask the user whether to commit (never auto-commit) and suggest `/trellis-archive` after the commit.
