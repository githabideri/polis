using System;
using Vintagestory.API.Client;
using Vintagestory.API.Common;

public class PolisHotkeys : ModSystem
{
    ICoreClientAPI capi;
    bool previewEnabled;
    bool previewArmed;

    public override bool ShouldLoad(EnumAppSide forSide)
    {
        return forSide == EnumAppSide.Client;
    }

    public override void StartClientSide(ICoreClientAPI api)
    {
        capi = api;

        RegisterHotkey("polis-spawn", "Polis: Spawn/select bot", GlKeys.N, "/polis spawn");
        RegisterHotkey("polis-selectlook", "Polis: Select looked-at bot", GlKeys.L, "/polis selectlook");
        RegisterHotkey("polis-goto", "Polis: Goto look direction", GlKeys.G, "/polis gotolook 256");
        RegisterPreviewHotkey();
        RegisterHotkey("polis-activate", "Polis: Activate looked-at", GlKeys.A, "/polis activate l[]");
        RegisterHotkey("polis-break", "Polis: Break looked-at", GlKeys.B, "/polis break l[]");
        RegisterHotkey("polis-placeheld", "Polis: Place held block", GlKeys.H, "/polis placeheld");
        RegisterHotkey("polis-stop", "Polis: Stop bot", GlKeys.S, "/polis stop");
        RegisterHotkey("polis-debug", "Polis: Toggle debug", GlKeys.D, "/polis debug");
        RegisterHotkey("polis-pathdump", "Polis: Dump path data", GlKeys.P, "/polis pathdump");
        RegisterHotkey("polis-manage", "Polis: Bot Manager", GlKeys.M, "/polis manage");
        RegisterHotkey("polis-possess", "Polis: Possess selected bot", GlKeys.U, "/polis possess");
        RegisterHotkey("polis-unpossess", "Polis: Exit possession", GlKeys.U, "/polis unpossess", alt: true, shift: true);

        capi.Input.RegisterHotKey("polis-panic", "Polis: Emergency UI Reset", GlKeys.P, HotkeyType.GUIOrOtherControls, altPressed: true, shiftPressed: true);
        capi.Input.SetHotKeyHandler("polis-panic", OnPanicHotkey);

        // Phase 1.5: Register client-side possession smoothing handler
        var possessionHandler = new PolisClientPossessionHandler();
        possessionHandler.Register(capi);

        capi.Event.MouseDown += OnMouseDown;
    }

    private bool OnPanicHotkey(KeyCombination comb)
    {
        var opened = capi.Gui.OpenedGuis.ToArray();
        foreach (var dlg in opened)
        {
            if (dlg is GuiDialogBotManager || dlg.GetType().Name.StartsWith("GuiDialogBot"))
            {
                dlg.TryClose();
                capi.Gui.TriggerDialogClosed(dlg);
            }
        }
        
        capi.ShowChatMessage("Polis UI Emergency Reset Executed.");
        return true;
    }

    void RegisterHotkey(string code, string name, GlKeys key, string command, bool alt = true, bool shift = false)
    {
        capi.Input.RegisterHotKey(code, name, key, HotkeyType.GUIOrOtherControls, altPressed: alt, shiftPressed: shift);
        capi.Input.SetHotKeyHandler(code, _ => SendCommand(command));
    }

    void RegisterPreviewHotkey()
    {
        const string code = "polis-preview";
        capi.Input.RegisterHotKey(code, "Polis: Toggle path preview", GlKeys.G, HotkeyType.GUIOrOtherControls, altPressed: true, shiftPressed: true);
        capi.Input.SetHotKeyHandler(code, _ =>
        {
            previewEnabled = !previewEnabled;
            previewArmed = previewEnabled;
            SendCommand("/polis preview toggle");
            return true;
        });
    }

    void OnMouseDown(MouseEvent e)
    {
        if (!previewArmed) return;
        if (e.Handled) return;
        if (e.Button != EnumMouseButton.Left) return;
        if (!capi.Input.MouseGrabbed) return;

        previewArmed = false;
        SendCommand("/polis preview commit");
        e.Handled = true;
    }

    public override void Dispose()
    {
        if (capi != null)
        {
            capi.Event.MouseDown -= OnMouseDown;
        }
    }

    bool SendCommand(string command)
    {
        if (string.IsNullOrWhiteSpace(command)) return false;
        capi.SendChatMessage(command);
        return true;
    }
}
