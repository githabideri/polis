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
dotnet build -c Release -v quiet

if [ "$DEPLOY" = true ]; then
    if [ -z "$VSDATA" ]; then
        echo "ERROR: VSDATA not set, cannot deploy"
        exit 1
    fi
    echo "Deploying to Mods folder..."
    cp -r bin/Release/Mods/polis-builder-npc "$VSDATA/Mods/"
fi

echo "Done."
