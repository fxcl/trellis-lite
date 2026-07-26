<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Trellis** (14336 symbols, 20870 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Trellis/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Trellis/clusters` | All functional areas |
| `gitnexus://repo/Trellis/processes` | All execution flows |
| `gitnexus://repo/Trellis/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

<!-- trellis-lite:start -->
# Trellis Lite — AI Agent Instructions

This project also uses **Trellis Lite** for lightweight solo-developer workflow.

### Workflow File

Read `.trellis-lite/workflow.md` for the full 3-phase workflow (PLAN → CODE → WRAP).

### Task Manager

All task operations go through one script:

```bash
python3 .trellis-lite/scripts/trellis.py <command>
```

Key commands: `init`, `task create/start/current/finish/archive/list`, `session`, `context`, `specs`.

### Specs

Coding conventions live in `.trellis-lite/spec/*.md`. **Always read relevant specs before writing code.**

### How to Handle a User Request (Lite Mode)

1. **Check current state**: `python3 .trellis-lite/scripts/trellis.py context`
2. **Triage**: Trivial (< 5 min)? Just do it. Needs planning? Create a task.
3. **3-phase loop**: PLAN (task create → PRD → start) → CODE (specs → implement → check) → WRAP (update specs → commit → archive → session)

### Rules

- **Plan before code**. Even a 3-bullet PRD is better than guessing.
- **Read specs first**. Don't recall from memory; read the files.
- **One task at a time**. Finish before starting the next.
- **No auto-commit**. Always ask the user before `git commit`.
- **Capture learnings**. If you discovered something, write it to specs.
- **Be efficient**. Don't over-ceremony small tasks. Agility means speed.

### Sub-Agent Usage

- **Implement**: Use `GeneralPurpose` agent. Tell it to read `prd.md` + specs.
- **Check**: Use `CodeReview` agent. Tell it to review `git diff` against specs + PRD.
- Always start sub-agent prompts with: `Active task: <path>`

### Quick Links

- Workflow: `.trellis-lite/workflow.md`
- Specs: `.trellis-lite/spec/`
- Tasks: `.trellis-lite/tasks/`
- Journal: `.trellis-lite/workspace/triage/`
<!-- trellis-lite:end -->
