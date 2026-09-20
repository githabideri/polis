# Research: Entity Interaction Primitive & Command

## Context
Goal: Wire the `PolisInteractEntityAction` primitive into the `/polis` chat command system and determine the optimal `hitPosition` for the `OnInteract` call.

## 1. Command Wiring
The interaction primitive should be exposed via a new subcommand in `PolisBuilderNpcSystem.cs`.

### Registration
```csharp
cmd.BeginSubCommand("interactentity")
    .WithDescription("Interact with an entity (e.g. shear, milk, trade)")
    .WithArgs(parsers.Long("id"), parsers.OptionalWord("mode"))
    .HandleWith(CmdInteractEntity)
    .EndSubCommand();
```

### Handler Implementation (`CmdInteractEntity`)
The handler should perform the following steps:
1. **Selection:** Use `TryGetSelectedBot(player, out var bot, out var error)` to find the active NPC.
2. **Mode Parsing:** Parse the optional `mode` string into `EnumInteractMode`. 
   - Default: `EnumInteractMode.Interact`.
   - Supported: `Interact` (Right Click), `Attack` (Left Click).
3. **Execution:** Pass the parsed ID and mode into a new `PolisInteractEntityAction` and execute via `StartSingleAction`.

## 2. Hit Position Selection
The native `Entity.OnInteract` method requires a `Vec3d hitPosition`.

### Recommendation
Use the **geometric center** of the target entity's selection box. This ensures the interaction point is always valid regardless of the entity's size, scale, or current orientation.

```csharp
// Logic for PolisInteractEntityAction.Start
var hitPos = new Vec3d(
    (target.SelectionBox.X1 + target.SelectionBox.X2) / 2.0,
    (target.SelectionBox.Y1 + target.SelectionBox.Y2) / 2.0,
    (target.SelectionBox.Z1 + target.SelectionBox.Z2) / 2.0
);
```

### Technical Detail
In Vintage Story, `hitPosition` for entity interactions is generally treated as **relative to the entity's position** (`target.Pos.XYZ`). Using the center of the selection box is the most reliable fallback when precise ray-tracing isn't available.

## 3. Primitives & Dependencies
- **Dependency:** Requires `PolisInteractEntityAction.cs`.
- **Range:** Normal interaction range is ~4.5 blocks. The action should ideally verify distance before calling `OnInteract` to avoid "ghost" interactions.
