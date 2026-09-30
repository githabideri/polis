using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;

/// <summary>
/// Log levels for WebSocket event streaming.
/// Clients subscribe at a level and receive that level and all levels below it.
/// </summary>
public enum PolisLogLevel
{
    /// <summary>Key events only: action_complete, bot_spawned, bot_died, debug_toggled</summary>
    Normal = 0,

    /// <summary>Normal + state changes, warnings, bot_unloaded</summary>
    Info = 1,

    /// <summary>Info + internal debug details, path calculations</summary>
    Debug = 2
}

/// <summary>
/// A single event to be broadcast to WebSocket clients.
/// </summary>
public class PolisEvent
{
    public string Type { get; }
    public PolisLogLevel Level { get; }
    public object Data { get; }
    public long Timestamp { get; }

    public PolisEvent(string type, PolisLogLevel level, object data)
    {
        Type = type;
        Level = level;
        Data = data;
        Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    }

    public string ToJson()
    {
        return JsonSerializer.Serialize(new
        {
            type = Type,
            level = (int)Level,
            data = Data,
            ts = Timestamp
        }, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
    }
}

/// <summary>
/// Manages WebSocket connections and broadcasts events to subscribed clients.
/// Thread-safe: events can be queued from any thread (game thread),
/// broadcast loop runs on its own dedicated task.
/// </summary>
public class PolisEventBroadcaster : IDisposable
{
    private readonly Channel<PolisEvent> eventChannel;
    private readonly ConcurrentDictionary<string, WebSocketConnection> connections;
    private readonly ConcurrentQueue<PolisEvent> eventHistory;
    private readonly CancellationTokenSource cts;
    private readonly Task broadcastTask;
    private readonly Action<string> logAction;
    private bool disposed;

    private const int MaxQueueSize = 1000;
    private const int MaxHistorySize = 100;
    private const string LogPrefix = "[polis-ws]";

    public int ConnectionCount => connections.Count;

    /// <summary>
    /// Get recent event history (newest first).
    /// </summary>
    public IEnumerable<PolisEvent> GetEventHistory() => eventHistory.Reverse().Take(MaxHistorySize);

    public PolisEventBroadcaster(Action<string> logAction = null)
    {
        this.logAction = logAction;
        connections = new ConcurrentDictionary<string, WebSocketConnection>();
        eventHistory = new ConcurrentQueue<PolisEvent>();
        cts = new CancellationTokenSource();

        // Bounded channel with DropOldest to prevent memory pressure
        eventChannel = Channel.CreateBounded<PolisEvent>(new BoundedChannelOptions(MaxQueueSize)
        {
            FullMode = BoundedChannelFullMode.DropOldest,
            SingleReader = true,
            SingleWriter = false
        });

        broadcastTask = Task.Run(BroadcastLoopAsync);
    }

    /// <summary>
    /// Queue an event for broadcast. Called from game thread - non-blocking.
    /// </summary>
    public void QueueEvent(PolisEvent evt)
    {
        if (disposed || evt == null) return;

        // Add to history (trim if over limit)
        eventHistory.Enqueue(evt);
        while (eventHistory.Count > MaxHistorySize)
        {
            eventHistory.TryDequeue(out _);
        }

        // TryWrite is non-blocking; if channel is full, DropOldest kicks in
        if (!eventChannel.Writer.TryWrite(evt))
        {
            logAction?.Invoke($"{LogPrefix} Event channel full, dropping event: {evt.Type}");
        }
    }

    /// <summary>
    /// Queue an event with inline construction.
    /// </summary>
    public void QueueEvent(string type, PolisLogLevel level, object data)
    {
        QueueEvent(new PolisEvent(type, level, data));
    }

    /// <summary>
    /// Add a new WebSocket connection with default Normal subscription level.
    /// Returns connection ID for later reference.
    /// </summary>
    public string AddConnection(WebSocket socket, PolisLogLevel initialLevel = PolisLogLevel.Normal)
    {
        var connId = Guid.NewGuid().ToString("N")[..8];
        var conn = new WebSocketConnection(socket, initialLevel);
        connections[connId] = conn;

        logAction?.Invoke($"{LogPrefix} Connection added: {connId} (level={initialLevel})");
        return connId;
    }

    /// <summary>
    /// Remove a connection (e.g., on disconnect).
    /// </summary>
    public void RemoveConnection(string connId)
    {
        if (connections.TryRemove(connId, out var conn))
        {
            conn.Dispose();
            logAction?.Invoke($"{LogPrefix} Connection removed: {connId}");
        }
    }

    /// <summary>
    /// Update subscription level for an existing connection.
    /// </summary>
    public void UpdateSubscription(string connId, PolisLogLevel level)
    {
        if (connections.TryGetValue(connId, out var conn))
        {
            conn.SubscribedLevel = level;
            logAction?.Invoke($"{LogPrefix} Connection {connId} subscribed to level {level}");
        }
    }

    /// <summary>
    /// Main broadcast loop - runs on dedicated task, reads from channel, sends to all subscribers.
    /// </summary>
    private async Task BroadcastLoopAsync()
    {
        try
        {
            await foreach (var evt in eventChannel.Reader.ReadAllAsync(cts.Token))
            {
                await BroadcastEventAsync(evt);
            }
        }
        catch (OperationCanceledException)
        {
            // Expected on shutdown
        }
        catch (Exception ex)
        {
            logAction?.Invoke($"{LogPrefix} Broadcast loop error: {ex.Message}");
        }
    }

    private async Task BroadcastEventAsync(PolisEvent evt)
    {
        if (connections.IsEmpty) return;

        var json = evt.ToJson();
        var bytes = Encoding.UTF8.GetBytes(json);
        var segment = new ArraySegment<byte>(bytes);

        foreach (var kvp in connections)
        {
            var connId = kvp.Key;
            var conn = kvp.Value;

            // Check subscription level filter
            if ((int)evt.Level > (int)conn.SubscribedLevel)
                continue;

            // Check socket state
            if (conn.Socket.State != WebSocketState.Open)
            {
                RemoveConnection(connId);
                continue;
            }

            try
            {
                await conn.SendAsync(segment, cts.Token);
            }
            catch (WebSocketException)
            {
                RemoveConnection(connId);
            }
            catch (OperationCanceledException)
            {
                // Shutdown
                break;
            }
            catch (Exception ex)
            {
                logAction?.Invoke($"{LogPrefix} Send error to {connId}: {ex.Message}");
                RemoveConnection(connId);
            }
        }
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;

        cts.Cancel();
        eventChannel.Writer.Complete();

        try
        {
            broadcastTask.Wait(TimeSpan.FromSeconds(2));
        }
        catch { }

        foreach (var conn in connections.Values)
        {
            conn.Dispose();
        }
        connections.Clear();

        cts.Dispose();
        logAction?.Invoke($"{LogPrefix} Broadcaster disposed");
    }

    /// <summary>
    /// Represents a single WebSocket connection with its subscription preferences.
    /// </summary>
    private class WebSocketConnection : IDisposable
    {
        public WebSocket Socket { get; }
        public PolisLogLevel SubscribedLevel { get; set; }
        private readonly SemaphoreSlim sendLock = new(1, 1);
        private bool disposed;

        public WebSocketConnection(WebSocket socket, PolisLogLevel level)
        {
            Socket = socket;
            SubscribedLevel = level;
        }

        /// <summary>
        /// Thread-safe send with semaphore to prevent concurrent writes.
        /// </summary>
        public async Task SendAsync(ArraySegment<byte> data, CancellationToken ct)
        {
            if (disposed || Socket.State != WebSocketState.Open) return;

            await sendLock.WaitAsync(ct);
            try
            {
                if (Socket.State == WebSocketState.Open)
                {
                    await Socket.SendAsync(data, WebSocketMessageType.Text, true, ct);
                }
            }
            finally
            {
                sendLock.Release();
            }
        }

        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            sendLock.Dispose();

            try
            {
                if (Socket.State == WebSocketState.Open || Socket.State == WebSocketState.CloseReceived)
                {
                    Socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Server shutdown", CancellationToken.None)
                        .Wait(TimeSpan.FromSeconds(1));
                }
            }
            catch { }
        }
    }
}

/// <summary>
/// Messages that clients can send to the WebSocket server.
/// </summary>
public class WsClientMessage
{
    public WsSubscription Subscribe { get; set; }
}

public class WsSubscription
{
    public string Level { get; set; }

    public PolisLogLevel GetLevel()
    {
        return Level?.ToLowerInvariant() switch
        {
            "debug" => PolisLogLevel.Debug,
            "info" => PolisLogLevel.Info,
            _ => PolisLogLevel.Normal
        };
    }
}
