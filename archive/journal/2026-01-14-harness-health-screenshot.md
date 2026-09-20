# 2026-01-14: Harness health + screenshot

## Context
User observed polisbot taking hits in creative mode without dying. Added
health visibility in `/polis/state` and a local screenshot trigger to support
visual verification.

## Changes
- `/polis/state` now reports `CurrentHealth` and `MaxHealth` for the bot.
## Attempted (failed)
- Tried a `POST /polis/screenshot` endpoint via `xdotool`/`flatpak-spawn`. It
  fails in the Flatpak sandbox due to host portal restrictions and working
  directory issues. Removed for now.

## Notes
- Creative playstyle can make killing entities unintuitive. Use survival mode
  when validating bot death or check health via the harness.
- Screenshot automation still needs a client-side hook or a trusted external
  automation path; revisit later.
