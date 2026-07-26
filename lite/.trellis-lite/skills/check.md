# Check — Quality Verification

Use after implementation to verify code quality before committing.

## Step 1: Identify Changes

```bash
git status --porcelain
```

## Step 2: Read Context

Read in order:
1. Active task's `prd.md` — requirements and acceptance criteria
2. Relevant specs from `.trellis-lite/spec/`:
   ```bash
   python3 .trellis-lite/scripts/trellis.py specs
   cat .trellis-lite/spec/<relevant>.md
   ```

## Step 3: Review Against Specs

For each changed file, check:
- **Spec compliance** — does the code follow conventions in specs?
- **PRD compliance** — does it satisfy the acceptance criteria?
- **Pattern consistency** — does it match existing code style?
- **Error handling** — are edge cases covered?
- **No scope creep** — only what the PRD asks for

## Step 4: Run Project Checks

```bash
# Run whatever your project uses:
npm run lint && npm run typecheck && npm test
# or: make check
# or: cargo test
# etc.
```

## Step 5: Fix Issues

- **Mechanical** (lint, missing type, wrong import) → fix directly
- **Design issue** → report to user, don't silently rewrite

## Step 6: Report

```
## Check Complete

### Files Reviewed
- <path>

### Issues Fixed
1. `<file>:<line>` — <what> → <fix>

### Issues Open
- `<file>:<line>` — <issue> — <why deferred>

### Verification
- Lint: pass/fail
- TypeCheck: pass/fail
- Tests: pass/fail
```

## Sub-Agent Mode

When dispatched as a `CodeReview` agent:
- Start with `Active task: <path>`
- Read `prd.md` and specs
- Review `git diff`
- Self-fix mechanical issues
- Report findings
- Do NOT commit
