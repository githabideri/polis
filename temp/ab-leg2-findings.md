
## A/B leg 2 (2026-10-11 night) - after the platform walls

Protocol: both models, same message ("Forage three berries for the
camp"), all 9 bushes re-ripened (disclosed) before each attempt, the
body placed by operator where a walk had wedged (disclosed; the
traverser's hillside behaviour is the platform limit, not the brain).

**Platform walls fixed this leg (all in the platform, neither model):**
1. `/polis/targets` sphere cap 32 -> 64 (C# clamp; the 53-block cluster
   was simply unanswerable before)
2. chat loop: the final step keeps tools (the old forced-plain-text
   turn trapped a model that found its target on the last tool step)
3. goal-line normalizer (raw bush code -> canonical material) +
   forage goals compile deterministically (goto pre-step + forage,
   campaign=True validator gate, raw-cell target field)
4. the goto job verifies ARRIVAL BY POSITION (LastAction flips Ok when
   the bot STARTS moving - 'goto ok' after 10s of a 34-block walk,
   forage preflight then saw 62 blocks); retries failed walks (the
   traverser's 3-repath budget is non-deterministic on hillside)
5. sweep keep lists normalize ids to int at both ends (a string id in
   the roster never matched the int keep list: the mission's own boot
   reaped the agent's body - the chest bank made that free)

**Results (this leg):**
- **35B (qwen3.6-35b-strata, llama.cpp, thinking_budget 3000/4000)**
  A1: COMPLETE. 3 tool calls: query r=64 sphere -> 9 targets ->
  mission dispatched the same turn. Goto arrived, forage measured
  6/3 cranberries. Wall 42s. (Earlier same-night attempts: 48-61s,
  all perception-clean; killed by walls 1-4.)
- **27B (qwen3.8-27b-dual, vLLM, no thinking cap)**
  B1: COMPLETE. 2 queries (one 'base' zone miss, then a point query
  at its own body position r=16 -> 5 targets) -> dispatch -> 5/3.
  Wall 75s.
  B2: perception + dispatch perfect (zone miss, r=32 query, dispatch)
  - walk failed 3x (stuck at 512089,114.8,512042).
  B3: ADAPTIVE - re-read the last failure ('stuck walking into a
  bush's own cell'), picked a different bush with a clear approach.
  Walk failed 3x again (stuck 6 blocks from target).
  B4: 'done' - NO dispatch. The 27B kept session memory across the
  repeated identical request and answered the goal as already
  achieved (B1). A semantic behaviour the 35B does not show (it
  re-executes the same request fresh).

**Verdict.** The '27B cannot plan' reading of leg 1 was wrong in
part: leg 1's failures were mostly the platform walls above, and the
vLLM thinking-budget asymmetry (unbounded thinking eats the 4000
output budget -> 'no reply text'), which looks like a dead model but
is a configuration artifact. With the walls fixed, BOTH models do
perception -> same-turn mission dispatch -> honest reporting. The
35B is the better campaign brain: 1/1 clean completions on every
post-fix attempt, dispatch in 1-2 tool calls, a stable query-first
search posture; the 27B completes on 1/3 (terrain ate the other two)
and has the idiosyncratic memory no-op. 35B stays the default brain;
the 27B is a usable fallback, not a disqualified one.

**Residual platform work (not the brain):**
- The hillside traverser's 3-repath budget is non-deterministic (the
  same short walk fails 3x in a mission but succeeds on the operator's
  immediate retry). Needs its own investigation (hillside-nav report
  follow-up).
- FORAGED FRUIT STAYS ON THE GROUND: the forage job measures the
  delta but nothing picks the berries up or carries them to the camp
  larder. A1+B1 left 11 berries lying at the bush cluster. The
  bank-deposit protocol (campaign persistence) must gain a
  carry-back step.
