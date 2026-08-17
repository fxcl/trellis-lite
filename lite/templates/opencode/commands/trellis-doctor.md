---
description: Run the Trellis health check and interpret problems/warnings
---

Run the health check:

```bash
python3 .trellis-lite/scripts/trellis.py doctor
```

Interpret the output:

- **Problems** (exit 1): broken state — stale `.current-task` pointer, missing directories, invalid status values. Doctor auto-fixes what it safely can; anything it cannot fix, propose the manual fix to the user before touching state yourself.
- **Warnings**: non-blocking health signals (planning-status task active, unchecked PRD items, done task without session). Summarize them and let the user decide.

Do not modify `.trellis-lite/` state files directly — use trellis.py commands.
