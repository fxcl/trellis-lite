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

If you create `.claude/commands/` custom slash commands, they can wrap trellis.py:

```
/trellis-context    → python3 .trellis-lite/scripts/trellis.py context
/trellis-current    → python3 .trellis-lite/scripts/trellis.py task current
```
