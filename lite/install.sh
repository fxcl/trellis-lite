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
#   qoder       → AGENTS.md + .qoder/agents/ (trellis-brainstorm, trellis-implement, trellis-check)
#                 + .qoder/skills/trellis-*/SKILL.md (12 slash entry points: 4 deep-workflow skills
#                 generated from .trellis-lite/skills/ + 8 py-command wrappers generated from
#                 templates/claude/commands/trellis-*.md; trellis-check is the deep-workflow version)
#   claude      → CLAUDE.md + .claude/commands/ (9 slash commands: trellis-context ... trellis-list)
#   opencode    → AGENTS.md (shared with qoder) + .opencode/agents/ (3 agents)
#                 + .opencode/commands/ (9 commands: trellis-context ... trellis-list)
#   cline       → .clinerules/trellis-lite.md + .cline/skills/trellis-*/SKILL.md
#                 (12 slash entry points, same generated wrappers as qoder)
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

# --- F62: macOS bash 3.2 compatibility gate ---
#
# macOS /bin/bash is 3.2.57 (last GPLv2 release), which lacks bash 4.0+
# features used below: `read -ra` (validate_platforms loop) and
# `arr+=()` syntax (F50 INSTALLED_FILES, INSTALLED_PLATFORMS). On bash
# 3.2 the script first dies with a cryptic `syntax error near
# unexpected token '('` — and worse, F50's `trap rollback ERR` may
# already have started cleanup of partially-installed files because
# the first failing line is mid-install. Detect up front with a clear
# upgrade hint instead, so users get an actionable error before any
# state is touched.
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
    echo -e "${RED}Error: bash 4.0+ required (you have $BASH_VERSION).${NC}" >&2
    echo "" >&2
    echo -e "macOS users: install via Homebrew:" >&2
    echo -e "  brew install bash" >&2
    echo -e "then re-run with the new shell:" >&2
    echo -e "  /usr/local/bin/bash install.sh . <name>" >&2
    echo "" >&2
    echo -e "Linux users: your distro's bash 4+ is at /usr/bin/bash." >&2
    exit 1
fi

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

# --- F50: rollback on partial-install failure ---
#
# If any step after we've started writing to the target fails (Python missing,
# permission denied, Python 3 < 3.9), `set -e` aborts. Without cleanup, the
# target is left with .trellis-lite/, AGENTS.md, CLAUDE.md, .clinerules/
# already copied but not initialised — re-running install.sh then silently
# skips the copies (line 116 detects existing .trellis-lite/) and the user
# is stuck with a broken state they have to rm -rf manually.
#
# Fix: track every file/dir we touch in INSTALLED_FILES and clean them up
# via `trap ERR` if anything fails mid-install. The trap is reset to nothing
# once init succeeds so the rest of the script (gitignore + pre-commit hook)
# can run without rollback semantics.
INSTALLED_FILES=()
rollback() {
    local exit_code=$?
    if [ ${#INSTALLED_FILES[@]} -eq 0 ]; then
        return $exit_code
    fi
    echo "" >&2
    echo -e "${RED}✗ Install failed (exit $exit_code) — rolling back partial state${NC}" >&2
    for f in "${INSTALLED_FILES[@]}"; do
        if [ -e "$f" ]; then
            rm -rf "$f"
            echo -e "  ${RED}removed${NC} $f" >&2
        fi
    done
    echo -e "${YELLOW}Re-run ./install.sh after fixing the cause (e.g. install Python 3.9+).${NC}" >&2
    exit $exit_code
}
trap rollback ERR

# --- 1. Copy .trellis-lite/ ---

SRC_TRELLIS="${SCRIPT_DIR}/.trellis-lite"
DST_TRELLIS="${TARGET_DIR}/.trellis-lite"

if [ -d "$DST_TRELLIS" ]; then
    echo -e "${YELLOW}⚠  .trellis-lite/ already exists in target. Skipping copy.${NC}"
    echo -e "  To overwrite, remove it first: rm -rf ${DST_TRELLIS}"
else
    echo -e "${GREEN}→ Copying .trellis-lite/ ...${NC}"
    cp -r "$SRC_TRELLIS" "$DST_TRELLIS"
    INSTALLED_FILES+=("$DST_TRELLIS")
    # Remove runtime-only files that may linger in the template copy
    # (.current-task, .developer, __pycache__). init below recreates .developer.
    rm -f "${DST_TRELLIS}/.current-task" "${DST_TRELLIS}/.developer"
    rm -rf "${DST_TRELLIS}/scripts/__pycache__"
fi

# --- 1b. Copy docs/ (reference material for agents and users) ---
#
# Agents read these (best-practices, workflow-checklist, architecture-review,
# etc.) when following References links in templates and workflow.md. Without
# this copy those links 404 in the installed project. Idempotent: skip if the
# user already has a docs/ dir (may have their own documentation).

SRC_DOCS="${SCRIPT_DIR}/docs"
DST_DOCS="${TARGET_DIR}/docs"

if [ -d "$SRC_DOCS" ]; then
    if [ -d "$DST_DOCS" ]; then
        echo -e "${YELLOW}⚠  docs/ already exists in target. Skipping (merge manually if needed).${NC}"
    else
        echo -e "${GREEN}→ Copying docs/ ...${NC}"
        cp -r "$SRC_DOCS" "$DST_DOCS"
        # Marker so uninstall can distinguish Trellis docs from a pre-existing
        # user docs/ dir (which install skips and uninstall must not touch).
        echo "Installed by Trellis Lite. Safe to remove on uninstall." \
            > "${DST_DOCS}/.trellis-docs"
        INSTALLED_FILES+=("$DST_DOCS")
    fi
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
        INSTALLED_FILES+=("$DST_AGENTS")
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
        INSTALLED_FILES+=("$DST_CLAUDE")
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
        INSTALLED_FILES+=("$DST_CLINERULES")
    fi

    # Write Cline rule file (same content as AGENTS.md, Cline reads .clinerules/*.md)
    DST_CLINE_RULE="${DST_CLINERULES}/trellis-lite.md"
    if [ -f "$DST_CLINE_RULE" ]; then
        echo -e "${YELLOW}⚠  .clinerules/trellis-lite.md already exists. Skipping.${NC}"
    else
        echo -e "${GREEN}→ Installing .clinerules/trellis-lite.md (Cline) ...${NC}"
        # Copy AGENTS.md content (Cline doesn't support @import)
        cp "${SCRIPT_DIR}/AGENTS.md" "$DST_CLINE_RULE"
        INSTALLED_FILES+=("$DST_CLINE_RULE")
    fi
    INSTALLED_PLATFORMS+=("Cline")
fi

# Qoder → .qoder/agents/ (Trellis sub-agents)
if has_platform "qoder"; then
    SRC_QODER_AGENTS="${SCRIPT_DIR}/templates/qoder/agents"
    DST_QODER_AGENTS="${TARGET_DIR}/.qoder/agents"

    if [ -d "$SRC_QODER_AGENTS" ]; then
        mkdir -p "$DST_QODER_AGENTS"
        for f in "$SRC_QODER_AGENTS"/*.md; do
            [ -f "$f" ] || continue
            DST_FILE="$DST_QODER_AGENTS/$(basename "$f")"
            if [ -f "$DST_FILE" ]; then
                echo -e "${YELLOW}⚠  .qoder/agents/$(basename "$f") already exists. Skipping.${NC}"
            else
                cp "$f" "$DST_FILE"
                INSTALLED_FILES+=("$DST_FILE")
            fi
        done
    fi
fi

# Skills-based platforms → .qoder/skills/ + .cline/skills/trellis-*/SKILL.md
# (slash entry points)
#
# Qoder and Cline have no standalone commands directory; skills are their
# slash entry points (Qoder: skill dirs are its slash entries; Cline: skill
# dirs under .cline/skills/, triggered by description match or /skill-name —
# docs.cline.bot/customization/skills). Each SKILL.md is GENERATED at install
# time: thin YAML frontmatter + the verbatim body from .trellis-lite/skills/
# <name>.md (already copied to the target). The .trellis-lite/skills/ files
# remain the single body source. The SAME generation runs for every skills
# platform, so wrappers are byte-identical across platforms. Wrappers are
# generated on FIRST install only; re-installs skip existing ones (delete
# <plat>/skills/trellis-*/ and re-run install to regenerate after a skills
# source update).
SKILL_DST_DIRS=()
has_platform "qoder" && SKILL_DST_DIRS+=("${TARGET_DIR}/.qoder/skills")
has_platform "cline" && SKILL_DST_DIRS+=("${TARGET_DIR}/.cline/skills")

# set -u guard: bash <4.4 errors on expanding an empty array
if [ "${#SKILL_DST_DIRS[@]}" -gt 0 ]; then
SRC_SKILLS="${TARGET_DIR}/.trellis-lite/skills"
SRC_CLAUDE_COMMANDS_FOR_SKILLS="${SCRIPT_DIR}/templates/claude/commands"

for DST_SKILLS in "${SKILL_DST_DIRS[@]}"; do
    DST_SKILLS_REL="${DST_SKILLS#"${TARGET_DIR}/"}"

    if [ -d "$SRC_SKILLS" ]; then
        for f in "$SRC_SKILLS"/*.md; do
            [ -f "$f" ] || continue
            skill_name="$(basename "$f" .md)"
            case "$skill_name" in
                brainstorm)  skill_desc="Trellis PLAN phase: turn a request into a PRD via codebase exploration and one-question-at-a-time interviews" ;;
                before-dev)  skill_desc="Trellis CODE phase: mandatory pre-implementation routine — load task artifacts, read specs, follow existing patterns" ;;
                check)       skill_desc="Trellis WRAP phase: review changes against specs and PRD, run project checks, self-fix, report" ;;
                update-spec) skill_desc="Trellis WRAP phase: capture reusable lessons into .trellis-lite/spec/ files" ;;
                *)           skill_desc="Trellis Lite workflow skill: ${skill_name}" ;;
            esac
            DST_SKILL_DIR="${DST_SKILLS}/trellis-${skill_name}"
            if [ -f "${DST_SKILL_DIR}/SKILL.md" ]; then
                echo -e "${YELLOW}⚠  ${DST_SKILLS_REL}/trellis-${skill_name}/SKILL.md already exists. Skipping.${NC}"
            else
                mkdir -p "$DST_SKILL_DIR"
                {
                    echo "---"
                    echo "name: trellis-${skill_name}"
                    # Block scalar: skill descriptions contain ': ' which is
                    # invalid in a YAML plain scalar.
                    echo "description: |"
                    echo "  ${skill_desc}"
                    echo "---"
                    echo ""
                    cat "$f"
                } > "${DST_SKILL_DIR}/SKILL.md"
                INSTALLED_FILES+=("${DST_SKILL_DIR}/SKILL.md")
            fi
        done
    fi

    # Py-command wrappers: one skill per trellis.py subcommand so skills
    # platforms get the same /trellis-context, /trellis-new, ... slash
    # entries Claude and OpenCode have. Body source is
    # templates/claude/commands/trellis-*.md (the single source for
    # command-map bodies across ALL platforms): keep the body verbatim, drop
    # the Claude frontmatter (incl. allowed-tools), wrap in skill frontmatter
    # with the description reused from the Claude file. trellis-check is
    # SKIPPED — the deep-workflow skill above already owns that name and
    # covers py check.
    # Same first-install-only rule as the deep-workflow skills.
    if [ -d "$SRC_CLAUDE_COMMANDS_FOR_SKILLS" ]; then
        for f in "$SRC_CLAUDE_COMMANDS_FOR_SKILLS"/trellis-*.md; do
            [ -f "$f" ] || continue
            cmd_name="$(basename "$f" .md)"
            [ "$cmd_name" = "trellis-check" ] && continue
            DST_SKILL_DIR="${DST_SKILLS}/${cmd_name}"
            if [ -f "${DST_SKILL_DIR}/SKILL.md" ]; then
                echo -e "${YELLOW}⚠  ${DST_SKILLS_REL}/${cmd_name}/SKILL.md already exists. Skipping.${NC}"
            else
                cmd_desc="$(sed -n 's/^description:[[:space:]]*//p' "$f" | head -n 1)"
                mkdir -p "$DST_SKILL_DIR"
                {
                    echo "---"
                    echo "name: ${cmd_name}"
                    echo "description: |"
                    echo "  ${cmd_desc}"
                    echo "---"
                    # Body = everything after the closing --- of the Claude
                    # frontmatter (it already opens with a blank line, so no
                    # extra separator is needed here).
                    awk 'NR==1{next} /^---/{p=1; next} p' "$f"
                } > "${DST_SKILL_DIR}/SKILL.md"
                INSTALLED_FILES+=("${DST_SKILL_DIR}/SKILL.md")
            fi
        done
    fi

done
fi

# OpenCode → .opencode/agents/ + .opencode/commands/
if has_platform "opencode"; then
    # Agents
    SRC_OPENCODE_AGENTS="${SCRIPT_DIR}/templates/opencode/agents"
    DST_OPENCODE_AGENTS="${TARGET_DIR}/.opencode/agents"

    if [ -d "$SRC_OPENCODE_AGENTS" ]; then
        mkdir -p "$DST_OPENCODE_AGENTS"
        for f in "$SRC_OPENCODE_AGENTS"/*.md; do
            [ -f "$f" ] || continue
            DST_FILE="$DST_OPENCODE_AGENTS/$(basename "$f")"
            if [ -f "$DST_FILE" ]; then
                echo -e "${YELLOW}⚠  .opencode/agents/$(basename "$f") already exists. Skipping.${NC}"
            else
                cp "$f" "$DST_FILE"
                INSTALLED_FILES+=("$DST_FILE")
            fi
        done
    fi

    # Commands
    SRC_OPENCODE_COMMANDS="${SCRIPT_DIR}/templates/opencode/commands"
    DST_OPENCODE_COMMANDS="${TARGET_DIR}/.opencode/commands"

    if [ -d "$SRC_OPENCODE_COMMANDS" ]; then
        mkdir -p "$DST_OPENCODE_COMMANDS"
        for f in "$SRC_OPENCODE_COMMANDS"/*.md; do
            [ -f "$f" ] || continue
            DST_FILE="$DST_OPENCODE_COMMANDS/$(basename "$f")"
            if [ -f "$DST_FILE" ]; then
                echo -e "${YELLOW}⚠  .opencode/commands/$(basename "$f") already exists. Skipping.${NC}"
            else
                cp "$f" "$DST_FILE"
                INSTALLED_FILES+=("$DST_FILE")
            fi
        done
    fi
fi

# Claude Code → .claude/commands/trellis-*.md (slash commands)
if has_platform "claude"; then
    SRC_CLAUDE_COMMANDS="${SCRIPT_DIR}/templates/claude/commands"
    DST_CLAUDE_COMMANDS="${TARGET_DIR}/.claude/commands"

    if [ -d "$SRC_CLAUDE_COMMANDS" ]; then
        mkdir -p "$DST_CLAUDE_COMMANDS"
        for f in "$SRC_CLAUDE_COMMANDS"/trellis-*.md; do
            [ -f "$f" ] || continue
            DST_FILE="$DST_CLAUDE_COMMANDS/$(basename "$f")"
            if [ -f "$DST_FILE" ]; then
                echo -e "${YELLOW}⚠  .claude/commands/$(basename "$f") already exists. Skipping.${NC}"
            else
                cp "$f" "$DST_FILE"
                INSTALLED_FILES+=("$DST_FILE")
            fi
        done
    fi
fi

echo ""

# --- 3. Initialize ---

echo -e "${GREEN}→ Running trellis.py init ...${NC}"
# Run from target dir so get_repo_root() finds the target .trellis-lite/
cd "$TARGET_DIR"
# If .developer already exists (e.g. re-running install on an existing
# Trellis project), don't silently overwrite it — the user may have run
# `init` deliberately with a different name and re-running install would
# surprise them by rewriting it. Re-running `init` explicitly is still
# available for users who want to change their developer name.
if [ -f "${DST_TRELLIS}/.developer" ]; then
    EXISTING_DEV="$(grep '^name=' "${DST_TRELLIS}/.developer" | head -1 | cut -d= -f2-)"
    echo -e "${YELLOW}  Note: .developer already set to '${EXISTING_DEV}'; skipping init (re-run 'init' to change).${NC}"
else
    python3 "${DST_TRELLIS}/scripts/trellis.py" init "$DEV_NAME"
fi

# init succeeded (or was skipped because .developer already exists).
# Disable rollback: any subsequent failure should NOT remove files we
# successfully wrote, since the user can still manually fix the remaining
# steps (gitignore, pre-commit hook) after.
trap - ERR

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
