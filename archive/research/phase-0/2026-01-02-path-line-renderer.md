# Research: Client-Side Path Line Renderer

## Context
Goal: Replace the clunky server-side block highlight path visualization with a smooth client-side line renderer using actual waypoints.

## 1. Networking (Server to Client)
Pathfinding is calculated on the server, but rendering must happen on the client.

### Network Channel
Register a dedicated channel in both Client and Server ModSystems:
```csharp
// In StartServerSide and StartClientSide
var channel = api.Network.RegisterChannel("polis-path")
    .RegisterMessageType<PolisPathPacket>();
```

### Data Packet
```csharp
[ProtoContract]
public class PolisPathPacket {
    [ProtoMember(1)]
    public Vec3d[] Waypoints;
    [ProtoMember(2)]
    public int Color; // Optional: custom colors for different bots/states
}
```

## 2. Client-Side Rendering
Implement `IRenderer` to draw the path segments.

### Registration
```csharp
capi.Event.RegisterRenderer(this, EnumRenderStage.Opaque, "polis-path-debug");
```

### Rendering Logic (`OnRenderFrame`)
Use `capi.Render.RenderLine` for simplicity. To maintain precision at high coordinates, use the player's position as the origin.

```csharp
// Example rendering loop
EntityPlayer player = capi.World.Player.Entity;
BlockPos origin = player.Pos.AsBlockPos;

for (int i = 0; i < waypoints.Length - 1; i++) {
    Vec3d p1 = waypoints[i];
    Vec3d p2 = waypoints[i+1];
    
    capi.Render.RenderLine(
        origin,
        (float)(p1.X - origin.X), (float)(p1.Y - origin.Y), (float)(p1.Z - origin.Z),
        (float)(p2.X - origin.X), (float)(p2.Y - origin.Y), (float)(p2.Z - origin.Z),
        pathColor
    );
}
```

## 3. Integration Plan
1. **Server:** In `PolisGotoAction`, replace or supplement the `debugPath` callback.
2. **Packet Send:** Instead of `HighlightPath` (which uses `sapi.World.HighlightBlocks`), send the `PolisPathPacket` to the controlling player.
3. **Client:** `PolisPathRenderer` receives the packet, stores the waypoints, and draws them until cleared or updated.

## 4. Why This Approach?
- **Improves Clarity:** Lines show exact navigation paths through tight spaces (e.g., doors, tall grass).
- **Reduces Server Load:** Moving visualization to the client removes the need for the server to track and time-out block highlights for every movement.
- **Better Debugging:** Precise waypoint lines help identify why pathing fails at specific corners or slopes.
