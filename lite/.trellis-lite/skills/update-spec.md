# Update Spec — Capture Learnings

Use during Phase 3 (WRAP) or whenever you discover something worth preserving.

## When to Update Specs

- Debugged a tricky issue that others might hit
- Discovered a project convention or pattern
- Learned an API contract or data format rule
- Found a constraint that's not obvious from code alone
- A review caught a recurring mistake

## How to Write a Spec

A spec is an **executable contract**, not a vague principle.

### Bad (vague)
> "Handle errors gracefully"

### Good (executable)
> "All API endpoints return `{ data, error, meta }`. On error, `data` is null and `error` is `{ code: string, message: string }`. HTTP status is 4xx for client errors, 5xx for server errors."

## Spec File Conventions

```bash
python3 .trellis-lite/scripts/trellis.py specs  # see existing specs
```

- One file per area: `api.md`, `database.md`, `ui-components.md`, `testing.md`, etc.
- Use `## Rule:` headers for individual rules so they're scannable
- Include code examples for "do" and "don't"
- Reference the file/path that motivated the rule

## Spec File Template

```markdown
# <Area> Spec

## Rule: <name>
<Description>

**Do:**
```<lang>
<code example>
```

**Don't:**
```<lang>
<code example>
```

## Rule: <name>
...
```

## Flow

1. **Identify** what you learned (a pattern, a pitfall, a contract)
2. **Check existing specs** — does this belong in an existing file or a new one?
3. **Write the rule** with concrete examples
4. **Verify** the rule applies to existing code (not just your current change)
5. **Commit** the spec change alongside or after your code change

## Key Principle

Specs prevent the same problem from recurring. If you fixed a bug, write a spec so the next session (you or AI) won't reintroduce it.
