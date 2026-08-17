#!/usr/bin/env bash
# Trellis Lite uninstaller
# Removes the runtime and platform entry files from a target directory.
# Usage: ./uninstall.sh [target-dir]

set -euo pipefail

TARGET="${1:-.}"

if [ ! -d "$TARGET" ]; then
    echo "Error: '$TARGET' is not a directory" >&2
    exit 1
fi

# Refuse to run if there's no .trellis-lite/ AND no entry files
# (so we don't accidentally trash a project that doesn't use Trellis)
# Guards probe Trellis-owned sentinels (trellis-* files / marker files),
# not bare platform dirs — a user's own .qoder/ or .opencode/ setup must
# not be mistaken for a Trellis install.
if [ ! -d "$TARGET/.trellis-lite" ] \
    && [ ! -f "$TARGET/AGENTS.md" ] \
    && [ ! -f "$TARGET/CLAUDE.md" ] \
    && [ ! -f "$TARGET/.clinerules/trellis-lite.md" ] \
    && [ ! -e "$TARGET/.qoder/agents/trellis-brainstorm.md" ] \
    && [ ! -e "$TARGET/.qoder/skills/trellis-brainstorm" ] \
    && [ ! -e "$TARGET/.opencode/agents/trellis-brainstorm.md" ] \
    && [ ! -e "$TARGET/.opencode/commands/trellis-context.md" ] \
    && [ ! -e "$TARGET/.claude/commands/trellis-context.md" ] \
    && [ ! -f "$TARGET/docs/.trellis-docs" ]; then
    echo "Error: '$TARGET' does not appear to have Trellis Lite installed" >&2
    echo "  (no .trellis-lite/, AGENTS.md, CLAUDE.md, .clinerules/, .qoder/agents/, .qoder/skills/, .opencode/, .claude/commands/, or docs/ found)" >&2
    exit 1
fi

echo "Removing Trellis Lite from '$TARGET'..."

removed=0

# Runtime directory
if [ -d "$TARGET/.trellis-lite" ]; then
    rm -rf "$TARGET/.trellis-lite"
    echo "  ✓ .trellis-lite/"
    removed=$((removed + 1))
fi

# Docs (Trellis reference material) — only if installed by us (marker present).
# A pre-existing user docs/ dir was skipped by install; don't touch it.
if [ -f "$TARGET/docs/.trellis-docs" ]; then
    rm -rf "$TARGET/docs"
    echo "  ✓ docs/"
    removed=$((removed + 1))
fi

# Platform entry files
for f in AGENTS.md CLAUDE.md; do
    if [ -f "$TARGET/$f" ]; then
        rm -f "$TARGET/$f"
        echo "  ✓ $f"
        removed=$((removed + 1))
    fi
done

# Cline rules — remove only the trellis-lite rule, keep other rules
if [ -f "$TARGET/.clinerules/trellis-lite.md" ]; then
    rm -f "$TARGET/.clinerules/trellis-lite.md"
    echo "  ✓ .clinerules/trellis-lite.md"
    removed=$((removed + 1))
    # Remove the directory only if it's now empty
    if [ -d "$TARGET/.clinerules" ] && [ -z "$(ls -A "$TARGET/.clinerules")" ]; then
        rmdir "$TARGET/.clinerules"
        echo "  ✓ .clinerules/ (empty, removed)"
    fi
fi

# Qoder agents + skills — remove only Trellis-managed entries (trellis-*),
# keep user-created agents/skills intact
for f in "$TARGET"/.qoder/agents/trellis-*.md; do
    [ -f "$f" ] || continue
    rm -f "$f"
    echo "  ✓ ${f#"$TARGET"/}"
    removed=$((removed + 1))
done
for d in "$TARGET"/.qoder/skills/trellis-*; do
    [ -d "$d" ] || continue
    rm -rf "$d"
    echo "  ✓ ${d#"$TARGET"/}"
    removed=$((removed + 1))
done
# Prune now-empty Trellis subdirs, then the .qoder/ parent
for qoder_sub in agents skills; do
    if [ -d "$TARGET/.qoder/$qoder_sub" ] && [ -z "$(ls -A "$TARGET/.qoder/$qoder_sub")" ]; then
        rmdir "$TARGET/.qoder/$qoder_sub"
        echo "  ✓ .qoder/$qoder_sub/ (empty, removed)"
    fi
done
if [ -d "$TARGET/.qoder" ] && [ -z "$(ls -A "$TARGET/.qoder")" ]; then
    rmdir "$TARGET/.qoder"
    echo "  ✓ .qoder/ (empty, removed)"
fi

# OpenCode agents + commands — remove only Trellis-managed entries
# (trellis-*), keep user-created ones intact
for f in "$TARGET"/.opencode/agents/trellis-*.md; do
    [ -f "$f" ] || continue
    rm -f "$f"
    echo "  ✓ ${f#"$TARGET"/}"
    removed=$((removed + 1))
done
for f in "$TARGET"/.opencode/commands/trellis-*.md; do
    [ -f "$f" ] || continue
    rm -f "$f"
    echo "  ✓ ${f#"$TARGET"/}"
    removed=$((removed + 1))
done
# Prune now-empty Trellis subdirs, then the .opencode/ parent
for opencode_sub in agents commands; do
    if [ -d "$TARGET/.opencode/$opencode_sub" ] && [ -z "$(ls -A "$TARGET/.opencode/$opencode_sub")" ]; then
        rmdir "$TARGET/.opencode/$opencode_sub"
        echo "  ✓ .opencode/$opencode_sub/ (empty, removed)"
    fi
done
if [ -d "$TARGET/.opencode" ] && [ -z "$(ls -A "$TARGET/.opencode")" ]; then
    rmdir "$TARGET/.opencode"
    echo "  ✓ .opencode/ (empty, removed)"
fi

# Claude Code trellis commands — remove only Trellis-managed entries
# (trellis-*), keep user-created ones intact
for f in "$TARGET"/.claude/commands/trellis-*.md; do
    [ -f "$f" ] || continue
    rm -f "$f"
    echo "  ✓ ${f#"$TARGET"/}"
    removed=$((removed + 1))
done
# Prune now-empty .claude/commands/ and the .claude/ parent
if [ -d "$TARGET/.claude/commands" ] && [ -z "$(ls -A "$TARGET/.claude/commands")" ]; then
    rmdir "$TARGET/.claude/commands"
    echo "  ✓ .claude/commands/ (empty, removed)"
    if [ -d "$TARGET/.claude" ] && [ -z "$(ls -A "$TARGET/.claude")" ]; then
        rmdir "$TARGET/.claude"
        echo "  ✓ .claude/ (empty, removed)"
    fi
fi

# --- Clean up .gitignore entries added by install.sh ---
GITIGNORE="${TARGET}/.gitignore"
if [ -f "$GITIGNORE" ] && grep -qxF "# Trellis Lite runtime" "$GITIGNORE" 2>/dev/null; then
    # Remove the marker comment and any Trellis-managed runtime-file entries
    # that follow it (until the next marker or non-managed line). We keep skip=1
    # across intervening user lines (e.g. comments, blank lines) so a
    # subsequent .trellis-lite/.X entry is still cleaned up — even if the
    # user edited the block in between.
    #
    # The grep above is anchored (-x) and literal (-F) so a user's prose
    # comment like "# Trellis Lite runtime monitoring explained" doesn't
    # trigger this branch and falsely report a cleanup.
    tmpfile=$(mktemp)
    trap 'rm -f "$tmpfile" 2>/dev/null || true' EXIT
    awk '
        /^# Trellis Lite runtime$/ { skip=1; next }
        skip && /^\.trellis-lite\/\./ { next }
        skip { print; next }
        { print }
    ' "$GITIGNORE" > "$tmpfile" && mv "$tmpfile" "$GITIGNORE"
    echo "  ✓ .gitignore (removed Trellis Lite runtime entries)"
    removed=$((removed + 1))
fi

# --- Remove pre-commit hook (only if it's the Trellis Lite one) ---
HOOK="${TARGET}/.git/hooks/pre-commit"
if [ -f "$HOOK" ] && grep -q "Trellis Lite" "$HOOK" 2>/dev/null; then
    rm -f "$HOOK"
    echo "  ✓ .git/hooks/pre-commit (Trellis Lite hook)"
    removed=$((removed + 1))
fi

echo ""
echo "✓ Removed $removed item(s) from '$TARGET'"
echo ""
echo "Note: tasks archived under .trellis-lite/tasks/archive/YYYY-MM/"
echo "      were also removed. If you backed them up elsewhere, they"
echo "      are still recoverable from your backup."
