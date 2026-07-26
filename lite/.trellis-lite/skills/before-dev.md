# Before Dev — Load Project Guidelines

**Mandatory before writing any code.** Read this every time you start implementation.

## Steps

1. **Read current task artifacts**:
   ```bash
   python3 .trellis-lite/scripts/trellis.py task current
   ```
   Then read the task's `prd.md`. If `design.md` exists, read it too.

2. **Discover available specs**:
   ```bash
   python3 .trellis-lite/scripts/trellis.py specs
   ```

3. **Read specs relevant to your task**:
   ```bash
   cat .trellis-lite/spec/<relevant-file>.md
   ```
   Read ALL spec files that apply to the code you're about to write. Don't skip — specs exist because past-you (or past-AI) learned something the hard way.

4. **Understand existing code patterns**:
   - Read files in the same directory you'll be editing
   - Note naming conventions, error handling style, import patterns
   - Follow existing patterns unless the PRD explicitly says otherwise

5. **Proceed with implementation** once you understand:
   - What to build (from PRD)
   - How to build it (from specs + existing patterns)
   - What "done" looks like (from acceptance criteria)

## Key Principle

Specs are **executable contracts**, not vague principles. If a spec says "all API responses use `{ data, error }` format", that's a rule you must follow, not a suggestion.
