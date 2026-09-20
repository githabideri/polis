# Bot Manager GUI Fix

> **Status:** Low Priority / Visual Glitch (Known Issue)
> **Date:** 2026-01-03

The Gemini iteration implemented most of the stabilization plan, but the current build never shows the Bot Manager window because the client ignores the 
"open UI" signal coming from the server.

**What happens now:**
- `/polis manage` (or Alt+M) calls the server command `CmdManage`.
- `CmdManage` sends `PolisBotListResponsePacket { Bots = null }` to signal the client to open the GUI even before the bot list is ready.
- The client packet handler `OnBotListResponse` currently does nothing when `Bots` is null, so the dialog is never created/opened and the player only sees a chat message saying nothing was selected.

**Required fix:**
- Treat `Bots = null` as a “show the window now” signal.
- Ensure `botManagerDialog` is instantiated and `TryOpen()` is called whenever that packet arrives, even if there are no bots yet.
- Only skip `UpdateBots` when the payload is null; do not skip dialog creation.

**Sample patch:**
```csharp
private void OnBotListResponse(PolisBotListResponsePacket packet)
{
    if (botManagerDialog == null)
    {
        botManagerDialog = new GuiDialogBotManager(capi, clientChannel);
    }

    if (!botManagerDialog.IsOpened())
    {
        botManagerDialog.TryOpen();
    }

    if (packet.Bots != null)
    {
        botManagerDialog.UpdateBots(packet.Bots);
    }
}
```
With this change, Alt+M opens the manager immediately (even with zero bots), the Close button stays available, and subsequent BotList responses keep the list populated with Spawn/Delete/Select controls.
