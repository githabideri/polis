using System;
using System.Collections.Generic;
using Vintagestory.API.Client;
using Vintagestory.API.Common;
using Vintagestory.API.Config;
using Vintagestory.API.MathTools;

public class GuiDialogBotManager : GuiDialog
{
    private IClientNetworkChannel channel;
    private List<PolisBotEntry> bots = new List<PolisBotEntry>();

    public override string ToggleKeyCombinationCode => "polis-manage";

    public GuiDialogBotManager(ICoreClientAPI capi, IClientNetworkChannel channel) : base(capi)
    {
        this.channel = channel;
    }

    public override void OnGuiOpened()
    {
        base.OnGuiOpened();
        channel.SendPacket(new PolisBotListRequestPacket());
        recompose();
    }

    public void UpdateBots(PolisBotEntry[] newBots)
    {
        int oldCount = this.bots.Count;
        int newCount = newBots?.Length ?? 0;
        
        this.bots = new List<PolisBotEntry>(newBots);
        
        if (IsOpened())
        {
            capi.Event.EnqueueMainThreadTask(recompose, "polis-bot-manager-refresh");
        }
    }

    public void ShowDebugInfo(string message)
    {
        capi.ShowChatMessage($"[polis] {message}");
    }

    private void recompose()
    {
        capi.ShowChatMessage($"[polis] Recompose: {this.bots.Count} bots to render");
        
        // 1. Root Dialog Bounds
        ElementBounds dialogBounds = ElementStdBounds.AutosizedMainDialog.WithAlignment(EnumDialogArea.CenterMiddle);
        ElementBounds bgBounds = ElementBounds.Fill.WithFixedPadding(GuiStyle.ElementToDialogPadding);
        bgBounds.BothSizing = ElementSizing.FitToChildren;

        // Title and Header
        ElementBounds titleBounds = ElementBounds.Fixed(0, 0, 400, 30);
        ElementBounds spawnButtonBounds = ElementBounds.Fixed(0, 40, 150, 30);
        ElementBounds headerBounds = ElementBounds.Fixed(0, 80, 400, 25);

        var composer = capi.Gui
            .CreateCompo("polis-bot-manager", dialogBounds)
            .AddShadedDialogBG(bgBounds)
            .AddDialogTitleBar("Polis Bot Manager", () => TryClose())
            .BeginChildElements(bgBounds)
                .AddButton("Spawn Bot", OnSpawnClick, spawnButtonBounds)
                .AddStaticText("ID | Type | Distance", CairoFont.WhiteSmallText().WithWeight(Cairo.FontWeight.Bold), headerBounds);

        // 2. Add bots to the composer
        double y = 110;
        if (bots.Count == 0)
        {
            composer.AddStaticText("No bots tracked.", CairoFont.WhiteSmallText(), ElementBounds.Fixed(0, y, 400, 30));
            y += 40;
        }
        else
        {
            for (int i = 0; i < bots.Count; i++)
            {
                var bot = bots[i];
                var plrPos = capi.World.Player.Entity.Pos;
                double dist = Math.Sqrt(plrPos.SquareDistanceTo(bot.X, bot.Y, bot.Z));
                
                // Show load status indicator
                string loadStatus = bot.IsLoaded ? "" : " [FAR]";
                string text = $"{(bot.IsSelected ? ">> " : "")}{bot.EntityId}: {botCodeShort(bot.Code)} ({dist:0.0}m){loadStatus}";

                ElementBounds textBounds = ElementBounds.Fixed(0, y + 5, 250, 30);
                ElementBounds selectBounds = ElementBounds.Fixed(260, y, 60, 30);
                ElementBounds deleteBounds = ElementBounds.Fixed(330, y, 60, 30);

                // Gray out unloaded bots
                CairoFont font;
                if (!bot.IsLoaded)
                {
                    font = CairoFont.WhiteSmallText().WithColor(new double[] { 0.6, 0.6, 0.6, 1.0 });
                }
                else if (bot.IsSelected)
                {
                    font = CairoFont.WhiteSmallText().WithWeight(Cairo.FontWeight.Bold);
                }
                else
                {
                    font = CairoFont.WhiteSmallText();
                }
                
                composer.AddStaticText(text, font, textBounds);
                
                long id = bot.EntityId;
                bool isLoaded = bot.IsLoaded;
                
                // Only allow selection if loaded
                composer.AddSmallButton(isLoaded ? "Sel" : "---", () => {
                    if (isLoaded)
                    {
                        channel.SendPacket(new PolisBotActionPacket { EntityId = id, Action = "select" });
                    }
                    return true;
                }, selectBounds);
                
                // Allow deletion regardless of load state
                composer.AddSmallButton("Del", () => {
                    channel.SendPacket(new PolisBotActionPacket { EntityId = id, Action = "delete" });
                    return true;
                }, deleteBounds);

                y += 40;
            }
        }

        // 3. Focus Anchor (Safety button to prevent hang)
        ElementBounds closeButtonBounds = ElementBounds.Fixed(0, y + 10, 400, 30);
        composer.AddButton("Close Manager", () => TryClose(), closeButtonBounds);
        
        // 4. Telemetry
        composer.AddStaticText($"F: {Focused}", CairoFont.WhiteSmallText().WithColor(new double[]{1,1,1,0.3}), ElementBounds.Fixed(0, y + 50, 400, 20));

        SingleComposer = composer.EndChildElements().Compose();
        
        // 5. Explicitly request focus to prevent "Focus Trap"
        capi.Gui.RequestFocus(this);
    }

    private bool OnSpawnClick()
    {
        channel.SendPacket(new PolisBotActionPacket { Action = "spawn" });
        return true;
    }

    private string botCodeShort(string code)
    {
        if (string.IsNullOrEmpty(code)) return "bot";
        int idx = code.IndexOf(':');
        return idx >= 0 ? code.Substring(idx + 1) : code;
    }

    public override bool OnEscapePressed()
    {
        TryClose();
        return true;
    }

    public override void OnKeyUp(KeyEvent e)
    {
        if (e.KeyCode == (int)GlKeys.Escape)
        {
            TryClose();
        }
        base.OnKeyUp(e);
    }
}