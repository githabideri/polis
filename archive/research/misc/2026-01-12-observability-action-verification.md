# Observability and Action Verification (R4)

Date: 2026-01-12

Purpose
Confirm how the mod can verify actions (spawn, move, pickup) programmatically and what signals exist for completion/failure, to drive the agentic harness.

Summary
- The harness already exposes a polling-friendly state API (`/polis/state`) that includes bot position, nearby item entities, and `LastAction` (name/ok/msg) for recent pickup/drop actions.
- Pickup/drop verification is implemented via action callbacks that record `BotState.LastAction*` and can be verified by combining `LastAction` with inventory + nearby item state.
- Movement verification (goto) has completion/failure callbacks in `PolisGotoAction` (`OnDone`, `OnStuck`, `OnNoPath`) but does not currently record `LastAction`, so harness verification must rely on position polling or debug logs.
- Entity interaction/attack uses debug logs and can emit before/after hurt/health numbers, but does not surface a structured result in `LastAction`.
- btca (vssurvivalmod) confirms the vanilla action system signals completion via `IsFinished()` and failure via `ExecutionHasFailed`, with `EntityActivity.Finished` used to advance/complete activities.
- btca (vsapi) does not expose `EntityActivitySystem`, `EntityActivity`, or `EntityActionBase`; only `EnumEntityActivity` and `EntityAgent.CurrentControls` appear in the public API, so activity/action completion details are engine or survivalmod-level, not in vsapi.

Evidence
- `polis-builder-npc/PolisBuilderNpcSystem.cs` (BotState fields + `RecordActionResult`; `CmdTestState` log output; `GetTestStateResult` builds `LastAction` in state JSON).
- `polis-builder-npc/PolisTestHarness.cs` (`TestStateResult.ActionInfo` fields: `Name`, `Ok`, `Msg`).
- `polis-builder-npc/PolisPickupItemAction.cs` and `polis-builder-npc/PolisDropItemAction.cs` (result callbacks invoked on `Succeed/Fail` with explicit failure reasons).
- `polis-builder-npc/PolisBuilderNpcSystem.cs` (`CmdPickup`/`CmdDrop` wire result callbacks to `RecordActionResult`).
- `polis-builder-npc/PolisBuilderNpcSystem.cs` (`PolisGotoAction` uses `OnDone`, `OnStuck`, `OnNoPath` and debug logs; no `RecordActionResult`).
- `polis-builder-npc/PolisInteractEntityAction.cs` (debug logging for interactions; attack logs before/after `onHurtCounter` and `Health`).
- `polis-builder-npc/scripts/polis-http-smoke.py` (state polling to verify drop/pickup and goto distance thresholds).
- `polis-builder-npc/docs/TESTING_HARNESS.md` (documented `LastAction` and verification patterns).
- btca vssurvivalmod: `vssurvivalmod/Systems/EntityActivitySystem/EntityActivitySystem.cs` (`EntityActivity.Finished` checked in `OnTick`).
- btca vssurvivalmod: `vssurvivalmod/Systems/EntityActivitySystem/EntityActivity.cs` (`OnTick` advances actions when `CurrentAction.IsFinished()`; sets `Finished = true` when action list ends).
- btca vssurvivalmod: `vssurvivalmod/Systems/EntityActivitySystem/Action/GotoAction.cs` (`IsFinished` returns `done || ExecutionHasFailed`; `OnDone`, `OnStuck`, `OnNoPath` set `done` or `ExecutionHasFailed`).
- btca vsapi: `vsapi/Common/Entity/EnumEntityActivity.cs` (public activity enum only).
- btca vsapi: `vsapi/Common/Entity/EntityAgent.cs` (`CurrentControls` field; no activity system implementation).

Open questions
- Should `LastActionMs` (stored in `BotState`) be exposed in `/polis/state` for more precise timing/ordering?
- Do we want structured results for non-pickup/drop actions (goto, interact, activate, break, place), or is position/state polling sufficient?
- Is there a need for per-action IDs or sequence numbers to disambiguate overlapping commands in the harness UI?

Implications for harness design
- Use `/polis/state` polling as the primary verification mechanism: bot `Pos`, `Items` list, and `LastAction` for pickup/drop.
- For movement verification, use distance-to-target checks (as in `scripts/polis-http-smoke.py`); debug logs are secondary evidence only.
- For interaction/attack verification, consider checking target health/attributes externally if needed; current action only logs diagnostics.
- Suggested structured action result fields (if expanded beyond pickup/drop): `Name`, `Ok`, `Msg`, `Ms`, `TargetId`, `TargetPos`, `Range`, `Dist`, `ItemCode`, `Qty`, `Mode` (for interact), `PathKind` (astar vs line), and a monotonic `ActionId` for correlation.
