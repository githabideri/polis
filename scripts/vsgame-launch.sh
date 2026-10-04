#!/bin/bash
# vsgame-launch.sh — launch Vintage Story; auto-open a world if VSGAME_WORLD
# is set (env from /etc/vsgame.env).
#
# 2026-10-05: --playStyle added. Bare `--openWorld <new>` defaults to
# playStyle "creativebuilding", which auto-creates a flat EMPTY creative
# world (worldgen preset "Empty") — useless for survival testing. Pass a
# real survival preset for standard terrain:
#   preset-surviveandbuild  classic survive-and-build (worldType "standard")
#   preset-exploration      gentler (death keeps inventory, passive mobs)
#   preset-wildernesssurvival / preset-homosapiens  harder
# Deploy: copy this file to /usr/local/bin/vsgame-launch.sh on the game host
# and set VSGAME_WORLD / VSGAME_PLAYSTYLE in the game host's env file.
PLAYSTYLE="${VSGAME_PLAYSTYLE:-preset-surviveandbuild}"
if [ -n "$VSGAME_WORLD" ]; then
  exec /opt/vintagestory/extra/vintagestory/Vintagestory --openWorld "$VSGAME_WORLD" --playStyle "$PLAYSTYLE"
else
  exec /opt/vintagestory/extra/vintagestory/Vintagestory
fi
