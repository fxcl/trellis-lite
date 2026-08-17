---
description: WRAP-phase quality check — review changes against specs and PRD, self-fix, verify
---

Run the WRAP-phase quality gate:

```bash
python3 .trellis-lite/scripts/trellis.py doctor
```

If doctor reports problems (exit 1), fix them before continuing. Warnings are non-blocking but must be reported.

Then follow `.trellis-lite/skills/check.md` steps 1–6:

1. Get the change set: `git status` + `git diff` (staged and unstaged).
2. Read the active task's `prd.md` and relevant specs.
3. Review every changed file against specs and PRD acceptance criteria.
4. Run the project's checks (lint / typecheck / tests) if they exist.
5. Self-fix mechanical issues directly; report design questions instead of guessing.
6. Report: files reviewed, issues fixed, issues open, verification results, PRD acceptance criteria status.

No git commit — committing is the user's decision.
