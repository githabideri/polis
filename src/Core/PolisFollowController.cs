// PolisFollowController — the explicit follow toggle (2026-10-11, replacing
// the NLP "come to me" reflex, which was too tight a sifter for natural
// language; operator decision: follow is a command, not a guess).
//
//   follow off         -> release all following bots
//   follow 900,905     -> the listed bots follow the player
//
// A 2 s tick re-issues a goto to the player's cell only when the player has
// moved more than FOLLOW_TRIGGER blocks since that bot's last goto target,
// and only while the bot is idle (JobRunning false) — a bot doing work
// catches up on its next idle tick instead of being interrupted. Player
// offline: followers hold their position (no re-issue).
//
// The oikistes layer maps operator semantics onto this: "follow me" -> my
// body's id, "follow all" -> every bot's ids. The webui exposes the same
// as a toggle button.
//
// 10-11 post-mortem: the original registration used
// sapi.Event.RegisterCallback((float dt) => FollowTick(), 2000) and the
// callback never fired (follow armed, player moved 30 blocks, no re-issue,
// no exception logged — it simply does not run on 1.22.7). The proven
// repeated-tick path in this codebase is RegisterGameTickListener (the 50 ms
// system tick and the 1 s zone tick both fire); the tick body is now
// try/catch'd and every re-issue is logged, so a future silent death shows
// up in the journal.
using System;
using System.Collections.Generic;
using System.Linq;
using Vintagestory.API.Common;
using Vintagestory.API.MathTools;
using Vintagestory.API.Server;
using Polis.Actions.Navigation;

public partial class PolisSystem
{
    const float FOLLOW_TRIGGER_BLOCKS = 6f;
    internal readonly System.Collections.Generic.HashSet<long> followBots = new System.Collections.Generic.HashSet<long>();
    internal readonly System.Collections.Generic.Dictionary<long, Vec3i> followLastTargets = new System.Collections.Generic.Dictionary<long, Vec3i>();

    internal void FollowInit()
    {
        // NOT Event.RegisterCallback — see the post-mortem above.
        sapi.Event.RegisterGameTickListener(FollowTickListener, 2000);
        sapi.Logger.Debug("[polis] follow: tick listener registered (2000ms)");
    }

    private void FollowTickListener(float dt)
    {
        try
        {
            FollowTick();
        }
        catch (Exception ex)
        {
            sapi.Logger.Error("[polis] follow tick threw: " + ex.Message + "\n" + ex.StackTrace);
        }
    }

    internal int FollowAdd(System.Collections.Generic.IEnumerable<long> ids, Action<string> log)
    {
        int added = 0;
        foreach (var id in ids.Distinct())
        {
            if (bots.ContainsKey(id) && followBots.Add(id)) added++;
        }
        followLastTargets.Clear();
        log?.Invoke($"follow on: bot(s) {string.Join(",", followBots.OrderBy(x => x))}");
        return added;
    }

    internal bool IsFollowing() => followBots.Count > 0;

    internal System.Collections.Generic.List<long> FollowingBotIds()
        => followBots.OrderBy(x => x).ToList();

    internal int FollowClear(Action<string> log)
    {
        int n = followBots.Count;
        followBots.Clear();
        followLastTargets.Clear();
        if (n > 0) log?.Invoke($"follow off (released {n})");
        return n;
    }

    internal void FollowTick()
    {
        if (sapi == null || sapi.World == null) return;
        if (followBots.Count == 0) return;

        // The estate runs one operator; take the first online player.
        EntityPlayer player = null;
        foreach (var p in sapi.World.AllOnlinePlayers)
        {
            if (p is IServerPlayer sp && sp.Entity != null)
            { player = sp.Entity; break; }
        }
        if (player == null) return; // offline: hold positions

        var pcell = new Vec3i((int)player.Pos.X, (int)player.Pos.Y, (int)player.Pos.Z);

        foreach (var id in followBots.ToArray())
        {
            if (!bots.TryGetValue(id, out var bot) || bot.Entity == null)
            {
                followBots.Remove(id);
                continue;
            }
            if (bot.JobRunning) continue; // busy: catch up on the next idle tick

            bool fresh;
            if (!followLastTargets.TryGetValue(id, out var last))
            {
                fresh = true;
            }
            else
            {
                float dx = last.X - pcell.X, dy = last.Y - pcell.Y, dz = last.Z - pcell.Z;
                fresh = (float)System.Math.Sqrt(dx * dx + dy * dy + dz * dz) > FOLLOW_TRIGGER_BLOCKS;
            }
            if (!fresh) continue;

            followLastTargets[id] = pcell;
            sapi.Logger.Debug($"[polis] follow: re-issue goto for {id} -> ({pcell.X},{pcell.Y},{pcell.Z})");
            void OnResult(bool ok, string msg)
            {
                bot.RecordActionResult("follow", ok, msg, sapi.World.ElapsedMilliseconds);
            }
            var action = new PolisGotoAction(
                bot.Activity,
                new Vec3d(pcell.X, pcell.Y, pcell.Z),
                true,   // useAstar
                "walk", // animCode
                0.02f,  // walkSpeed
                1f,     // animSpeed
                null,   // debug
                null,   // debugPath
                false,  // debugEnabled
                true,   // allowFallback
                OnResult);
            StartSingleAction(bot, "follow", action);
        }
    }
}
