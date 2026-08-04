# Coding Specs

Write your project's coding conventions and patterns here. The AI reads these
before implementing any code.

## How to structure specs

Create one `.md` file per topic. Keep them short and actionable.

### Example: `conventions.md`

```markdown
# Conventions

- Use 2-space indentation
- Prefer named exports over default exports
- Error messages must include context for debugging
- All public functions need JSDoc comments
```

### Example: `api-patterns.md`

```markdown
# API Patterns

- REST endpoints use kebab-case: /api/user-profiles
- All responses wrapped in { data, error, meta }
- Pagination via cursor, not offset
- Rate limit: 100 req/min per token
```

## When to update specs

- You discover a new pattern worth repeating
- A bug fix reveals a convention that should be enforced
- You make a technical decision that affects future code