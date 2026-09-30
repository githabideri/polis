using System;
using System.Threading;
using Vintagestory.API.Client;

/// <summary>
/// Client-side renderer that captures screenshots on demand.
/// Captures must happen during an active OpenGL context (render frame).
///
/// Usage:
/// 1. Call RequestCapture() to queue a capture request
/// 2. On next render frame (EnumRenderStage.Done), capture occurs
/// 3. Result is available via GetLastCaptureResult() or callback
/// </summary>
public class PolisScreenCaptureRenderer : IRenderer
{
    private const string LogPrefix = "[polis-screenshot]";

    private ICoreClientAPI capi;

    // Capture state
    private volatile bool captureRequested;
    private volatile bool saveToFile;
    private string requestedFilePath;

    // Last capture result (thread-safe access)
    private readonly object resultLock = new object();
    private ScreenshotResult lastResult;

    // Callback for async capture completion
    private Action<ScreenshotResult> captureCallback;

    public double RenderOrder => 1.0; // Run after main rendering is done
    public int RenderRange => 0; // Always run (no distance culling)

    public class ScreenshotResult
    {
        public bool Success { get; set; }
        public int Width { get; set; }
        public int Height { get; set; }
        public byte[] PngData { get; set; }
        public string Base64 { get; set; }
        public string FilePath { get; set; }
        public string Error { get; set; }
        public long CaptureTimeMs { get; set; }
    }

    public void Register(ICoreClientAPI capi)
    {
        this.capi = capi;
        // Register for the Done stage - after all rendering is complete
        capi.Event.RegisterRenderer(this, EnumRenderStage.Done, "polis-screenshot-capture");
        capi.Logger.Notification($"{LogPrefix} Renderer registered");
    }

    public void Unregister()
    {
        if (capi != null)
        {
            capi.Event.UnregisterRenderer(this, EnumRenderStage.Done);
            capi.Logger.Notification($"{LogPrefix} Renderer unregistered");
        }
    }

    /// <summary>
    /// Request a screenshot capture on the next render frame.
    /// </summary>
    /// <param name="saveToFile">If true, also saves to file</param>
    /// <param name="filePath">Custom file path, or null for default</param>
    /// <param name="callback">Optional callback when capture completes</param>
    public void RequestCapture(bool saveToFile = false, string filePath = null, Action<ScreenshotResult> callback = null)
    {
        this.saveToFile = saveToFile;
        this.requestedFilePath = filePath;
        this.captureCallback = callback;
        this.captureRequested = true;

        if (capi != null)
        {
            capi.Logger.Debug($"{LogPrefix} Capture requested (saveToFile={saveToFile})");
        }
    }

    /// <summary>
    /// Gets the last capture result. Thread-safe.
    /// </summary>
    public ScreenshotResult GetLastCaptureResult()
    {
        lock (resultLock)
        {
            return lastResult;
        }
    }

    public void OnRenderFrame(float dt, EnumRenderStage stage)
    {
        if (!captureRequested) return;
        captureRequested = false;

        var startTime = DateTime.UtcNow.Ticks;

        try
        {
            // Get viewport dimensions from render API
            var render = capi.Render;
            int width = render.FrameWidth;
            int height = render.FrameHeight;

            if (width <= 0 || height <= 0)
            {
                SetResult(new ScreenshotResult
                {
                    Success = false,
                    Error = $"Invalid frame dimensions: {width}x{height}"
                });
                return;
            }

            capi.Logger.Debug($"{LogPrefix} Capturing {width}x{height} frame");

            // Capture framebuffer
            var rgba = PolisScreenCapture.CaptureFrameRgba(width, height);
            if (rgba == null)
            {
                SetResult(new ScreenshotResult
                {
                    Success = false,
                    Error = "Failed to capture framebuffer"
                });
                return;
            }

            // Encode to PNG
            var pngData = PolisScreenCapture.EncodeToPng(rgba, width, height);
            if (pngData == null)
            {
                SetResult(new ScreenshotResult
                {
                    Success = false,
                    Error = "Failed to encode PNG"
                });
                return;
            }

            var result = new ScreenshotResult
            {
                Success = true,
                Width = width,
                Height = height,
                PngData = pngData,
                Base64 = Convert.ToBase64String(pngData),
                CaptureTimeMs = (DateTime.UtcNow.Ticks - startTime) / TimeSpan.TicksPerMillisecond
            };

            // Save to file if requested
            if (saveToFile)
            {
                string path = requestedFilePath ?? PolisScreenCapture.GetDefaultScreenshotPath();
                if (PolisScreenCapture.SaveToPng(rgba, width, height, path))
                {
                    result.FilePath = path;
                    capi.Logger.Notification($"{LogPrefix} Screenshot saved: {path}");
                }
                else
                {
                    capi.Logger.Warning($"{LogPrefix} Failed to save screenshot to: {path}");
                }
            }

            capi.Logger.Debug($"{LogPrefix} Capture complete: {width}x{height}, {pngData.Length} bytes, {result.CaptureTimeMs}ms");
            SetResult(result);
        }
        catch (Exception ex)
        {
            capi.Logger.Error($"{LogPrefix} Capture error: {ex.Message}");
            SetResult(new ScreenshotResult
            {
                Success = false,
                Error = ex.Message
            });
        }
    }

    private void SetResult(ScreenshotResult result)
    {
        lock (resultLock)
        {
            lastResult = result;
        }

        // Invoke callback if set
        var callback = captureCallback;
        captureCallback = null;
        callback?.Invoke(result);
    }

    public void Dispose()
    {
        Unregister();
    }
}
