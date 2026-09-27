#!/bin/bash
# build.sh - Build and optionally deploy polis-builder-npc
#
# Usage:
#   ./build.sh           # Build only
#   ./build.sh --deploy  # Build and copy to VSDATA/Mods
#
# This script handles .env sourcing automatically so agents don't forget.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse args first (so --help works without env)
DEPLOY=false
VERBOSE=false
for arg in "$@"; do
    case $arg in
        --deploy|-d)
            DEPLOY=true
            ;;
        --verbose|-v)
            VERBOSE=true
            ;;
        --help|-h)
            echo "Usage: ./build.sh [--deploy] [--verbose]"
            echo "  --deploy, -d   Copy built mod to VSDATA/Mods after building"
            echo "  --verbose, -v  Show environment paths"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

# Validate and source environment (suppress output unless verbose)
if [ "$VERBOSE" = true ]; then
    ./scripts/check-env.sh || exit 1
else
    ./scripts/check-env.sh > /dev/null || exit 1
fi
set -a
source .env
set +a

# Build
echo "Building..."
# Clean the mod output dir first (2026-09-27): dotnet build never removes files
# that fell out of the item lists (a renamed tools/ subdir survived in the
# output and got deployed as dead weight).
rm -rf bin/Release/Mods
dotnet build -c Release -v quiet

if [ "$DEPLOY" = true ]; then
    if [ -z "$VSDATA" ]; then
        echo "ERROR: VSDATA not set, cannot deploy"
        exit 1
    fi
    # 2026-09-21: VS 1.22 only loads user mods from the game directory (the
    # $VSDATA/Mods copy is ignored by 1.22). Deploy to both, game dir authoritative.
    echo "Deploying to game Mods folder..."
    # rm-then-copy (2026-09-27): cp -r never removes stale files - a renamed
    # subdirectory (webui-v2 -> webui) survived the deploy and the harness 404'd.
    if [ -n "$VINTAGE_STORY" ]; then
        rm -rf "$VINTAGE_STORY/Mods/polis-builder-npc"
        cp -r bin/Release/Mods/polis-builder-npc "$VINTAGE_STORY/Mods/"
    fi
    if [ -n "$VSDATA" ]; then
        rm -rf "$VSDATA/Mods/polis-builder-npc"
        cp -r bin/Release/Mods/polis-builder-npc "$VSDATA/Mods/"
    fi
fi

echo "Done."
