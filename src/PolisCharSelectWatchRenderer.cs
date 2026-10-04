using System;
using Vintagestory.API.Client;

namespace Polis
{
    /// <summary>
    /// Bounded client-side safety net against the "character-selection wedge":
    /// the survival mod opens GuiDialogCreateCharacter when a player joins
    /// without the "createCharacter" moddata, and that dialog pauses the game
    /// (PauseGame(true) in OnGuiOpened) - which in a singleplayer world
    /// suspends the server tick (ClientProgram suspends while IsGamePaused)
    /// and freezes every game-tick-driven behavior, including this mod's bots.
    ///
    /// The Polis mod sets the moddata server-side on save load (see
    /// PolisSystem.ConfirmCharacterSelectionForPlayers), so the dialog never
    /// opens in the first place. This renderer is the belt to that
    /// suspenders: it runs on render frames, which keep going even while the
    /// game is suspended (the pause menu still renders), so it can close the
    /// dialog and unpause the game in situations where no game-tick callback
    /// would ever fire again.
    ///
    /// It only arms for ~15s of wall-clock after LevelFinalize (the window in
    /// which the join-time auto-open happens), then stops checking - a dialog
    /// a human opens later (F10 / charsel) is never touched.
    /// </summary>
    internal class PolisCharSelectWatchRenderer : IRenderer
    {
        static readonly long WatchWindowMs = 15_000;

        readonly ICoreClientAPI capi;
        long armedAtMs;
        bool closedOnce;

        public PolisCharSelectWatchRenderer(ICoreClientAPI capi)
        {
            this.capi = capi;
        }

        public void Register()
        {
            capi.Event.RegisterRenderer(this, EnumRenderStage.Before, "polis-charselect-watch");
            capi.Logger.Debug("[polis] charselect watch renderer registered");
        }

        /// <summary>Arm the bounded watch window (called on LevelFinalize).</summary>
        public void Arm()
        {
            armedAtMs = Environment.TickCount64;
            closedOnce = false;
        }

        public void OnRenderFrame(float deltaTime, EnumRenderStage stage)
        {
            if (armedAtMs == 0)
                return;
            if (Environment.TickCount64 - armedAtMs > WatchWindowMs)
            {
                armedAtMs = 0;
                return;
            }
            if (closedOnce)
                return;

            foreach (object gui in capi.OpenedGuis)
            {
                if (gui is Vintagestory.GameContent.GuiDialogCreateCharacter dlg)
                {
                    closedOnce = true;
                    armedAtMs = 0;
                    capi.Logger.Notification("[polis] closing auto-opened character-selection dialog (unpausing game)");
                    dlg.TryClose();
                    return;
                }
            }
        }

        public void Dispose()
        {
            // nothing to dispose
        }
    }
}
