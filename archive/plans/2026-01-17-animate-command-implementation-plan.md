# Implementation Plan: `/polis animate` Command

**Date:** 2026-01-17
**Status:** Draft - Awaiting Approval
**Purpose:** Add harness + chat command to trigger animations on bots for testing and future skill integration

---

## Overview

Add a new `animate` command to both the HTTP harness and `/polis` chat interface, allowing:
1. Testing animation codes before integrating them into actions
2. Future skill progression hooks (animation speed tied to per-bot skill level)
3. Manual animation control for debugging/demos

---

## Research Findings (Basis for Design)

### Animation Lifecycle in VS

From vsvillage `AiTaskGotoAndInteract.cs`:
```csharp
// Animations loop by default - check IsAnimationActive to detect completion
if (targetReached) {
    return entity.AnimManager.IsAnimationActive(interactAnim.Code);
}

// Explicit stop required before transition
entity.AnimManager.StopAnimation(animMeta.Code);
entity.AnimManager.StartAnimation(interactAnim);
```

**Key findings:**
- No explicit "loop" property - animations loop until stopped
- `IsAnimationActive(code)` returns false when one-shot animations finish
- Explicit `StopAnimation(code)` required for cleanup
- Multiple animations can blend via `BlendMode`

### AnimationMetaData Properties

From `refs/vsapi/Common/Model/Animation/AnimationMetaData.cs`:
```csharp
public string Code;              // Identifier for stop/check
public string Animation;         // Actual animation name
public float AnimationSpeed;     // Default 1.0f
public float Weight;             // Blending weight
public EnumAnimationBlendMode BlendMode;  // Add, Average, AddAverage
public float EaseInSpeed;        // Transition in (default 10f)
public float EaseOutSpeed;       // Transition out (default 10f)
```

---

## Command Design

### Syntax

**Harness (POST /polis/command):**
```json
{"cmd": "animate", "args": ["hit"], "context": {"playerUid": "..."}}
{"cmd": "animate", "args": ["hit", "1.5"], "context": {"playerUid": "..."}}
{"cmd": "animate", "args": ["hit", "1.0", "loop"], "context": {"playerUid": "..."}}
{"cmd": "animate", "args": ["stop", "hit"], "context": {"playerUid": "..."}}
{"cmd": "animate", "args": ["stop"], "context": {"playerUid": "..."}}
```

**Chat:**
```
/polis animate <animCode> [speed] [loop]
/polis animate stop [animCode]
```

**CLI (poliscli.py):**
```bash
poliscli animate hit
poliscli animate hit --speed 1.5
poliscli animate hit --loop
poliscli animate stop
poliscli animate stop hit
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `animCode` | Yes | - | Animation code (e.g., `hit`, `interact`, `walk`) |
| `speed` | No | `1.0` | Playback speed multiplier (0.5 = half, 2.0 = double) |
| `loop` | No | `false` | If present, animation loops until stopped |

### Stop Variants

| Command | Behavior |
|---------|----------|
| `animate stop` | Stop ALL running animations on selected bot |
| `animate stop <code>` | Stop specific animation by code |

---

## Implementation Details

### 1. File: `PolisBuilderNpcSystem.cs`

#### A. Add case to command switch (~line 1054)

```csharp
case "animate":
    return ExecuteAnimateCommand(args, context);
```

#### B. Add ExecuteAnimateCommand method

Location: After other Execute*Command methods (~line 2200)

```csharp
PolisTestHarness.CommandResult ExecuteAnimateCommand(string[] args, PolisTestHarness.CommandContext context)
{
    // Get selected bot
    if (!TryGetHarnessBot(out var bot, out var err))
    {
        return new PolisTestHarness.CommandResult { Ok = false, Message = err };
    }

    var entity = bot.Entity;
    if (entity == null)
    {
        return new PolisTestHarness.CommandResult { Ok = false, Message = "Bot entity not loaded" };
    }

    // Handle stop command
    if (args.Length >= 1 && args[0].Equals("stop", StringComparison.OrdinalIgnoreCase))
    {
        return ExecuteAnimateStop(entity, args.Length > 1 ? args[1] : null);
    }

    // Validate animation code
    if (args.Length < 1 || string.IsNullOrWhiteSpace(args[0]))
    {
        return new PolisTestHarness.CommandResult
        {
            Ok = false,
            Message = "Usage: animate <animCode> [speed] [loop] | animate stop [animCode]"
        };
    }

    string animCode = args[0].ToLowerInvariant();

    // Parse optional speed
    float speed = 1.0f;
    if (args.Length >= 2 && !args[1].Equals("loop", StringComparison.OrdinalIgnoreCase))
    {
        if (!float.TryParse(args[1], NumberStyles.Float, CultureInfo.InvariantCulture, out speed))
        {
            return new PolisTestHarness.CommandResult { Ok = false, Message = $"Invalid speed: {args[1]}" };
        }
        speed = Math.Clamp(speed, 0.1f, 10f);
    }

    // Parse optional loop flag
    bool loop = args.Any(a => a.Equals("loop", StringComparison.OrdinalIgnoreCase));

    // Apply per-bot speed modifier if available (future skill system hook)
    float finalSpeed = ApplyBotAnimationSpeedModifiers(bot, animCode, speed);

    // Start animation
    var animMeta = new AnimationMetaData
    {
        Code = animCode,
        Animation = animCode,
        AnimationSpeed = finalSpeed,
        BlendMode = EnumAnimationBlendMode.Average
    }.Init();

    bool started = entity.AnimManager.StartAnimation(animMeta);

    if (!started)
    {
        return new PolisTestHarness.CommandResult
        {
            Ok = false,
            Message = $"Failed to start animation '{animCode}' (not found in shape?)"
        };
    }

    // Track looping animations for cleanup
    if (loop)
    {
        TrackLoopingAnimation(bot, animCode);
    }
    else
    {
        // One-shot: schedule stop check
        ScheduleOneShotAnimationStop(bot, animCode);
    }

    string loopNote = loop ? " (looping)" : " (one-shot)";
    string speedNote = finalSpeed != speed ? $" (modified from {speed:F2})" : "";
    return new PolisTestHarness.CommandResult
    {
        Ok = true,
        Message = $"Started animation '{animCode}' speed={finalSpeed:F2}{speedNote}{loopNote}"
    };
}

PolisTestHarness.CommandResult ExecuteAnimateStop(EntityAgent entity, string animCode)
{
    if (string.IsNullOrWhiteSpace(animCode))
    {
        // Stop all - get active animations and stop each
        var active = entity.AnimManager.ActiveAnimationsByAnimCode;
        int count = active.Count;
        foreach (var code in active.Keys.ToList())
        {
            entity.AnimManager.StopAnimation(code);
        }
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Stopped {count} animation(s)"
        };
    }
    else
    {
        entity.AnimManager.StopAnimation(animCode);
        return new PolisTestHarness.CommandResult
        {
            Ok = true,
            Message = $"Stopped animation '{animCode}'"
        };
    }
}
```

#### C. Animation tracking for one-shot cleanup

Add to BotState or manage via scheduled task:

```csharp
// Option 1: Simple delayed check via game tick
void ScheduleOneShotAnimationStop(BotState bot, string animCode)
{
    // Check every 100ms if animation finished, stop it after
    long checkUntil = sapi.World.ElapsedMilliseconds + 10000; // 10s max

    void CheckAnimation(float dt)
    {
        if (bot.Entity == null) return;
        if (sapi.World.ElapsedMilliseconds > checkUntil) return;

        if (!bot.Entity.AnimManager.IsAnimationActive(animCode))
        {
            // Animation finished naturally - cleanup tracking
            return;
        }

        // Still playing, check again
        sapi.Event.RegisterCallback(CheckAnimation, 100);
    }

    sapi.Event.RegisterCallback(CheckAnimation, 100);
}

// Track looping animations in BotState for cleanup
void TrackLoopingAnimation(BotState bot, string animCode)
{
    bot.LoopingAnimations ??= new HashSet<string>();
    bot.LoopingAnimations.Add(animCode);
}
```

#### D. Add to BotState class

```csharp
// In BotState class definition
public HashSet<string> LoopingAnimations;
```

### 2. Add Chat Command

In `RegisterCommands` method (~line 656):

```csharp
cmd.BeginSubCommand("animate")
    .WithDescription("Play an animation on the selected bot")
    .WithArgs(
        parsers.Word("animCodeOrStop"),
        parsers.OptionalWord("speedOrAnimCode"),
        parsers.OptionalWord("loop")
    )
    .HandleWith(CmdAnimate)
    .EndSubCommand();
```

Handler:

```csharp
TextCommandResult CmdAnimate(TextCommandCallingArgs args)
{
    var player = args.Caller.Player as IServerPlayer;
    if (!TryGetPlayerSelectedBot(player, out var bot, out var error))
    {
        return TextCommandResult.Error(error);
    }

    string[] cmdArgs = new string[3];
    cmdArgs[0] = (string)args[0];
    cmdArgs[1] = args[1] as string ?? "";
    cmdArgs[2] = args[2] as string ?? "";

    var result = ExecuteAnimateCommand(
        cmdArgs.Where(a => !string.IsNullOrEmpty(a)).ToArray(),
        new PolisTestHarness.CommandContext { PlayerUid = player.PlayerUID }
    );

    return result.Ok
        ? TextCommandResult.Success(result.Message)
        : TextCommandResult.Error(result.Message);
}
```

### 3. Update Command List

In the error message for unknown commands (~line 1054), add `animate`:

```csharp
result.Message = "Unknown command: " + cmd + ". Available: spawn, select, ..., animate, ...";
```

### 4. CLI Wrapper: `poliscli.py`

Add new command to the CLI wrapper:

```python
@cli.command()
@click.argument('anim_code')
@click.option('--speed', '-s', default=1.0, type=float, help='Animation speed multiplier')
@click.option('--loop', '-l', is_flag=True, help='Loop animation until stopped')
@click.pass_context
def animate(ctx, anim_code, speed, loop):
    """Play an animation on the selected bot.

    Examples:
        poliscli animate hit
        poliscli animate hit --speed 1.5
        poliscli animate interact --loop
        poliscli animate stop
        poliscli animate stop hit
    """
    args = [anim_code]

    # Handle stop command specially
    if anim_code.lower() == 'stop':
        if speed != 1.0:  # speed arg used as animation code for stop
            # This is awkward - may need separate stop command
            pass
        return _post_command(ctx, 'animate', args)

    if speed != 1.0:
        args.append(str(speed))
    if loop:
        args.append('loop')

    return _post_command(ctx, 'animate', args)


@cli.command()
@click.argument('anim_code', required=False)
@click.pass_context
def animstop(ctx, anim_code):
    """Stop animation(s) on the selected bot.

    Examples:
        poliscli animstop        # Stop all animations
        poliscli animstop hit    # Stop specific animation
    """
    args = ['stop']
    if anim_code:
        args.append(anim_code)
    return _post_command(ctx, 'animate', args)
```

**Alternative simpler design** (single command with subcommand-style):

```python
@cli.command()
@click.argument('args', nargs=-1)
@click.option('--speed', '-s', default=None, type=float, help='Animation speed')
@click.option('--loop', '-l', is_flag=True, help='Loop animation')
@click.pass_context
def animate(ctx, args, speed, loop):
    """Play or stop animations on selected bot.

    Usage:
        poliscli animate hit              # One-shot animation
        poliscli animate hit -s 1.5       # With speed
        poliscli animate hit --loop       # Looping
        poliscli animate stop             # Stop all
        poliscli animate stop hit         # Stop specific
    """
    cmd_args = list(args)

    # Don't add speed/loop for stop command
    if not (cmd_args and cmd_args[0].lower() == 'stop'):
        if speed is not None:
            cmd_args.append(str(speed))
        if loop:
            cmd_args.append('loop')

    return _post_command(ctx, 'animate', cmd_args)
```

---

## Animation Speed Modifier API (Per-Bot + Global)

Design for future integration with skill progression:

```csharp
/// <summary>
/// Per-bot animation speed modifiers.
/// Stored in BotState, persisted with bot data.
/// </summary>
public class BotAnimationSpeedModifiers
{
    /// <summary>Base speed multiplier for all animations (default 1.0)</summary>
    public float GlobalMultiplier { get; set; } = 1.0f;

    /// <summary>Per-animation-category multipliers (e.g., "combat" -> 1.2)</summary>
    public Dictionary<string, float> CategoryMultipliers { get; } = new();

    /// <summary>Per-animation-code multipliers (e.g., "hit" -> 1.5)</summary>
    public Dictionary<string, float> AnimationMultipliers { get; } = new();
}

// In BotState class:
public BotAnimationSpeedModifiers AnimSpeedModifiers { get; set; }

// Helper to compute final speed
float ApplyBotAnimationSpeedModifiers(BotState bot, string animCode, float baseSpeed)
{
    var mods = bot.AnimSpeedModifiers;
    if (mods == null) return baseSpeed;

    float result = baseSpeed * mods.GlobalMultiplier;

    // Apply category modifier (future: map animCode -> category)
    string category = GetAnimationCategory(animCode);
    if (category != null && mods.CategoryMultipliers.TryGetValue(category, out float catMod))
    {
        result *= catMod;
    }

    // Apply specific animation modifier
    if (mods.AnimationMultipliers.TryGetValue(animCode, out float animMod))
    {
        result *= animMod;
    }

    return Math.Clamp(result, 0.1f, 10f);
}

string GetAnimationCategory(string animCode)
{
    // Future: map animations to skill categories
    // e.g., "hit", "attack" -> "combat"
    //       "dig", "chop" -> "mining"
    return null; // Not implemented yet
}
```

This allows:
- **Per-bot global modifier:** Bot A is 20% faster at everything
- **Per-bot category modifier:** Bot B has high combat skill, 1.5x combat animations
- **Per-bot specific modifier:** Bot C has mastered the "dig" animation specifically
- **Stacking:** All modifiers multiply together

Future skill system can modify these values:
```csharp
bot.AnimSpeedModifiers.CategoryMultipliers["combat"] = 1.0f + (combatSkillLevel * 0.05f);
```

---

## Available Animation Codes (Reference)

Standard seraph humanoid animations:

| Category | Codes |
|----------|-------|
| Locomotion | `walk`, `run`, `idle`, `stand`, `sit`, `lie`, `crouch` |
| Combat | `hit`, `attack`, `hurt`, `die` |
| Interaction | `interact`, `dig`, `chop`, `use` |
| Movement | `fall`, `climb`, `jump`, `land` |

**Note:** Exact availability depends on the entity's shape JSON. Invalid codes will fail silently or return false from `StartAnimation`.

---

## Testing Checklist

After implementation:

1. **Basic start:**
   ```bash
   curl -X POST http://localhost:8585/polis/command \
     -d '{"cmd":"animate","args":["hit"],"context":{"playerUid":"..."}}'
   ```
   - Verify bot plays hit animation once

2. **Speed modifier:**
   ```bash
   poliscli animate hit --speed 2.0
   ```
   - Verify animation plays at 2x speed

3. **Loop flag:**
   ```bash
   poliscli animate interact --loop
   ```
   - Verify animation loops until stopped

4. **Stop specific:**
   ```bash
   poliscli animate stop interact
   ```

5. **Stop all:**
   ```bash
   poliscli animate stop
   ```

6. **Invalid animation:**
   - Test with nonexistent code, verify graceful error

7. **Chat command parity:**
   - `/polis animate hit`
   - `/polis animate hit 1.5`
   - `/polis animate hit 1.0 loop`
   - `/polis animate stop`

8. **Per-bot speed modifier (future):**
   - Set `bot.AnimSpeedModifiers.GlobalMultiplier = 1.5`
   - Run `animate hit --speed 1.0`
   - Verify final speed is 1.5 (1.0 * 1.5)

---

## Files to Modify

| File | Changes |
|------|---------|
| `PolisBuilderNpcSystem.cs` | Add case, handlers, chat command, speed modifier API |
| `BotState` (in same file or separate) | Add `LoopingAnimations`, `AnimSpeedModifiers` |
| `poliscli.py` | Add `animate` command |
| `docs/CLI.md` | Document new command |
| `docs/SERVER_COMMANDS.md` | Document chat command |

---

## Open Questions / Future Work

1. **Animation blending:** Should starting a new animation auto-stop conflicting ones? (Current: no, uses BlendMode.Average)

2. **Animation events:** Some animations have `damageAtFrame` or `soundAtFrame` attributes. Should we trigger these?

3. **First-person variant:** Some animations have `-fp` variants for first-person view. Relevant for possession mode?

4. **Persistence:** Should looping animations persist across save/load? (Probably not - cleanup on load)

5. **Skill integration timeline:** When will the skill system be implemented to use the speed modifier API?

---

## Approval Checklist

- [ ] Design reviewed
- [ ] Animation codes list verified against actual seraph shape
- [ ] Per-bot speed modifier API approved
- [ ] CLI wrapper design approved
- [ ] Testing plan adequate
