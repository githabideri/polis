# Polis CLI Implementation

**Date:** 2026-01-17

## Summary

Implemented `poliscli.py`, a Python CLI wrapper for the HTTP test harness designed for ergonomic LLM/agent use.

## Files Created/Modified

| File | Action | Purpose |
|------|--------|---------|
| `scripts/poliscli.py` | Created | Main CLI (~900 lines) |
| `docs/CLI.md` | Created | Full usage documentation |
| `docs/TESTING_HARNESS.md` | Modified | Added CLI reference section |
| `CLAUDE.md` | Modified | Added mock data guidelines |

## Features Implemented

### Commands (26 total)

**Query Commands:**
- `status` - Server readiness check
- `players` - List online players
- `player` - Get player info
- `bots` - List all bots
- `state` - Get bot state + inventory
- `targets` - Nearby interactables
- `look` - Player look target (raytrace)

**Action Commands:**
- `spawn` - Spawn new bot
- `select` - Select bot by ID
- `despawn` - Despawn selected bot
- `goto` - Move to coordinates (with `--wait`)
- `stop` - Cancel activity
- `give` - Give item to bot
- `drop` - Drop from hand
- `pickup` - Pick up nearby item
- `activate` - Activate block
- `mine` - Mine block (with `--wait`)
- `harvest` - Harvest block (with `--wait`)
- `harvestcrop` - Harvest farmland crop
- `takefrom` - Take from container
- `putinto` - Put into container
- `butcher` - Butcher dead entity
- `possess` - Mount player onto bot
- `unpossess` - Unmount player
- `controls` - Set movement controls
- `exec` - Raw server command

### Global Flags

```
--host HOST        Harness host (default: localhost)
--port PORT        Harness port (default: 8585)
--player UID       Player UID (overrides $POLIS_PLAYER_UID)
--bot ID           Bot ID (overrides $POLIS_BOT_ID)
--json             Force JSON output
--quiet, -q        Minimal output
--verbose, -v      Debug output
--tokens, -t       Show token count comparison
--timeout SEC      Wait timeout (default: 30)
```

### Output Formats

1. **TOON** (default) - Compact format, ~25-32% token savings
2. **JSON** (`--json`) - Standard JSON for debugging
3. **Quiet** (`-q`) - Minimal OK/FAIL output

### Token Counting (`--tokens`)

Shows actual token comparison using tiktoken:
```
--- tokens: 92 (TOON) | JSON: 123 | TOON: 92 | savings: 25.2% ---
```

## Preliminary Test Results

### Tested & Working

| Command | Test | Result |
|---------|------|--------|
| `--help` | Main + subcommands | OK |
| `status` | Default, `--json`, `-q`, `-t` | OK |
| `players` | Default (TOON) | OK |
| `bots` | Default, `--json`, `-q`, `-t` | OK |
| `state` | Default, `--json`, `--bot ID`, `-t` | OK |
| `spawn` | Default (near player) | OK - Bot #412 created |
| `select` | By ID | OK |
| `give` | Item to bot | OK - stone-granite |
| `drop` | From hand | OK |
| `pickup` | Nearby item | OK (with 2s delay for CanCollect) |

### Token Savings Measured

| Command | JSON | TOON | Savings |
|---------|------|------|---------|
| `status` | 75 | 51 | 32.0% |
| `state` | 123 | 92 | 25.2% |
| `bots` (3 bots) | 231 | 178 | 22.9% |

### Not Yet Tested

- `goto --wait` - Movement with arrival wait
- `mine`, `harvest`, `harvestcrop` - Timed actions
- `activate` - Block activation
- `takefrom`, `putinto` - Container interaction
- `butcher` - Entity butchering (blocked on knife item code)
- `possess`, `unpossess`, `controls` - Possession system
- `targets`, `look` - Discovery queries
- Environment variable defaults
- Connection error handling
- Exit codes in failure scenarios

### Known Issues

1. **Knife item code resolved** - Correct format is `game:knife-generic-{material}` (e.g., `game:knife-generic-copper`). The `generic` type identifier is required. Other types: `dagger`, `stiletto`, `khanjar`, `baselard`.

2. **Butcher range check** - Butcher failed with "Target too far: 23.6 > 4.5" because chicken wandered away before being killed, leaving corpse out of range.

## Dependencies

- **Required:** Python 3.8+ stdlib only
- **Optional:**
  - `python-toon` - TOON output format (falls back to JSON)
  - `tiktoken` - Token counting for `--tokens` flag

Install optional deps:
```bash
pip install --user python-toon tiktoken
```

## Next Steps

### Testing Priorities

1. **Knife item code resolution** - Find correct item code for butcher testing
2. **Timed action commands** - Test `mine`, `harvest`, `harvestcrop` with `--wait`
3. **Movement commands** - Test `goto --wait` arrival detection
4. **Container commands** - Test `takefrom`, `putinto` workflow
5. **Error handling** - Test connection errors, invalid args, exit codes
6. **Environment variables** - Verify `POLIS_PLAYER_UID`, `POLIS_BOT_ID` work

### CLI Refinements

1. **Composite commands** - Consider adding convenience commands as patterns emerge
2. **Output filtering** - Add `--fields` to select specific output fields
3. **Batch mode** - Consider stdin command reading for scripted workflows
4. **Shell completion** - Add bash/zsh completion scripts
5. **Alias setup** - Document `alias polis='./scripts/poliscli.py'` in CLI.md

### Documentation

1. Update CLI.md with correct knife item code once found
2. Add more workflow examples based on testing
3. Document common error messages and solutions
