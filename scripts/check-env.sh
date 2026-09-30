#!/bin/bash
# check-env.sh - Validate environment setup for polis
#
# Usage: ./scripts/check-env.sh
#
# This script ensures .env exists and contains valid paths before building.
# Run this before your first build, especially in worktrees.
#
# Exit codes:
#   0 = Environment OK
#   1 = Error (missing .env, invalid paths, etc.)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output (disabled if not a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

error() { echo -e "${RED}ERROR:${NC} $1" >&2; }
warn() { echo -e "${YELLOW}WARNING:${NC} $1" >&2; }
ok() { echo -e "${GREEN}OK:${NC} $1"; }

# --- Check if .env exists ---
if [ ! -f "$PROJECT_DIR/.env" ]; then
    error ".env not found in $PROJECT_DIR"

    # Try to find .env in main project (for worktrees)
    # Worktrees have a .git file pointing to the main repo
    if [ -f "$PROJECT_DIR/.git" ]; then
        # Extract main worktree path from .git file
        GIT_DIR=$(cat "$PROJECT_DIR/.git" | sed 's/gitdir: //')
        # The gitdir is like /path/to/main/.git/worktrees/<name>
        # We want /path/to/main (parent of .git directory)
        MAIN_GIT_DIR=$(dirname "$(dirname "$GIT_DIR")")
        MAIN_PROJECT=$(dirname "$MAIN_GIT_DIR")

        if [ -f "$MAIN_PROJECT/.env" ]; then
            echo "Found .env in main project: $MAIN_PROJECT/.env"
            echo "Copying to worktree..."
            cp "$MAIN_PROJECT/.env" "$PROJECT_DIR/.env"
            ok "Copied .env from main project"
        else
            error "No .env in main project either: $MAIN_PROJECT"
            echo ""
            echo "Create .env from the example:"
            echo "  cp .env.example .env"
            echo "  # Then edit .env with your paths"
            echo ""
            echo "See .env.example for path examples and troubleshooting."
            exit 1
        fi
    else
        echo ""
        echo "Create .env from the example:"
        echo "  cp .env.example .env"
        echo "  # Then edit .env with your paths"
        echo ""
        echo "See .env.example for path examples and troubleshooting."
        exit 1
    fi
fi

# --- Source and validate .env ---
source "$PROJECT_DIR/.env"

# Check VINTAGE_STORY is set and exported
if [ -z "$VINTAGE_STORY" ]; then
    error "VINTAGE_STORY not set in .env"
    echo "Make sure your .env has: export VINTAGE_STORY=/path/to/vintagestory"
    echo "See .env.example for path examples."
    exit 1
fi

# Check VINTAGE_STORY path exists and has the required DLL
if [ ! -f "$VINTAGE_STORY/VintagestoryAPI.dll" ]; then
    error "VintagestoryAPI.dll not found at: $VINTAGE_STORY/VintagestoryAPI.dll"
    echo ""
    echo "Current VINTAGE_STORY value: $VINTAGE_STORY"
    echo ""
    echo "Common issues:"
    echo "  1. Path uses ~ instead of absolute path (use /home/user/... not ~/...)"
    echo "  2. Missing 'export' keyword in .env"
    echo "  3. Wrong path to Vintage Story installation"
    echo ""
    echo "See .env.example for correct path examples."
    exit 1
fi

# Check VSDATA is set (optional but recommended)
if [ -z "$VSDATA" ]; then
    warn "VSDATA not set in .env - you won't be able to deploy mods"
    warn "Add: export VSDATA=/path/to/VintagestoryData"
else
    if [ ! -d "$VSDATA" ]; then
        warn "VSDATA directory doesn't exist: $VSDATA"
        warn "Mod deployment will fail until this is fixed"
    elif [ ! -d "$VSDATA/Mods" ]; then
        warn "VSDATA/Mods directory doesn't exist: $VSDATA/Mods"
        warn "Creating it..."
        mkdir -p "$VSDATA/Mods"
        ok "Created $VSDATA/Mods"
    fi
fi

ok "Environment validated"
echo "  VINTAGE_STORY=$VINTAGE_STORY"
[ -n "$VSDATA" ] && echo "  VSDATA=$VSDATA"
exit 0
