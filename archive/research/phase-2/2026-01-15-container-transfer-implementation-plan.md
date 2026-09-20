# Container Transfer Implementation Plan

**Date:** 2026-01-15
**Phase:** Phase 2 (Task/Job System)
**Feature:** Container Transfer Actions (takefrom / putinto)

## Overview

Implementation of server-side container transfer actions using EntityActivitySystem. Bots can withdraw items from containers and deposit items into containers, with full validation (range, claims, block interface).

---

## Architecture

### Design Pattern
Two separate atomic actions following existing pattern (PolisPickupItemAction, PolisDropItemAction):
- **PolisContainerTakeAction** - withdraw from `IBlockEntityContainer` → bot inventory
- **PolisContainerPutAction** - withdraw from bot inventory → `IBlockEntityContainer`

Both actions are executed by the bot's `EntityActivitySystem` and can be wrapped in goto actions if out of range.

### Validation Flow
```
User command (harness/CLI)
  ↓
CmdTakeFrom / CmdPutInto (parse args, resolve owner player)
  ↓
PolisContainerTakeAction / PolisContainerPutAction (Start method)
  ├─ Range check (≤ 4.5 blocks to container center)
  ├─ Block exists + has container interface (IBlockEntityContainer)
  ├─ Claims check (Use flag via owner player)
  ├─ Bot has EntityBehaviorSeraphInventory
  ├─ Source/dest slot validation (non-empty for put, valid index for take)
  ├─ Transfer execution (ItemSlot operations + dirty calls)
  └─ Result callback with success/failure + message
```

---

## Deliverables

### 1. PolisContainerTakeAction.cs

**File:** `PolisContainerTakeAction.cs` (new file)
**Location:** Root directory (alongside PolisPickupItemAction.cs, PolisDropItemAction.cs)
**Lines:** ~150

**Constructor:**
```csharp
public PolisContainerTakeAction(
    BlockPos targetPos,
    int containerSlotIndex,
    int qty,
    IServerPlayer ownerPlayer,
    float range,
    Action<string> debugLog
)
```

**Key Members:**
- `targetPos`: BlockPos of container
- `containerSlotIndex`: Which slot in container (0-based)
- `qty`: How many to take (0 = all)
- `ownerPlayer`: Player who owns the bot (for claims check)
- `range`: Maximum distance (default 4.5f)
- `debugLog`: Optional debug callback

**Start() Logic:**
1. Safety: validate actor is EntityAgent
2. Range check: distance to block center ≤ range
3. Block check: block exists (id ≠ 0)
4. Container check: cast to `IBlockEntityContainer`, has inventory
5. Claims check: `world.Claims.TestAccess(ownerPlayer, targetPos, EnumBlockAccessFlags.Use)` → deny if `Denied`
6. Bot inventory: get `EntityBehaviorSeraphInventory`, check not null
7. Transfer:
   - Get slot: `containerInv[containerSlotIndex]`
   - Check not empty
   - Call `PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out moved, ...)`
   - If succeeded:
     - Decrement container slot: `containerSlot.Itemstack.StackSize -= moved`
     - Null if empty: `if (StackSize <= 0) containerSlot.Itemstack = null`
     - Mark dirty: `containerSlot.MarkDirty()`
     - Block entity dirty: `(blockEntity as BlockEntity).MarkDirty(true)`
8. Result callback: invoke with (ok, message)

**Validation Messages:**
- "actor is not an agent"
- "out of range dist=X.XX range=Y.YY"
- "no block at target position"
- "block is not a container (is game:stone-granite)"
- "container has no inventory"
- "access denied by land claim"
- "bot has no seraph inventory"
- "container slot X is empty"
- "could not transfer any items"
- "transferred N items from container to bot"

---

### 2. PolisContainerPutAction.cs

**File:** `PolisContainerPutAction.cs` (new file)
**Location:** Root directory
**Lines:** ~160

**Constructor:**
```csharp
public PolisContainerPutAction(
    BlockPos targetPos,
    int botSlotIndex,
    int qty,
    IServerPlayer ownerPlayer,
    float range,
    Action<string> debugLog
)
```

**Key Members:** Same as Take, except:
- `botSlotIndex`: Which bot slot to take from (0=right hand, 1=left hand, ≥2 for backpack)

**Start() Logic:**
1. Safety: validate actor is EntityAgent
2. Range check: same as Take
3. Block check: same as Take
4. Container check: same as Take
5. Claims check: same as Take (Use flag)
6. Bot inventory: get `EntityBehaviorSeraphInventory`
7. Bot slot: resolve from index:
   - `0` → `agent.RightHandItemSlot`
   - `1` → `agent.LeftHandItemSlot`
   - `≥2` → `invbh.Inventory[slotIndex]` (backpack)
   - Check: slot not null, not empty
8. Transfer:
   - Get qty to put: clamp to available in slot
   - Iterate container slots until done:
     - For each slot: `sourceSlot.TryPutInto(containerSlot, ref op)`
     - If moved > 0: mark slot dirty
   - After loop: mark block entity dirty: `(blockEntity as BlockEntity).MarkDirty(true)`
9. Result callback: invoke with (ok, message)

**Validation Messages:**
- (Range, block, container, claims, bot inventory checks: same as Take)
- "invalid slot index X (use 0=right, 1=left, 2+=backpack)"
- "right hand is empty" / "left hand is empty" / "slot X is empty"
- "could not transfer any items"
- "transferred N items from bot to container"

---

### 3. CmdTakeFrom Handler

**Location:** `PolisBuilderNpcSystem.cs`, method `CmdTakeFrom`
**Lines:** ~50

**Signature:**
```csharp
TextCommandResult CmdTakeFrom(TextCommandCallingArgs args)
```

**Parse:**
```csharp
var player = args.Caller.Player as IServerPlayer;
if (player == null) return TextCommandResult.Error("Server player required");
if (!TryGetSelectedBot(player, out var bot, out var error)) return error;

var pos = ((Vec3d)args.Parsers[0].GetValue()).AsBlockPos;
int slotIndex = (int)args.Parsers[1].GetValue();
int qty = args.Parsers[2].IsMissing ? 0 : (int)args.Parsers[2].GetValue();
```

**Get Owner Player:**
```csharp
BotRecord botRecord = globalData.Bots[bot.Entity.EntityId];
IServerPlayer ownerPlayer = sapi.World.PlayerByUid(botRecord.OwnerUid) as IServerPlayer;
if (ownerPlayer == null)
    return TextCommandResult.Error("Bot owner is offline or unknown");
```

**Create & Start Action:**
```csharp
var action = new PolisContainerTakeAction(
    pos,
    slotIndex,
    qty,
    ownerPlayer,
    DefaultActionRange,
    debugEnabled ? msg => LogDebug(player, msg) : null
);

bot.Activity.Queue(action);
LogDebug(player, $"takefrom queued: pos={FormatBlockPos(pos)} slot={slotIndex} qty={qty}");
return TextCommandResult.Success("takefrom started");
```

---

### 4. CmdPutInto Handler

**Location:** `PolisBuilderNpcSystem.cs`, method `CmdPutInto`
**Lines:** ~50

**Signature:**
```csharp
TextCommandResult CmdPutInto(TextCommandCallingArgs args)
```

**Parse & Execute:** (Same structure as CmdTakeFrom, create PolisContainerPutAction instead)

---

### 5. Command Registration

**Location:** `PolisBuilderNpcSystem.cs`, method `RegisterCommands()`
**Lines:** ~20

**Add to command registration:**
```csharp
cmd.BeginSubCommand("takefrom")
    .WithDescription("Take items from a container at position")
    .WithArgs(parsers.WorldPosition("pos"), parsers.Int("slot"), parsers.OptionalInt("qty"))
    .HandleWith(CmdTakeFrom)
    .EndSubCommand();

cmd.BeginSubCommand("putinto")
    .WithDescription("Put items into a container at position")
    .WithArgs(parsers.WorldPosition("pos"), parsers.Int("slot"), parsers.OptionalInt("qty"))
    .HandleWith(CmdPutInto)
    .EndSubCommand();
```

---

## Implementation Steps (Order)

1. **Create PolisContainerTakeAction.cs**
   - Copy structure from PolisPickupItemAction.cs
   - Implement validation chain
   - Implement transfer logic with container slot iteration
   - Test compilation

2. **Create PolisContainerPutAction.cs**
   - Copy structure from PolisDropItemAction.cs
   - Implement validation chain
   - Implement slot resolution + transfer logic
   - Test compilation

3. **Add CmdTakeFrom to PolisBuilderNpcSystem.cs**
   - Implement handler
   - Test parse + bot selection

4. **Add CmdPutInto to PolisBuilderNpcSystem.cs**
   - Implement handler
   - Test parse + bot selection

5. **Register commands in RegisterCommands()**
   - Add BeginSubCommand blocks
   - Verify syntax

6. **Build project**
   ```bash
   cd /home/mf/Code/polis-builder/polis-builder-npc
   dotnet build -c Release
   ```
   - Fix any compiler errors
   - Verify no IL errors in output

7. **Deploy mod**
   ```bash
   cp -r bin/Release/Mods/polis-builder-npc ../vsdata/Mods/
   ```

8. **Restart VS server**
   - Wait for `[polis] Test harness started on port 8585`

9. **Run tests** (per `2026-01-15-container-transfer-test-plan.md`)

---

## Code Pattern Reference

### Similar Existing Actions

**PolisPickupItemAction.cs** - withdraw from EntityItem
- Range check pattern (line 56-61)
- Null validation pattern (line 28-47)
- MarkDirty pattern (line 103, 107)
- Result callback pattern (line 96, 104)

**PolisDropItemAction.cs** - insert into world
- Slot resolution pattern (line 54-77)
- Inventory helpers usage (line 108)
- MarkDirty + persist pattern (line 107-108)

**PolisInteractEntityAction.cs** - entity interaction validation
- NormalizeHitPos helper (if needed for container)
- Range check with formatted output (line 59-66)

**PolisActivateBlockAction.cs** - block activation
- BlockSelection creation pattern (line 3902-3908)
- Range check pattern (line 3883-3890)
- Claims check pattern (N/A in activate, but available in validate command)

### Claims Check Pattern

From `/polis validate` command (PolisBuilderNpcSystem.cs ~line 2741):
```csharp
var claimResponse = sapi.World.Claims?.TestAccess(player, pos, accessFlag) ?? EnumWorldAccessResponse.Granted;
if (claimResponse == EnumWorldAccessResponse.Denied)
{
    // deny action
}
```

**Key:** Use `TestAccess` (not `TryAccess`) to avoid sending error packets server-side.

### Inventory Helpers Pattern

From existing actions (pickup, give):
```csharp
if (PolisInventoryHelpers.TryInsertIntoBotInventory(agent, stack, out int moved, out string insertError, debugLog))
{
    // success
    invbh.storeInv();  // if modifying direct slots, call this
}
```

---

## Considerations

### Owner Player Null Case
If bot owner is offline, deny action:
```csharp
if (ownerPlayer == null)
    return error; // in command handler
```
Actions will not execute if owner is null (safer than allowing offline access).

### Claims with No Claims System
If `world.Claims` is null (no claims mod active), automatically grant:
```csharp
if (world.Claims != null)
{
    var response = world.Claims.TestAccess(ownerPlayer, targetPos, EnumBlockAccessFlags.Use);
    if (response == EnumWorldAccessResponse.Denied)
        deny();
}
// else: no claims system, proceed
```

### Partial Transfer Success
If container slot has 5 items and we request `qty=3`, but bot inventory only has room for 2:
- Result: transfer 2 items, report success "transferred 2 items"
- Container slot now has 3 remaining
- Bot inventory has 2 new items
- This is correct behavior (partial success)

### Empty Container Handling
If container slot is empty (null), takefrom fails with "slot is empty". This prevents errors from null stack operations.

### Backpack Slot Support
PutInto supports `slotIndex >= 2` for backpack slots. However:
- Slots 17-18 are ItemSlotBackpack (bag container items)
- Contents stored in ItemStack.Attributes["backpack"]
- Full support deferred (bag content handling complex)
- For now: only support hand slots (0-1)
- Return error: "slot X not supported (use 0=right, 1=left)"

---

## Files Modified

| File | Changes |
|------|---------|
| `PolisContainerTakeAction.cs` | **NEW** ~150 lines |
| `PolisContainerPutAction.cs` | **NEW** ~160 lines |
| `PolisBuilderNpcSystem.cs` | +CmdTakeFrom (+50), +CmdPutInto (+50), RegisterCommands (+20) |
| `docs/research/INDEX.md` | Add reference to this plan |

**Total new code:** ~430 lines

---

## Testing

See: `docs/research/phase-2/2026-01-15-container-transfer-test-plan.md`

12 step-by-step tests covering:
- Success cases (putinto, takefrom)
- Failure cases (out of range, empty slot)
- State verification via harness

---

## References

- **Inventory Model:** `docs/research/phase-2/2026-01-06-bot-inventory-research.md`
- **Container Transfer Research:** `docs/research/phase-2/2026-01-14-container-transfer-correctness.md`
- **Claims Enforcement:** `docs/research/misc/2026-01-13-claims-enforcement-patterns.md`
- **GroundStorage Access:** `docs/research/misc/2026-01-13-groundstorage-contents-access.md`
- **Bot Inventory Sync:** `docs/research/phase-2/2026-01-14-bot-inventory-sync-flow.md`
