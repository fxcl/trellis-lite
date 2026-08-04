#!/usr/bin/env bash
#
# Trellis Lite — Installer
#
# Copies .trellis-lite/ and platform-specific entry files into the target project.
# Then runs `trellis.py init` to set up developer identity.
#
# Usage:
#   ./install.sh [target-dir] [developer-name] [--platforms <list>]
#
# Platforms (default: all):
#   qoder       → AGENTS.md
#   claude      → CLAUDE.md
#   opencode    → AGENTS.md (shared with qoder)
#   cline       → .clinerules/trellis-lite.md
#   all         → all of the above (default)
#
# Examples:
#   ./install.sh . myname                       # install everything
#   ./install.sh . myname --platforms claude    # Claude Code only
#   ./install.sh . myname --platforms qoder,cline
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

# --- Parse args ---

TARGET_DIR=""
DEV_NAME="$(whoami)"
PLATFORMS="all"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --platforms)
            PLATFORMS="$2"
            shift 2
            ;;
        --platforms=*)
            PLATFORMS="${1#*=}"
            shift
            ;;
        *)
            if [ -z "$TARGET_DIR" ]; then
                TARGET_DIR="$1"
            elif [ "$DEV_NAME" = "$(whoami)" ]; then
                DEV_NAME="$1"
            fi
            shift
            ;;
    esac
done

# Default target to current directory if not provided
if [ -z "$TARGET_DIR" ]; then
    TARGET_DIR="."
fi

echo -e "${CYAN}Trellis Lite Installer${NC}"
echo ""

# Validate target directory exists before cd
if [ ! -d "$TARGET_DIR" ]; then
    echo -e "${RED}Error: target directory not found: ${TARGET_DIR}${NC}" >&2
    echo -e "${RED}Usage: ./install.sh [target-dir] [developer-name] [--platforms <list>]${NC}" >&2
    exit 1
fi

# Resolve target to absolute path
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
echo -e "Target:    ${TARGET_DIR}"
echo -e "Developer: ${DEV_NAME}"
echo -e "Platforms: ${PLATFORMS}"
echo ""

# --- Validate platforms ---

VALID_PLATFORMS=("qoder" "claude" "opencode" "cline" "all")
if [ "$PLATFORMS" != "all" ]; then
    IFS=',' read -ra REQUESTED <<< "$PLATFORMS"
    for p in "${REQUESTED[@]}"; do
        found=0
        for v in "${VALID_PLATFORMS[@]}"; do
            if [ "$p" = "$v" ]; then
                found=1
                break
            fi
        done
        if [ "$found" -eq 0 ]; then
            echo -e "${RED}Error: unknown platform '$p'. Valid: ${VALID_PLATFORMS[*]}${NC}" >&2
            exit 1
        fi
    done
fi

# --- Helper: check if platform is selected ---

has_platform() {
    local p="$1"
    [[ "$PLATFORMS" = "all" || ",$PLATFORMS," = *",$p,"* ]]
}

# --- 1. Copy .trellis-lite/ ---

SRC_TRELLIS="${SCRIPT_DIR}/.trellis-lite"
DST_TRELLIS="${TARGET_DIR}/.trellis-lite"

if [ -d "$DST_TRELLIS" ]; then
    echo -e "${YELLOW}⚠  .trellis-lite/ already exists in target. Skipping copy.${NC}"
    echo -e "  To overwrite, remove it first: rm -rf ${DST_TRELLIS}"
else
    echo -e "${GREEN}→ Copying .trellis-lite/ ...${NC}"
    cp -r "$SRC_TRELLIS" "$DST_TRELLIS"
    # Remove runtime-only files that may linger in the template copy
    # (.current-task, .developer, __pycache__). init below recreates .developer.
    rm -f "${DST_TRELLIS}/.current-task" "${DST_TRELLIS}/.developer"
    rm -rf "${DST_TRELLIS}/scripts/__pycache__"
fi

echo ""

# --- 2. Install platform entry files ---

INSTALLED_PLATFORMS=()

# Qoder / OpenCode → AGENTS.md
if has_platform "qoder" || has_platform "opencode"; then
    SRC_AGENTS="${SCRIPT_DIR}/AGENTS.md"
    DST_AGENTS="${TARGET_DIR}/AGENTS.md"

    if [ -f "$DST_AGENTS" ]; then
        echo -e "${YELLOW}⚠  AGENTS.md already exists. Skipping (merge manually if needed).${NC}"
    else
        echo -e "${GREEN}→ Installing AGENTS.md (Qoder / OpenCode) ...${NC}"
        cp "$SRC_AGENTS" "$DST_AGENTS"
    fi
    if has_platform "qoder"; then
        INSTALLED_PLATFORMS+=("Qoder")
    fi
    if has_platform "opencode"; then
        INSTALLED_PLATFORMS+=("OpenCode")
    fi
fi

# Claude Code → CLAUDE.md
if has_platform "claude"; then
    SRC_CLAUDE="${SCRIPT_DIR}/CLAUDE.md"
    DST_CLAUDE="${TARGET_DIR}/CLAUDE.md"

    if [ -f "$DST_CLAUDE" ]; then
        echo -e "${YELLOW}⚠  CLAUDE.md already exists. Skipping (merge manually if needed).${NC}"
    else
        echo -e "${GREEN}→ Installing CLAUDE.md (Claude Code) ...${NC}"
        cp "$SRC_CLAUDE" "$DST_CLAUDE"
    fi
    INSTALLED_PLATFORMS+=("Claude Code")
fi

# Cline → .clinerules/trellis-lite.md
if has_platform "cline"; then
    DST_CLINERULES="${TARGET_DIR}/.clinerules"

    if [ -d "$DST_CLINERULES" ]; then
        echo -e "${YELLOW}⚠  .clinerules/ already exists. Checking for trellis-lite.md ...${NC}"
    else
        echo -e "${GREEN}→ Creating .clinerules/ (Cline) ...${NC}"
        mkdir -p "$DST_CLINERULES"
    fi

    # Write Cline rule file (same content as AGENTS.md, Cline reads .clinerules/*.md)
    DST_CLINE_RULE="${DST_CLINERULES}/trellis-lite.md"
    if [ -f "$DST_CLINE_RULE" ]; then
        echo -e "${YELLOW}⚠  .clinerules/trellis-lite.md already exists. Skipping.${NC}"
    else
        echo -e "${GREEN}→ Installing .clinerules/trellis-lite.md (Cline) ...${NC}"
        # Copy AGENTS.md content (Cline doesn't support @import)
        cp "${SCRIPT_DIR}/AGENTS.md" "$DST_CLINE_RULE"
    fi
    INSTALLED_PLATFORMS+=("Cline")
fi

echo ""

# --- 3. Initialize ---

echo -e "${GREEN}→ Running trellis.py init ...${NC}"
# Run from target dir so get_repo_root() finds the target .trellis-lite/
cd "$TARGET_DIR"
python3 "${DST_TRELLIS}/scripts/trellis.py" init "$DEV_NAME"

echo ""
echo -e "${GREEN}✓ Trellis Lite installed!${NC}"
echo ""
echo -e "Supported platforms: ${INSTALLED_PLATFORMS[*]:-none}"
echo ""
echo -e "Next steps:"
echo -e "  1. Open your project in your AI coding tool"
echo -e "  2. The AI will read the entry file and follow the workflow"
echo -e "  3. Add coding specs to ${DST_TRELLIS}/spec/"
echo -e "  4. Start your first task:"
echo -e "     python3 ${DST_TRELLIS}/scripts/trellis.py task create \"My first task\""
echo ""

# --- 4. Add to .gitignore ---

GITIGNORE="${TARGET_DIR}/.gitignore"
RUNTIME_FILES=(
    ".trellis-lite/.developer"
    ".trellis-lite/.current-task"
)

if [ -f "$GITIGNORE" ]; then
    NEEDS_ADD=()
    for f in "${RUNTIME_FILES[@]}"; do
        if ! grep -qxF "$f" "$GITIGNORE" 2>/dev/null; then
            NEEDS_ADD+=("$f")
        fi
    done
    if [ ${#NEEDS_ADD[@]} -gt 0 ]; then
        echo -e "${GREEN}→ Adding runtime files to .gitignore ...${NC}"
        echo "" >> "$GITIGNORE"
        echo "# Trellis Lite runtime" >> "$GITIGNORE"
        for f in "${NEEDS_ADD[@]}"; do
            echo "$f" >> "$GITIGNORE"
        done
    fi
else
    echo -e "${YELLOW}⚠  No .gitignore found. Add these to .gitignore manually:${NC}"
    for f in "${RUNTIME_FILES[@]}"; do
        echo "  $f"
    done
fi

echo ""
echo -e "${GREEN}Done.${NC}"

# --- 5. Optionally install pre-commit hook (opt-in) ---

HOOK_SRC="${SCRIPT_DIR}/hooks/pre-commit"
HOOK_DST="${TARGET_DIR}/.git/hooks/pre-commit"

if [ -d "${TARGET_DIR}/.git" ] && [ -f "$HOOK_SRC" ]; then
    if [ -f "$HOOK_DST" ]; then
        echo -e "${YELLOW}⚠  .git/hooks/pre-commit already exists. Skipping (review manually).${NC}"
    else
        echo -e "${GREEN}→ Installing pre-commit hook ...${NC}"
        cp "$HOOK_SRC" "$HOOK_DST"
        chmod +x "$HOOK_DST"
        echo -e "  The hook will run ${CYAN}trellis doctor${NC} before each commit."
        echo -e "  To bypass: ${CYAN}git commit --no-verify${NC}"
    fi
elif [ ! -d "${TARGET_DIR}/.git" ]; then
    echo ""
    echo -e "${YELLOW}Note: no .git/ directory found. Skipping pre-commit hook install.${NC}"
    echo -e "  After 'git init', copy lite/hooks/pre-commit to .git/hooks/pre-commit manually."
fi
