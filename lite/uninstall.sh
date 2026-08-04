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
if [ ! -d "$TARGET/.trellis-lite" ] \
    && [ ! -f "$TARGET/AGENTS.md" ] \
    && [ ! -f "$TARGET/CLAUDE.md" ] \
    && [ ! -d "$TARGET/.clinerules" ]; then
    echo "Error: '$TARGET' does not appear to have Trellis Lite installed" >&2
    echo "  (no .trellis-lite/, AGENTS.md, CLAUDE.md, or .clinerules/ found)" >&2
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

echo ""
echo "✓ Removed $removed item(s) from '$TARGET'"
echo ""
echo "Note: tasks archived under .trellis-lite/tasks/archive/YYYY-MM/"
echo "      were also removed. If you backed them up elsewhere, they"
echo "      are still recoverable from your backup."
