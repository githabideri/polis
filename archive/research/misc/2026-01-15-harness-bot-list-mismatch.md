# Harness Bot List Mismatch

## Summary

The HTTP harness endpoint `GET /polis/bots` can return an empty list even when
bots are present and selectable in-game. At the same time, `/polis list` executed
via `POST /polis/servercmd` returns the active bot IDs and positions. This makes
automation that relies on `/polis/bots` incomplete and can leave bots behind
during cleanup.

## Evidence

- In-game: bots were visible/selectable (e.g., bot #315).
- `GET /polis/bots`: returned no bots.
- `POST /polis/servercmd` with `{"cmd":"/polis list","playerUid":"<uid>"}` returned
  bot IDs and positions.

## Impact

- Automation cleanup that uses only `/polis/bots` fails to remove all bots.
- Agent test scripts can incorrectly assume there are no bots.

## Notes / Follow-up

- Determine why `/polis/bots` and `/polis list` diverge (different data sources
  or different notions of "loaded" vs "registered").
- Decide which endpoint should be authoritative for automation.
