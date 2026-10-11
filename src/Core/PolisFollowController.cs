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
using System;
using System.Collections.Generic;
using System.Linq;
using Vintagestory.API.Common;
using Polis.Actions.Navigation;

public partial class PolisSystem
{
    const float FOLLOW_TRIGGER_BLOCKS = 6f;
    internal readonly System.Collections.Generic.HashSet<long> followBots = new System.Collections.Generic.HashSet<long>();
    internal readonly System.Collections.Generic.Dictionary<long, Vec3i> followLastTargets = new System.Collections.Generic.Dictionary<long, Vec3i>();

    internal void FollowInit()
    {
        sapi.Event.RegisterCallback(FollowTick, 2000);
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
        if (followBots.Count == 0) return;

        // The estate runs one operator; take the first living player.
        EntityPlayer player = null;
        foreach (var e in sapi.World.GetEntities())
        {
            if (e is EntityPlayer p && !p.IsDead) { player = p; break; }
        }
        if (player == null) return; // offline: hold positions

        var pcell = new Vec3i((int)player.ServerPos.X, (int)player.ServerPos.Y, (int)player.ServerPos.Z);

        foreach (var id in followBots.ToArray())
        {
            if (!bots.TryGetValue(id, out var bot) || bot.Entity == null || bot.Entity.IsDead)
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
