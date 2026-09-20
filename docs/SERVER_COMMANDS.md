# Vintage Story Server Command List (from wiki)

Source: https://wiki.vintagestory.at/index.php?title=List_of_server_commands&action=render
Fetched: 2026-01-13

Note: The wiki marks this page as outdated and recommends using the in-game command handbook (client command `.chb`) for the most current info.
This is a Markdown conversion of the wiki page, so formatting may be imperfect.

## Multiplayer Commands for Players

### /land

Commands for Land Claiming

- `/land [claim|free|info|list]` - Claim an area of the world where only you can build or use blocks in.
- `/land list` - Displays a list of the claims that you made so far, you can use displayed index number to modify it, see below.
- `/land info` - Display information on the claimant of the current position, if there is any.
- `/land free [index]` - Deletes a claim of yours.
- `/land adminfree` - Deletes the claim of a player as an admin.
- `/land claim [load|new|grant|revoke|grantgroup|revokegroup|grow|shrink|start|end|add|allowuseeveryone|plevel|fullheight|save|cancel|download]` - Create or modify an existing claim.
  - `/land claim load [0..999]` - Load an existing claim for modifying. Use index number as shown in /land list to select which claim.
  - `/land claim new` - Create a new claim, also marks the start position.
  - `/land claim grant [playername] [use|all]` - Grant given player access to your claim. 'use' for only use/interact rights, 'all' for use and place/break block rights.
  - `/land claim revoke [playername]` - Revoke a previously granted privilege to given player on your claim.
  - `/land claim grantgroup [groupname] [use|all]` - Grant given player group access to your claim. 'use' for only use/interact rights, 'all' for use and place/break block rights.
  - `/land claim revokegroup [groupname]` - Revoke a previously granted privilege to given player group on your claim.
  - `/land claim allowuseeveryone [true|false]` - Grant or Revoke use access to all players
  - `/land claim start` - Mark a start position for a cuboidal area to be claimed.
  - `/land claim end` - Mark an end position for a cuboidal area to be claimed.
  - `/land claim grow [north|east|south|west|up|down] [-99..99]` - Grow the currently selected cuboid towards north/east/south/west/up/down by given length. If no length is supplied then the selection is grown by 1 block.
  - `/land claim shrink [north|east|south|west|up|down] [-99..99]` - Shrink the currently selected cuboid towards north/east/south/west/up/down by given length. If no length is supplied then the selection is shrunk by 1 block.
  - `/land claim add` - Adds the currently selected cuboid to the currently edited claim. A claim may exist of multiple cuboids, as long as they are adjacent to eachother.
  - `/land claim fullheight` - Vertically grow the currently selected cuboid to encompass the full height from world bottom to world top. Note that with default settings this is not possible because players cannot claim that many chunks.
  - `/land claim save [description]` - Save current claim modifications and stop editing the current claim.
  - `/land claim cancel` - Discard all modifications to this claim.
  - `/land claim download [0..999]` - Download an existing claim of yours to your computer. Use index number as shown in /land list to select which claim. The .json file is saved in AppData/Roaming/VintageStoryData/WorldEdit. This command can be used on a server even if you are not an admin.

### /group

- `/group [create|disband|rename|invite|acceptinvite|leave|list|info|kick|op|deop]` - Create/manage or destroy a player group. Player groups currently only serve the function of offering a seperate channel to chat in in addition to granting access to claimed areas.
  - `/group create [groupname]` - Creates a new player group, own chat channel. While in the this group's chat channel:
  - `/group invite [group] [playername]` - Invites a player to this group
  - `/group acceptinvite [groupname]` - Accept an invite to join the group
  - `/group leave [group]` - Leaves this player group.
  - `/group list` - Lists all groups you are currently in.
  - `/group info [groupname]` - Lists the players of a group.
  - `/group rename [oldgroupname] [newgroupname]` - Renames the group.
  - `/group kick [group] [playername]` - Removes a player from the group.
  - `/group op [group] [playername]` - Grants operator status to this player, which allows them to invite other players.
  - `/group deop [group] [playername]` - Revokes operator status from this player.
  - `/group disband [group]` - Destroy a player group. Must be owner to perform this command.

### /waypoint

These commands affect the players Worldmap and waypoints.

- `/waypoint [add|addat|addati|list|remove]` - Add and edit your list of waypoints.
  - `/waypoint add red copper` - Adds a waypoint with given color and text at your current position. The color may be any named .NET Color or a Hex Code . Example:
  - `/waypoint addat [coords] [pinned] [color] [title]` - Add a waypoint at the given coordinates .
  - `/waypoint addati [icon] [x] [y] [z] [pinned] [color] [title]` - Add a waypoint at your current location, including colour and icon info.
  - `/waypoint list` - Shows a list of all player waypoints by id number.
  - `/waypoint list` - Removes the waypoint id as shown in .

### /kill

- `/kill` - Kills the player.

### /emote

- `/emote [wave|cheer|shrug|cry|nod|facepalm|bow|laugh|rage]` - Character does an emote animation.

### /pm

- `/pm [playername] [message]` - Send a private message to a user (creates a temporary group)

## Commands for Moderators and Admins

### /help

- `/help` - List all server commands.

### /giveblock

- `/giveblock clutter{type: "barrel-metal1"}` - Creates an itemstack of the specified block in the specified quantity, and gives it to the specified player. The player must have an empty inventory slot to receive the itemstack. Quantity, toplayername and attributes are optional. The default quantity is 1. If player name is not set, the command user's own player is targeted. Attributes may optionally be supplied in curly braces after the blockcode without a space between the block name and the braces. The attributes should be given in JSON format. Example:

### /giveitem

- `/giveitem [itemcode] [quantity] [toplayername] [attributes]` - Same as above but for items.

### /gamemode

- `/gamemode [0..4|guest|survival|creative|spectator]` - Mode names can be shortened to any length. Sets your game mode:
  - `0|guest` - Guest mode - Cannot place/remove any blocks but can interact with them
  - `1|survival` - Survival mode - Can slowly break/place blocks. Can die. Cannot fly. Survival inventory.
  - `2|creative` - Creative mode - Access to all blocks through the creative inventory. Instant block breaking. Cannot die. Can fly.
  - `3|spectator` - Spectator mode - Cannot place/remove blocks and cannot interact with anything, but can fly.

- `/gamemode [playername] [0..4]` - Sets the gamemode for given player.

### /gm

Shorthand of /gamemode

### /tp

- `/tp [coordinates]` - Teleport yourself to the position given.
  - `/tp x y z` - Teleports the player to given pretty coordinate visible from the pretty coordinate box.
  - `/tp =x =y =z` - Teleports the player to given absolute coordinate visible from the debug screen on CTRL + F3.
  - `/tp ~x ~y ~z` - Teleports player by a given relative distance, i.e. teleport ~1 ~0 ~0 will teleport the player one block in x direction.

- `/tp [playername] [coordinates]` - Teleport given player to a different position.

- `/tp [playername]` - Teleport yourself to given player.

- `/tpwp [starts with name]` - Teleport yourself to a waypoint.

### /ban

- `/ban [playername] [reason]` - Ban a player.

### /unban

- `/unban [playername]` - Unban a player.

### /kick

- `/kick [playername] [reason]` - Kick a player.

### /clear

- `/clearinv` - Removes all items from your inventory.

### /nexttempstorm

- `/nexttempstorm` - Tells you the amount of days left until the next temporal storm.
- `/nexttempstorm now` - Fast forwards the time so that a temporal storm starts right away.

## Privilege Control

### player selectors

In the following commands, [playername] represents a player selector. The following selectors are accepted:

The selectors with a bracket also accept filters to narrow down the list.

For example o[namematch=b*,range=10,role=admin] selects all online players whose name starts with 'b', are at most 10 blocks away from the caller, and are admins.

### /op

- `/player [playername] role admin` - Alias of .

### /role

- `[rolename]` - Display or modify on role .
  - `/role [rolename] spawnpoint [x] [y?] [z]` - Configure a role specific spawn point. Any player that has this role will spawn at this location.
  - `/role [rolename] privilege [grant|revoke] [privelegename]` - Grant or revoke privileges from given role.
  - `/role [rolename] landclaimallowance [value]` - Set the max allowed claimable area in cubic meters for every player that has this role. (default: 4 chunks = 4*32*32*32 cubic meters = 131072)
  - `/role [rolename] landclaimmaxareas [value]` - Set the max quantity of non-adjacent areas a player may claim. (default: 3)
  - `/role [rolename] landclaimminsize [x y z]` - Set the smallest cuboid a player may claim. (default: 6 by 6 by 6)

### /player

- `/player [playername] movespeed` - Set a player's move speed.
- `/player [playername] clearinv` - Clear the player's entire inventory.
- `/player [playername] wipedata` - Wipe the player data such as the entire inventory, skin/class etc..
- `/player [playername] [whitelist|privilege|role|entity|stats|gamemode|landclaimallowance|landclaimmaxareas]` - Modify or display player data.
  - `/player [playername] whitelist` - See current whitelist mode of given player.
  - `/player [playername] whitelist on` - Adds a player to a server whitelist.
  - `/player [playername] privilege` - Lists the players current privileges.
  - `/player [playername] privilege [grant|revoke] [privilegename]` - Grants or revokes given privilege for this player.
  - `/player [playername] role` - Shows the players current privilege role. (default: suplayer)
  - `/player [playername] role [rolename]` - Sets the players current privilege role. (default: suplayer)
  - `/player [playername] stats` - Shows a summary of the players current privileges.
  - `/player [playername] gamemode [0..4 or partially/fully written game mode name]` - Shows or sets the players current game mode.
  - `/player [playername] landclaimallowance [0..9999]` - Shows or sets a player specific extra land claim allowance, independent of the allowance set by the role. (default: 0)
  - `/player [playername] landclaimmaxareas [0..9999]` - Shows or sets a player specific extra land claim areas allowance , independent of the allowance set by the role. (default: 0)
  - `/player [playername] allowcharselonce` - Allows the player to re-select their class after doing so already.
  - `/player [playername] entity` - Shows info (position, satiety, health) about the player.
    - `/player [playername] entity temp [value]` - Set player's body temperature.
    - `/player [playername] entity health [0.1-1]` - Set player's health. (default: 1, making the health by 100% of full health bar)
    - `/player [playername] entity maxhealth [0.1-999]` - Set player's max health.
    - `/player [playername] entity satiety [0.1-1]` - Set player's satiety. (default: 1, making the satiety by 100% of full satiety bar)
    - `/player [playername] entity maxoxygen [int]` - Set player's maximum oxygen. Integer is the length of the oxygen timer in milliseconds. (default: 20000, or 20 seconds)
  - `/player [playername] entity intox [0.1-1]` - Sets player's intoxication value.
  - `/player [playername] movespeed [value]` - Sets the player's speed.

## World Control

### /worldconfig

Protip: Do not actually type the [ ] shown in this command syntax, that is intended only to show which values can be changed!

See dedicated page on World Configuration

All of the following work [ 1 ] in a singleplayer world to restore the parchment-style map to the classic colorful map:

- `/worldconfig colorAccurateWorldmap true`
- `/worldconfigcreate bool colorAccurateWorldmap true`
- `/player [playername] privilege grant colorAccurateWorldmap`

In a multiplayer world, the following restores the classic map for an individual:

- `/player [playername] privilege grant colorAccurateWorldmap`

while the following restores the classic map for all players:

- `/worldconfig colorAccurateWorldmap true`
- `/worldconfigcreate bool colorAccurateWorldmap true`

(needs confirmation)

### /entity

- `/entity [subcommand]` - Spawn, remove, and count entities (item drops, creatures, etc).
  - `/entity cmd [subcommand]` - Issue commands on existing entities
    - `/entity cmd stopanim` - Stop an entity animation.
    - `/entity cmd stoptask` - Stop an AI task.
    - `/entity cmd setattr` - Set entity attributes.
    - `/entity cmd setgen` - Set entity generation.
    - `/entity cmd setlact` - Set entity lactating.
    - `/entity cmd move` - Move a creature.
    - `/entity cmd kill` - Kill a creature.
    - `/entity cmd wipeall` - Removes all entities except players from all loaded chunks.
  - `/entity debug [0|1]` - Enable entity debug mode, this will send continous debug information to all connected clients, which are displayed above the entity if the client used the command .clientConfig showEntitydebuginfo 1
  - `/entity spawndebug [0|1]` - Enable entity spawn debug mode.
  - `/entity count [ entityfilter ]` - Count entities by code/filter and show a summary.
  - `/entity countg [ entityfilter ]` - Count entities by code/filter and show a summary grouped by first code part.
  - `/entity spawnat [entitytype] [amount] [position] [radius]` - Spawn an entity by type at given position, within a given radius. Valid types can be found in the survival mod assets folder /entities.
  - `/entity remove [ entityfilter ]` - Remove selected creatures.

entity filter is either a player name, or else one of the following selection codes:

- `s[]` - for self.
- `l[]` - for the entity currently looked at.
- `p[]` - for all players.
- `e[]` - for all entities.

Inside the square brackets, one or more filters can be added, to be more selective. Filters include name, type, class, alive, range. For example, e[type=gazelle,range=3,alive=true] .

The filters minx/miny/minz/maxx/maxy/maxz can also be used to specify a volume to search, coordinates are relative to the command caller's position.

Find the entity id by using .clientConfig showEntityDebuginfo . Useful for removing a specific trader permanently, for instance.

This argument may be omitted if the remainder of the command makes sense, in which case it will be interpreted as self.

### /time

- `/time [set|get|speed]` - Time related functions
  - `/time` - Shows current time.
  - `/time stop` - Stop passage of time and time affected processes
  - `/time resume` - Resume passage of time and time affected processes
  - `/time set [lunch|day|night|latenight|morning|latemorning|sunrise|sunset|afternoon|midnight|witchinghour]` - Sets the clock to the given time of day.
  - `/time set [time]` - Sets the clock to the time given in hours, in 24 hour format. E.g. 1.5 is 1:30 AM.
  - `/time setmonth [jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec]` - Sets the calendar to the given month of the year
  - `/time add [hours]:[minutes]` - Adds given hours and minutes to the calendar.
  - `/time speed [0-9999]` - Shows or sets current game time speed (default 60).
  - `/time hoursperday [0-9999]` - Shows or sets the current hours per day (default 24).
  - `/time calendarspeedmul` - Shows or set the calendar speed multiplier, changing the overall time speed in game (default 0.5, making the hours pass by 50% of normal speed).

| Time name | Time value |
| --- | --- |
| lunch | 12 |
| day | 12 |
| night | 20 |
| latenight | 22 |
| morning | 8 |
| latemorning | 10 |
| sunrise | 6.5 |
| sunset | 17.5 |
| afternoon | 14 |
| midnight | 0 |
| witchinghour | 3 |

### /weather

- `/weather` - Controls weather and wind patterns. If is run by itself it prints the current weather stats.
  - `/weather setprecipa` - Running with no arguments returns the current precip. override, if one is set. Including an argument overrides the precipitation intensity and in turn also the rain cloud overlay. removes all rain clouds, stops any rain but keeps some rain clouds, while causes the heaviest rain and full rain clouds. The server will remain indefinitely in that rain state until reset with .
  - `/weather setprecip` - Resets the precipitation override caused by command. This results in the precipitation value being handled automatically.
  - `/weather stoprain` - Stops any current rain by forwarding to a time in the future where there is no rain.
  - `/weather acp` - Toggles auto-changing weather patterns.
  - `/weather lp` - Lists all loaded weather patterns.
  - `/weather t` - Transitions to a random weather pattern.
  - `/weather c` - Quickly transitions to a random weather pattern.
  - `/weather setev [event]` - Sets a weather event globally.
  - `/weather setevr [event]` - Set a weather event only in the player's region.
  - `/weather setw [lightbreeze|mediumbreeze|still|storm|strongbreeze]` - Sets the current wind pattern to the given wind pattern.
  - `weatherpattern` - Instantly sets the weather pattern to .
  - `/weather setirandom` - Instantly sets the weather to a random weather pattern.
  - `[weatherpattern]` - Instantly sets the weather to only in the current region.

## Server control and configuration

### /serverconfig

- `[config]` - Modify or display the server config
  - `/serverconfig maxchunkradius [integer]` - Displays the max chunk radius. Sets the max chunk radius to the integer passed, which is the highest chunk radius a player may load.
  - `/serverconfig maxclients [integer]` - Displays the max clients. Sets the max number of connected clients to the integer passed.
  - `/serverconfig password [string]` - Sets the server password that is required to connect to the server. It may not contain spaces.
  - `/serverconfig nopassword` - Removes the password protection.
  - `/serverconfig antiabuse [Off|Basic|Pedantic]` - Sets anti-abuse level, this protects against a range of malicious player operations, but is currently a work in progress.
  - `/serverconfig allowpvp [bool]` - Control allowing players to combat each other.
  - `/serverconfig allowfirespread [bool]` - Enable/Disable spread of fire
  - `/serverconfig allowfallingblocks [bool]` - Enable/Disable block gravity.
  - `/serverconfig WhitelistMode [default|off|on]` - Control allowing only whitelisted players to connect to the server. "Default" means whitelist is on for dedicated servers, but off for single player open to LAN servers. Dedicated servers are now whitelisted by default. (The serverconfig "OnlyWhitelisted" is now obsolete.) An alternative to [default|off|on] is [0|1|2], with "default" corresponding to "0", and so on.
  - `/serverconfig entityspawning [bool]` - Control global entity spawning. Disabling it will cause no creatures to spawn (default: on).
  - `/serverconfig tickrate [10-100]` - Shows or sets the server tick rate. A higher tickrate makes the server more responsive. A lower tick rate has the opposite effect.
  - `/serverconfig blockTickSamplesPerChunk` - Control how many random update ticks per chunk should be executed.
  - `y` - Shows or sets the default spawn point. can be omitted to automatically use the surface position at given x/z location.
  - `/serverconfig setspawnhere` - Sets the default spawn point to where the player is currently standing.
  - `/serverconfig passtimewhenempty [bool]` - Shows or sets if time should pass when the server has no connected players.
  - `/serverconfig spawncapplayerscaling [0..1]` - Helps to evenly distribute mob spawns around each player. A value of 0 means no extra mobs can spawn on increased player count, a value of 1 means a second player doubles the spawn cap, 3 players triple the spawn cap and so on (default: 0.75).
  - `/serverconfig temporaryipblocklist [0..1]` - Enable or disable the ip based block list .
  - `/serverconfig loginfloodprotection [0..1]` - Enable or disable the ip based login flood protection .

### /stats

- `/stats` - Show current server statistics, tick rate, memory usage, etc..

### /announce

- `/announce [message]` - Announce a server wide message in all chat groups.

### /stop

- `/stop` - Stops the server.

### /autosavenow

- `/autosavenow` - Autosaves the server.

### /list

- `/list [clients|banned|role|privileges]` - Show various lists of information.
  - `/list clients` - Show current connected clients.
  - `/list banned` - Show current list of banned players.
  - `/list role` - Show list of all configured privilege roles.
  - `/list privileges` - Show list of all configured privileges.

### /allowlan

- `/allowlan [on|off]` - Whether or not to allow external lan connections to the server (temporary runtime setting for non dedicated servers)

## Utility and Debug Tools

### /moddb

- `/moddb [install|remove|list|search|searchcompatible|searchfor|searchforc]` - ModDB utility. To install and remove mods.
  - `/moddb install [modid] [gameVersion]` - : Install the specified mod.
  - `/moddb remove [modid]` - : Uninstall the specified mod.
  - `/moddb list` - : List all installed mods.
  - `/moddb search [query]` - : Full-text search on ModDB.
  - `/moddb searchcompatible [modid]` - : Search for a mod, filtered for game versions compatible with the current version.
  - `/moddb searchfor [gameVersion] [modid]` - : Search for a mod, filtered for the specified game version only.
  - `/moddb searchforc [gameVersion] [modid]` - : Search for a mod, filtered for game versions compatible with the specified version.

### /fixmapping

- `/fixmapping applyall` - Applies block and item remapping in order to upgrade to a new version of the game

### /genbackup

- `/genbackup [filename]` - Creates a full copy of the current save game and stores it in the backups folder. Can be run without pausing the server. If no filename is supplied, it will generate one based on the current date and time

### /bir

- `/bir [getid|getcode|remap]` - Block id remapper tools. Useful to fix broken blocks after removing/updating custom blocks.

### /chunk

- `/chunk [cit|printmap|unload|forceload]` - Chunk commands.
- `/chunk cit` - Current chunk generation info.
- `/chunk printmap` - Export a png file of a map of loaded chunks. Marks call location with a yellow pixel.
- `/chunk unload [0|1]` - Toggles whether the server should automatically unload chunks that are no longer in range of any players and also send chunk unload commands to the clients.
- `/chunk forceload x1 z1 x2 z2` - Tells the server to load given area and prevents unloading.

### /whenwillitstopraining

- `/whenwillitstopraining` - Tells when the rain should stop.

### /roomregdebug

Removed and replaced with /debug room as of version 1.19. These commands are kept for archival purposes.

- `/roomregdebug [list|hi|unhi]` - Room registration debug tools.
  - `/roomregdebug list` - Lists all rooms the player is in.
  - `/roomregdebug hi` - Highlights the space of rooms with color. Unsuitable rooms are in red, eligible rooms are in green.
  - `/roomregdebug unhi` - Removes room highlighting.

### /info

- `/info [ident|seed|createdversion|mapsize]` - Information about the current save game
  - `/info ident` - Shows the world identifier
  - `/info seed` - Shows the world seed
  - `/info createdversion` - Shows the game version in which the world was created
  - `/info mapsize` - Shows the world size

### /debug

- `/debug [subcommand]` - Various debug commands
  - `/debug logticks [milliseconds]` - If a server tick required more then supplied milliseconds to process, a breakdown of that tick will be logged to server-main.txt
  - `/debug tickhandlers` - Displays a summary of ticking blocks and entities are currently registered.
  - `/debug tickhandlers dump [gtblock|gtentity|dcblock|sdcblock|dcentity]` - Dumps a complete list of all tick/callback listeners to server-debug.txt
  - `/debug helddurability [value]` - Sets the durability of the currently held item
  - `/debug helddura [value]` - Alias of /debug helddurability
  - `/debug heldtemperature [value]` - Sets the temperature of the currently held item
  - `/debug heldtemp [value]` - Alias of /debug heldtemperature
  - `/debug heldstattr key type normal-generic` - Sets the stack attribute for the currently held item (e.g. for chest-east).
  - `/debug heldcoattr key [int|bool|string|tree|double|float] [value]` - Sets the collectible attribute for the currently held item.
  - `/debug setgen [value]` - Sets the generation of the currently looked-at entity
  - `/debug printcl [all|missing]` - Prints a full list of all/missing collectible codes to the server-debug.txt
  - `/debug itemcodes` - Exports a full list of all item codes to the server-main.txt
  - `/debug blockcodes` - Exports a full list of all block codes to the server-main.txt
  - `/debug blockids` - Lists the blocks that consume most block ids to the server-main.txt
  - `/debug blockstats` - Generates amount of block ids used, grouped by first block code part to server-main.txt
  - `/debug privileges` - Changes privilege debugging mode
  - `/debug netbench` - Toggles network benchmarking
  - `/debug tickposition` - Tick position
  - `/debug stacktrace` - Stack trace
  - `/debug chunk` - Various chunk commands.
    - `/debug chunk queue [quantity]` - Amount of generating chunks in queue.
    - `/debug chunk q [quantity]` - Alias of /debug chunk queue
    - `/debug chunk stats` - Statistics of currently loaded chunks.
    - `/debug chunk printmap` - Exports a map of loaded chunk as a png image.
    - `/debug chunk here` - Information about the chunk at the caller's position.
    - `/debug chunk resend` - Resends a chunk to all players.
    - `/debug chunk relight` - Relights a chunk for all players.
  - `/debug sendchunks [0|1]` - Allows toggling of the normal chunk generation/sending operations to all clients. Force loaded chunks are not affected by this switch.
  - `/debug rebuildlandclaimpartitions` - Rebuilds land claim partitions
  - `/debug octagonpoints` - Prints octagon points
  - `/debug cloh` - Compacts a large object heap
  - `/debug mainthreadstate` - Main thread state
  - `/debug killmainthread` - Kills the main thread
  - `/debug expclang` - Exports a list of block and item translations to collectiblelang.json and adds placeholders for missing translations.
  - `/debug rift [clear|fade|spawn|spawnhere]` - Various rift commands
    - `/debug rift clear` - Immediately removes all loaded rifts.
    - `/debug rift fade` - Slowly removes all loaded rifts, over a few minutes.
    - `/debug rift spawn [quantity]` - Spawns the specified quantity of rifts.
    - `/debug rift spawnhere` - Spawns one rift.
  - `/roomregdebug` - Room registration debug tools. Equivalent of the previous command.
    - `/debug rooms list` - Lists all rooms the player is in.
    - `/debug rooms hi` - Highlights the space of rooms with color. Unsuitable rooms are in red, eligible rooms are in green.
    - `/debug rooms unhi` - Removes room highlighting.
  - `/debug tiledd [tiled_dungeon_code] [amount_of_tiles]` - Tiled dungeon generator debugger/tester. Usage: amount of tiles is an integer number.
  - `/debug astar [command]` - A path-finding debug testing tool. Usage: command is one of the following: start, end, bench, clear.

### /wgen

- `/wgen [testmap|testnoise|chunk|region|pos|tree]` - World generation tools
  - `/wgen autogen` - Change automatic worldgen mode
  - `/wgen gt` - Generate trees mode
  - `/wgen testmap [climate|forest|wind|gprov|landform|ore]` - Generates a sample 512x512 map using a fixed worldseed as a png, saved where the game executables is located. May need to be administrator to work properly.
    - `/wgen testmap climater [hot|warm|cool|icy]` - Same as /wgen testmap climate, but you can choose the temperature preset
    - `/wgen testmap oretopdistort` - Ore top distort maps
    - `/wgen testmap rockstrata` - Rock strata maps
  - `/wgen genmap [climate|forest|wind|gprov|landform|ore]` - Same as testmap? (Need more info)
  - `rockstrata` - Generates a map of the current region (16x16 chunks) using the save game worldseed as a png, saved where the game executables are located. May need to be administrator to work properly. is based on the rockstrata JSON file at Vintagestory\assets\survival\worldgen. Limestone is 6, chalk is 8, bauxite is 9, slate is 10.
  - `/wgen regions [radius] [ore] [orename]` - Show availability of ore maps for ore in the regions. Radius can only be up to 2 - larger radius doesn't seem to show more. May require increasing viewing range.
  - `/wgen pregen [radius]` - Pregenerate chunks around the player
  - `/wgen regen [radius]` - Regenerate chunks around the player
  - `/wgen regenr [radius]` - Regenerate chunks around the player with random seed
  - `/wgen regenc [radius]` - Regenerate chunks around the world spawn
  - `/wgen regenrc [radius]` - Regenerate chunks around the world spawn with random seed
  - `/wgen delrock [radius]` - Remove rocks around the player - radius is ignored? Looks like 160x160 box centered on player. Will cause server overload, make take several minutes for server to recover
  - `/wgen delrockc [radius]` - Remove rocks around the world spawn - Does not work
  - `/wgen del [radius]` - Remove chunks around the player
  - `/wgen tree walnut` - Spawn a tree at the player's current x z coordinates. The y coordinate is the first non-empty block at or below the player's eye position. The code parameter is required. The size and aheadoffset parameters are optional. The tree generators are reloaded from the json files before generating the tree. Example:
  - `/wgen treelineup` - Spawn tree line
  - `/wgen pos [ymax|coords|latitude|structures|height|cavedistort|gprov|rockstrata|landform|climate]` - Shows info at the current position
  - `/wgen testnoise [octaves]`

### /we

See How to use WorldEdit

### /macro

- `/macro [addcmd|setcmd|syntax|desc|priv|save|delete|show|list]` - Create a server side macro that can execute one or more commands
  - `/macro addcmd [command]` - Add a command to a temporary macro.
  - `/macro setcmd [command]` - Override a command to a temporary macro.
  - `/help [name]` - Sets the syntax help info displayed when using .
  - `/help [name]` - Sets the description text displayed when using
  - `/macro [priv]` - Sets the privilege required to execute this command, e.g. controlserver if only for admins or, build for any player with build rights.
  - `/macro show` - Shows the contents of the temporary macro currently being defined by above commands.
  - `/macro save [name]` - Saves the temporary macro defined by above command to given command name.
  - `/macro list` - Shows a list of all saved macros.
  - `/macro show [name]` - Shows the contents of a saved macro.
  - `/macro delete [name]` - Deletes a previously saved macro.
  - `/macro discard [name]` - Discards the temporary macro.

## See also

- List of client commands
- World Configuration
