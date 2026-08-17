# Trellis Lite — Claude Code Bridge

> This file bridges Claude Code to the Trellis Lite instructions in AGENTS.md.
> Claude Code reads CLAUDE.md on startup; the @import below pulls in the full instructions.

@AGENTS.md

## Claude Code Specifics

### Sub-Agent Dispatch

Claude Code supports the `Task` tool for sub-agent dispatch:

- **Implement**: Use `Task` with `subagent_type: "general-purpose"`. Tell it to read `prd.md` + specs first.
- **Review**: Use `Task` with `subagent_type: "code-reviewer"`. Tell it to review `git diff` against specs + PRD.

Always start sub-agent prompts with: `Active task: <path from 'trellis.py task current'>`

### Slash Commands

`install.sh --platforms claude` ships 9 slash commands in `.claude/commands/` (flat `trellis-*.md` names, same namespace as OpenCode):

| Command | What it does |
|---|---|
| `/trellis-context` | Current state snapshot — active task, phase, recommended next step |
| `/trellis-new <title>` | PLAN: create a task + draft the PRD |
| `/trellis-start` | Activate the planning task (`task start`) |
| `/trellis-check` | Review the working diff against specs + PRD |
| `/trellis-finish` | `task finish` + session record + spec-update reminders |
| `/trellis-archive` | Archive a done task |
| `/trellis-doctor` | Health check (`doctor`) |
| `/trellis-cancel` | Cancel the active task |
| `/trellis-list` | List tasks (all statuses) |

If these commands are missing, either re-run `install.sh --platforms claude`
or invoke `trellis.py` subcommands directly.
