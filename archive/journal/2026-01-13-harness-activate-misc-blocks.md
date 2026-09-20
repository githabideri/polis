# 2026-01-13: Harness activation test (lantern/barrel/gate/groundstorage)

## Context

User added a lantern, barrel, wattle gate, and firewood placed on the ground. Goal was to verify `/polis/targets` discovery and `/polis/command activate` behavior for these objects.
Later, user added a quern, lever, storage vessel, and anvil for additional activation tests.

## Actions

1) `/polis/targets` scans (radius 12) for lantern, barrel, gate, and groundstorage.
2) `/polis/command activate` using explicit coordinates for each block.
3) Repositioned the bot next to the lantern and retried activation.
4) Bot-anchored `/polis/targets` scans for quern, storage vessel, anvil, and lever/valve.
5) `/polis/command activate` for quern, storage vessel, anvil, wattle gate (toggle twice), and valve lever.
6) Re-tested lantern activation twice to check toggle behavior.

## Results

- Lantern detected as `game:lantern-south` with `EntityClass: Lantern`, but activation failed with `No line of sight to target.`
- Lantern activation succeeded after moving the bot south of the lantern and back north to face it.
- Barrel activation succeeded (`game:barrel`, `EntityClass: Barrel`).
- Wattle gate activation succeeded twice (toggle open/close) on `game:wattlegate-sticks-n-closed-left-free`.
- Firewood on the ground appeared as `game:groundstorage` with `EntityClass: GroundStorage`.
- Firewood activation appeared to transfer the stack into the **player** hotbar (user observation), which is not ideal for bot-only operations.
- `LastAction` did not reflect lantern LOS failure; only the command response showed the failure.
- Quern, storage vessel, and anvil activation succeeded via explicit coords.
- “Iron pipe valve trip lever” was not found via `q=lever`, but appears as `game:jonas-steamengine-valve1-west` and is discoverable via `q=valve`.
- Valve lever activation failed LOS at first, then succeeded after repositioning the bot adjacent to it.
- Lantern activation succeeded twice in a row; user confirmed it does **not** toggle light on/off.

## Evidence

- Harness outputs recorded in `docs/TESTING_HARNESS_OUTPUTS.md` (lantern/barrel/gate/groundstorage sections).
- Additional outputs recorded in `docs/TESTING_HARNESS_OUTPUTS.md` (lantern bot scan, quern/vessel/anvil/gate sections).
- Raw command responses (local capture):
  - `/tmp/polis-harness-tests/cmd-activate-lantern.json`
  - `/tmp/polis-harness-tests/cmd-activate-barrel.json`
  - `/tmp/polis-harness-tests/cmd-activate-gate.json`
  - `/tmp/polis-harness-tests/cmd-activate-groundstorage.json`
  - `/tmp/polis-harness-tests/cmd-activate-lantern-3.json`
  - `/tmp/polis-harness-tests/cmd-activate-quern.json`
  - `/tmp/polis-harness-tests/cmd-activate-vessel.json`
  - `/tmp/polis-harness-tests/cmd-activate-anvil.json`

## Open Questions

- Lantern LOS: do we need broader hit testing for hanging/partial blocks, or a separate activation path for block entities?
- Ground storage contents: should `/polis/targets` optionally include a summarized content list for `GroundStorage` blocks?
- Lever discovery: is the lever outside scan radius, or does it use a different code/behavior that the `q` filters miss?
- Lantern toggle confirmed: activation does not switch the light on/off.

## Implications for harness design

- Command responses must be treated as the primary error signal when a command fails before an action starts.
- When testing “items on the ground,” use both entity scans and block scans; ground storage blocks will not match item-name queries.
- Consider a bot-only activation path for container-like blocks to avoid opening or transferring to the player inventory.
