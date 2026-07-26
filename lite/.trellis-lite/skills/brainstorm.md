# Brainstorm — Requirements Discovery

Use during Phase 1 to turn a user request into clear requirements.

## Core Rule

**If a question can be answered by exploring the codebase, explore the codebase instead.**

Before asking the user anything, check:
- Code, tests, configs
- README, docs, existing specs
- Related task history

Only ask about product intent, preferences, scope, and risk decisions.

## Flow

1. **Create task** (if not done):
   ```bash
   python3 .trellis-lite/scripts/trellis.py task create "<title>" --slug <name>
   ```

2. **Capture initial understanding** in `prd.md`:
   - Goal (one sentence)
   - Known requirements
   - Acceptance criteria

3. **Explore the codebase** for answers before asking.

4. **Ask one question at a time** — the single highest-value question. Include your recommendation and trade-off. Then stop.

5. **Update `prd.md`** after each answer.

6. **Repeat** until no user-owned decisions remain.

7. **Present final summary** — concise PRD review. Ask for confirmation to start.

## PRD Structure

```markdown
# <Title>

## Goal
<One sentence>

## Requirements
- <bullet>
- <bullet>

## Acceptance Criteria
- [ ] <verifiable condition>
- [ ] <verifiable condition>

## Notes
<context, constraints, references>
```

## When to Add Design Notes

For complex tasks (new module, cross-file refactor, API change), add a `## Design` section or separate `design.md`:
- Module boundaries
- Data flow
- Tradeoffs considered
- Compatibility concerns

## Stop Conditions

- User confirms PRD → proceed to `task start`
- User changes scope → update PRD, re-ask
- User says "just do it" → start implementation with current PRD
