using Vintagestory.API.Server;
using Vintagestory.API.Common;

namespace PolisBuilderNpc.Commands;

/// <summary>
/// Registers all /polis chat commands and their subcommands.
/// Command handlers remain in PolisBuilderNpcSystem since they need system state.
/// </summary>
internal static class PolisCommandRegistry
{
    internal static void RegisterCommands(ICoreServerAPI api, PolisBuilderNpcSystem system)
    {
        var parsers = api.ChatCommands.Parsers;
        var cmd = api.ChatCommands.Create("polis")
            .WithDescription("Polis NPC control (polisbot)")
            .RequiresPrivilege(Privilege.chat)
            .RequiresPlayer();

        cmd.BeginSubCommand("spawn")
            .WithDescription("Spawn a polisbot (profession or entity code: laborer, miner, lumberjack, builder, farmer, hunter, smith, knapper)")
            .WithArgs(parsers.OptionalWord("profession_or_entitycode"))
            .HandleWith(system.CmdSpawn)
            .EndSubCommand();

        cmd.BeginSubCommand("list")
            .WithDescription("List tracked bots")
            .HandleWith(system.CmdList)
            .EndSubCommand();

        cmd.BeginSubCommand("select")
            .WithDescription("Select a bot by entity id")
            .WithArgs(parsers.Long("id"))
            .HandleWith(system.CmdSelect)
            .EndSubCommand();

        cmd.BeginSubCommand("selectlook")
            .WithDescription("Select the bot you are looking at")
            .HandleWith(system.CmdSelectLook)
            .EndSubCommand();

        cmd.BeginSubCommand("despawn")
            .WithDescription("Despawn the selected bot")
            .HandleWith(system.CmdDespawn)
            .EndSubCommand();

        cmd.BeginSubCommand("goto")
            .WithDescription("Move bot to a world position")
            .WithArgs(parsers.WorldPosition("pos"), parsers.OptionalBool("astar"), parsers.OptionalFloat("speed"), parsers.OptionalBool("fallback"))
            .HandleWith(system.CmdGoto)
            .EndSubCommand();

        cmd.BeginSubCommand("gotolook")
            .WithDescription("Move bot toward your look direction (ray trace)")
            .WithArgs(parsers.OptionalFloat("range"), parsers.OptionalBool("astar"), parsers.OptionalFloat("speed"), parsers.OptionalBool("fallback"))
            .HandleWith(system.CmdGotoLook)
            .EndSubCommand();

        cmd.BeginSubCommand("preview")
            .WithDescription("Live path preview toward your look direction (commit to move)")
            .WithArgs(parsers.OptionalWord("mode"), parsers.OptionalFloat("range"))
            .HandleWith(system.CmdPreview)
            .EndSubCommand();

        cmd.BeginSubCommand("stop")
            .WithDescription("Cancel current action and stop movement")
            .HandleWith(system.CmdStop)
            .EndSubCommand();

        cmd.BeginSubCommand("activate")
            .WithDescription("Activate a block at position (optionally with JSON args)")
            .WithArgs(parsers.WorldPosition("pos"), parsers.OptionalWord("argsjson"))
            .HandleWith(system.CmdActivate)
            .EndSubCommand();

        cmd.BeginSubCommand("ignite")
            .WithDescription("Ignite an IIgnitable block (firepit, torch, etc.) at position")
            .WithArgs(parsers.WorldPosition("pos"))
            .HandleWith(system.CmdIgnite)
            .EndSubCommand();

        cmd.BeginSubCommand("break")
            .WithDescription("Break a block at position")
            .WithArgs(parsers.WorldPosition("pos"), parsers.OptionalFloat("dropmult"))
            .HandleWith(system.CmdBreak)
            .EndSubCommand();

        cmd.BeginSubCommand("mine")
            .WithDescription("Mine a block at position (timed, respects resistance and tool tier)")
            .WithArgs(parsers.WorldPosition("pos"), parsers.OptionalBool("autocollect"))
            .HandleWith(system.CmdMine)
            .EndSubCommand();

        cmd.BeginSubCommand("place")
            .WithDescription("Place a block at a target position (optional face)")
            .WithArgs(parsers.Word("blockcode"), parsers.WorldPosition("pos"), parsers.OptionalWord("face"))
            .HandleWith(system.CmdPlace)
            .EndSubCommand();

        cmd.BeginSubCommand("placeon")
            .WithDescription("Place a block onto your current block selection (optional face)")
            .WithArgs(parsers.Word("blockcode"), parsers.OptionalWord("face"))
            .HandleWith(system.CmdPlaceOn)
            .EndSubCommand();

        cmd.BeginSubCommand("placeheld")
            .WithDescription("Place the block from your active hotbar onto your block selection (optional face)")
            .WithArgs(parsers.OptionalWord("face"))
            .HandleWith(system.CmdPlaceHeld)
            .EndSubCommand();

        cmd.BeginSubCommand("equip")
            .WithDescription("Equip item into left/right hand or backpack slot")
            .WithArgs(parsers.WordRange("slot", "lefthand", "righthand", "backpack0", "backpack1"), parsers.Word("itemcode"), parsers.OptionalInt("qty"))
            .HandleWith(system.CmdEquip)
            .EndSubCommand();

        cmd.BeginSubCommand("give")
            .WithDescription("Give item to bot inventory")
            .WithArgs(parsers.Word("itemcode"), parsers.OptionalInt("qty"))
            .HandleWith(system.CmdGive)
            .EndSubCommand();

        cmd.BeginSubCommand("interact")
            .WithDescription("Interact with the entity you're looking at")
            .WithArgs(parsers.OptionalWord("mode"), parsers.OptionalFloat("range"))
            .HandleWith(system.CmdInteract)
            .EndSubCommand();

        cmd.BeginSubCommand("pickup")
            .WithDescription("Pick up an item entity (nearest or by id)")
            .WithArgs(parsers.OptionalLong("entityid"), parsers.OptionalFloat("range"))
            .HandleWith(system.CmdPickup)
            .EndSubCommand();

        cmd.BeginSubCommand("drop")
            .WithDescription("Drop item from bot inventory")
            .WithArgs(parsers.OptionalInt("slot"), parsers.OptionalInt("qty"))
            .HandleWith(system.CmdDrop)
            .EndSubCommand();

        cmd.BeginSubCommand("takefrom")
            .WithDescription("Take items from a container at position")
            .WithArgs(parsers.WorldPosition("pos"), parsers.Int("slot"), parsers.OptionalInt("qty"))
            .HandleWith(system.CmdTakeFrom)
            .EndSubCommand();

        cmd.BeginSubCommand("putinto")
            .WithDescription("Put items into a container at position")
            .WithArgs(parsers.WorldPosition("pos"), parsers.Int("slot"), parsers.OptionalInt("qty"))
            .HandleWith(system.CmdPutInto)
            .EndSubCommand();

        cmd.BeginSubCommand("validate")
            .WithDescription("Validate selection/LOS/claims for a target block")
            .WithArgs(parsers.WorldPosition("pos"), parsers.OptionalWord("access"))
            .HandleWith(system.CmdValidate)
            .EndSubCommand();

        cmd.BeginSubCommand("debug")
            .WithDescription("Toggle or set debug logging")
            .WithArgs(parsers.OptionalWord("mode"))
            .HandleWith(system.CmdDebug)
            .EndSubCommand();

        cmd.BeginSubCommand("pathdump")
            .WithDescription("Dump traverser path data and highlight path if available")
            .HandleWith(system.CmdPathDump)
            .EndSubCommand();

        cmd.BeginSubCommand("entitytypes")
            .WithDescription("List entity types (optional filter)")
            .WithArgs(parsers.OptionalWord("filter"))
            .HandleWith(system.CmdEntityTypes)
            .EndSubCommand();

        cmd.BeginSubCommand("manage")
            .WithDescription("Open the Bot Manager UI")
            .HandleWith(system.CmdManage)
            .EndSubCommand();

        cmd.BeginSubCommand("panic")
            .WithDescription("Emergency UI reset and mouse release")
            .HandleWith(system.CmdPanic)
            .EndSubCommand();

        cmd.BeginSubCommand("possess")
            .WithDescription("Possess the selected bot (see through its eyes)")
            .HandleWith(system.CmdPossess)
            .EndSubCommand();

        cmd.BeginSubCommand("unpossess")
            .WithDescription("Exit possession mode")
            .HandleWith(system.CmdUnpossess)
            .EndSubCommand();

        cmd.BeginSubCommand("teststate")
            .WithDescription("Query bot state + nearby items for testing")
            .WithArgs(parsers.OptionalFloat("radius"))
            .HandleWith(system.CmdTestState)
            .EndSubCommand();

        var zoneCmd = cmd.BeginSubCommand("zone")
            .WithDescription("Manage named zones");

        zoneCmd.BeginSubCommand("define")
            .WithDescription("Define a named AABB zone")
            .WithArgs(parsers.Word("name"), parsers.Int("x1"), parsers.Int("y1"), parsers.Int("z1"), parsers.Int("x2"), parsers.Int("y2"), parsers.Int("z2"))
            .HandleWith(system.CmdZoneDefine)
            .EndSubCommand();

        zoneCmd.BeginSubCommand("remove")
            .WithDescription("Remove a named zone")
            .WithArgs(parsers.Word("name"))
            .HandleWith(system.CmdZoneRemove)
            .EndSubCommand();

        zoneCmd.BeginSubCommand("list")
            .WithDescription("List all zones")
            .HandleWith(system.CmdZoneList)
            .EndSubCommand();

        zoneCmd.BeginSubCommand("check")
            .WithDescription("Show which zones the selected bot is in")
            .HandleWith(system.CmdZoneCheck)
            .EndSubCommand();

        zoneCmd.BeginSubCommand("show")
            .WithDescription("Highlight a zone's boundaries")
            .WithArgs(parsers.Word("name"))
            .HandleWith(system.CmdZoneShow)
            .EndSubCommand();

        zoneCmd.EndSubCommand();

        cmd.BeginSubCommand("animate")
            .WithDescription("Play an animation on the selected bot")
            .WithArgs(
                parsers.Word("animCodeOrStop"),
                parsers.OptionalWord("speedOrAnimCode"),
                parsers.OptionalWord("loop")
            )
            .HandleWith(system.CmdAnimate)
            .EndSubCommand();
    }
}
