# /polis/targets Output Structure

This document describes the `/polis/targets` endpoint output so agents can
discover nearby interactables reliably and keep outputs manageable.

## Endpoint
`GET /polis/targets?playerUid=<uid>&botId=<id>&radius=6&limit=20&mode=blocks|entities|all&q=&codeContains=&requireEntityClass=`

Parameters:
- `playerUid` (required unless `botId` is provided): anchor player for the scan (bootstrap when no bot yet).
- `botId` (optional): anchor bot for the scan (overrides `playerUid`; preferred once a bot exists).
- `radius` (float, default 6, clamped to 1..32): scan radius around player.
- `limit` (int, default 20, clamped to 1..200): max entries returned per list.
- `mode` (default `blocks`): `blocks`, `entities`, or `all`.
- `q` (optional): case-insensitive substring match across block/entity metadata. CLI uses `--search/-s` flag.
- `codeContains` (optional): comma-separated substrings matched against block/ entity code.
- `requireEntityClass` (optional, default false): when true, only returns blocks with `EntityClass`.

## Response Shape
Top-level fields:
- `Ok`: success flag.
- `Center`: player position (server-absolute).
- `Radius`: applied scan radius.
- `Blocks`: list of candidate blocks (if `mode` includes blocks).
- `Entities`: list of nearby non-player entities (if `mode` includes entities).

### Block Entry Fields
- `Pos`: block position `[x, y, z]`.
- `Code`: block code (e.g., `game:door-solid-oak`).
- `Dist`: distance from `Center` to block center.
- `EntityClass`: block entity class if present.
- `PlacedPriorityInteract`: whether block interaction priority is set.
- `Behaviors`: block behavior type names (if any).
- `Reasons`: why this block was included (`EntityClass`, `BlockBehaviors`, `PlacedPriorityInteract`).

### Entity Entry Fields
- `Id`: entity id.
- `Code`: entity code (e.g., `polis-builder-npc:polisbot`, `game:item-...`).
- `Class`: entity class name.
- `Pos`: entity position `[x, y, z]`.
- `Dist`: distance from `Center`.
- `ItemCode`: item stack code if the entity is an item entity.
- `ItemQty`: stack size if the entity is an item entity.

Notes:
- The entity list includes **any non-player entity** within range (items, bots,
  animals, etc.).
- The block list uses **heuristics** and will include non-interactive blocks
  that simply carry behaviors (e.g., soil). Filter by code or reasons.

## Example (chair, door, chest within radius 6)
```json
{
  "Ok": true,
  "Center": [224.4129638671875, 3.00006103515625, 271.23992919921875],
  "Radius": 6,
  "Blocks": [
    {
      "Pos": [224, 3, 270],
      "Code": "game:chest-east",
      "Dist": 0.9,
      "EntityClass": "GenericTypedContainer",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorContainer",
        "BlockBehaviorCarryableInteract",
        "BlockBehaviorCarryable",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": ["EntityClass", "BlockBehaviors"]
    },
    {
      "Pos": [223, 3, 268],
      "Code": "game:door-solid-oak",
      "Dist": 2.93,
      "EntityClass": "Generic",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorDoor",
        "BlockBehaviorBlockEntityInteract",
        "BlockBehaviorCarryableInteract",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": ["EntityClass", "BlockBehaviors"]
    },
    {
      "Pos": [224, 3, 267],
      "Code": "game:chair-plain",
      "Dist": 3.77,
      "EntityClass": null,
      "PlacedPriorityInteract": false,
      "Behaviors": ["BlockBehaviorUnstableFalling", "BlockBehaviorReinforcable"],
      "Reasons": ["BlockBehaviors"]
    }
  ],
  "Entities": []
}
```

## Filter Examples

### Filter by code + requireEntityClass (exclude chair/soil)
Request:
`/polis/targets?playerUid=<uid>&radius=6&limit=20&mode=blocks&requireEntityClass=true&codeContains=chest,door`

Response (trimmed):
```json
{
  "Ok": true,
  "Center": [224.96697998046875, 3.00006103515625, 271.72979736328125],
  "Radius": 6,
  "Blocks": [
    {
      "Pos": [224, 3, 270],
      "Code": "game:chest-east",
      "Dist": 1.41,
      "EntityClass": "GenericTypedContainer"
    },
    {
      "Pos": [223, 3, 268],
      "Code": "game:door-solid-oak",
      "Dist": 3.58,
      "EntityClass": "Generic"
    }
  ],
  "Entities": []
}
```

### Bot-anchored scan + text query (q)
Request:
`/polis/targets?botId=191&radius=6&limit=20&mode=blocks&q=chest`

Response (trimmed):
```json
{
  "Ok": true,
  "Center": [224.49187330574776, 3.0001, 269.3790022207],
  "Radius": 6,
  "Blocks": [
    {
      "Pos": [224, 3, 270],
      "Code": "game:chest-east",
      "Dist": 1.23
    }
  ],
  "Entities": []
}
```

### Item entity example (q matches ItemCode)
Request:
`/polis/targets?botId=191&radius=6&limit=20&mode=entities&q=stone`

Response (trimmed):
```json
{
  "Ok": true,
  "Center": [224.49187330574776, 3.0001, 269.3790022207],
  "Radius": 6,
  "Blocks": [],
  "Entities": [
    {
      "Id": 195,
      "Code": "game:item",
      "Class": "EntityItem",
      "Pos": [226.1991751540966, 3.0001, 270.1986360804114],
      "Dist": 1.89,
      "ItemCode": "game:stone-granite",
      "ItemQty": 1
    }
  ]
}
```

### Harvestable bush example
Request:
`/polis/targets?botId=191&radius=8&limit=5&mode=blocks&q=bush`

Response (trimmed):
```json
{
  "Ok": true,
  "Blocks": [
    {
      "Code": "game:bigberrybush-redcurrant-ripe",
      "EntityClass": "BerryBush",
      "Behaviors": [
        "BlockBehaviorHarvestable",
        "HarvestMarkerBehavior",
        "BlockBehaviorReinforcable"
      ]
    }
  ]
}
```

## Output Size + Agent Guidance
Large responses happen when:
- `limit` is high (e.g., 200), and
- many nearby blocks carry behaviors (common for soil/rock).

For agent use:
1) Start with `limit=20` and `radius=6`.
2) Filter via `q` or `codeContains` (e.g., `q=chest`, `codeContains=door,gate`).
3) Prefer `botId` scans once a bot exists; use `playerUid` only to bootstrap.
4) Use `/polis/command` `activate` with those coords.
5) If a target is in view, prefer `useLookTarget` for exact selection.
6) For item entities, use `q` or `codeContains` to match `ItemCode`.

## CLI Usage

The `poliscli.py` CLI wraps the HTTP API:

```bash
# Search for blocks by name
./scripts/poliscli.py targets -s chest --radius 16

# Search for ores
./scripts/poliscli.py targets -s ore --radius 32

# Exclude natural terrain blocks
./scripts/poliscli.py targets --exclude-natural --radius 20
```

**Note:** Use `--search/-s` for the search parameter (maps to HTTP `?q=`).

## Known Issue: Ore Naming Mismatch

Vintage Story uses real-world mineral names for ores, which don't always match player expectations:

| Player Term | Actual Block Code Pattern |
|-------------|---------------------------|
| iron ore | `ore-*-limonite-*`, `ore-*-magnetite-*`, `ore-*-hematite-*` |
| copper ore | `ore-*-malachite-*`, `ore-*-nativecopper-*` |
| tin ore | `ore-*-cassiterite-*` |
| gold ore | `ore-*-nativegold-*` |
| silver ore | `ore-*-nativesilver-*`, `ore-*-galena-*` |

**Workaround:** Search for the mineral name (`-s limonite`) or use generic term (`-s ore`) and filter results.
