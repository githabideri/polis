using System;
using System.IO;
using OpenTK.Graphics.OpenGL4;
using SkiaSharp;
using Vintagestory.API.Client;

/// <summary>
/// Screenshot capture utility for polis.
/// Uses OpenGL glReadPixels via OpenTK to capture the current framebuffer.
///
/// IMPORTANT: Must be called during an active OpenGL context (in IRenderer callback).
/// </summary>
public static class PolisScreenCapture
{
    private const string LogPrefix = "[polis-screenshot]";

    /// <summary>
    /// Captures the current framebuffer contents as RGBA byte array.
    /// Must be called from within an IRenderer.OnRenderFrame callback.
    /// </summary>
    /// <param name="width">Viewport width in pixels</param>
    /// <param name="height">Viewport height in pixels</param>
    /// <returns>RGBA byte array (4 bytes per pixel), or null on error</returns>
    public static byte[] CaptureFrameRgba(int width, int height)
    {
        if (width <= 0 || height <= 0) return null;

        try
        {
            byte[] pixels = new byte[width * height * 4];
            GL.ReadPixels(0, 0, width, height, PixelFormat.Rgba, PixelType.UnsignedByte, pixels);

            // OpenGL origin is bottom-left, flip vertically for correct orientation
            FlipVertically(pixels, width, height);

            return pixels;
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"{LogPrefix} CaptureFrameRgba error: {ex.Message}");
            return null;
        }
    }

    /// <summary>
    /// Flips RGBA pixel data vertically in-place.
    /// </summary>
    private static void FlipVertically(byte[] pixels, int width, int height)
    {
        int rowBytes = width * 4;
        byte[] tempRow = new byte[rowBytes];

        for (int y = 0; y < height / 2; y++)
        {
            int topOffset = y * rowBytes;
            int bottomOffset = (height - 1 - y) * rowBytes;

            // Swap rows
            System.Buffer.BlockCopy(pixels, topOffset, tempRow, 0, rowBytes);
            System.Buffer.BlockCopy(pixels, bottomOffset, pixels, topOffset, rowBytes);
            System.Buffer.BlockCopy(tempRow, 0, pixels, bottomOffset, rowBytes);
        }
    }

    /// <summary>
    /// Encodes RGBA pixel data to PNG format.
    /// </summary>
    /// <param name="rgba">RGBA pixel data</param>
    /// <param name="width">Image width</param>
    /// <param name="height">Image height</param>
    /// <returns>PNG byte array, or null on error</returns>
    public static byte[] EncodeToPng(byte[] rgba, int width, int height)
    {
        if (rgba == null || rgba.Length != width * height * 4) return null;

        try
        {
            using (var bitmap = new SKBitmap(width, height, SKColorType.Rgba8888, SKAlphaType.Unpremul))
            {
                // Copy pixel data to bitmap
                var handle = System.Runtime.InteropServices.GCHandle.Alloc(rgba, System.Runtime.InteropServices.GCHandleType.Pinned);
                try
                {
                    bitmap.InstallPixels(bitmap.Info, handle.AddrOfPinnedObject(), width * 4);
                }
                finally
                {
                    handle.Free();
                }

                using (var image = SKImage.FromBitmap(bitmap))
                using (var data = image.Encode(SKEncodedImageFormat.Png, 100))
                {
                    return data.ToArray();
                }
            }
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"{LogPrefix} EncodeToPng error: {ex.Message}");
            return null;
        }
    }

    /// <summary>
    /// Saves RGBA pixel data to a PNG file.
    /// </summary>
    /// <param name="rgba">RGBA pixel data</param>
    /// <param name="width">Image width</param>
    /// <param name="height">Image height</param>
    /// <param name="filePath">Output file path</param>
    /// <returns>True if saved successfully</returns>
    public static bool SaveToPng(byte[] rgba, int width, int height, string filePath)
    {
        var pngData = EncodeToPng(rgba, width, height);
        if (pngData == null) return false;

        try
        {
            // Ensure directory exists
            var dir = Path.GetDirectoryName(filePath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }

            File.WriteAllBytes(filePath, pngData);
            return true;
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"{LogPrefix} SaveToPng error: {ex.Message}");
            return false;
        }
    }

    /// <summary>
    /// Converts PNG byte array to base64 string.
    /// </summary>
    public static string ToBase64(byte[] pngData)
    {
        return pngData != null ? Convert.ToBase64String(pngData) : null;
    }

    /// <summary>
    /// Captures current framebuffer and returns as base64-encoded PNG.
    /// Must be called from within an IRenderer.OnRenderFrame callback.
    /// </summary>
    public static string CaptureToBase64Png(int width, int height)
    {
        var rgba = CaptureFrameRgba(width, height);
        if (rgba == null) return null;

        var png = EncodeToPng(rgba, width, height);
        return ToBase64(png);
    }

    /// <summary>
    /// Generates a default screenshot path with timestamp.
    /// </summary>
    public static string GetDefaultScreenshotPath()
    {
        var picturesDir = Environment.GetFolderPath(Environment.SpecialFolder.MyPictures);
        var polisDir = Path.Combine(picturesDir, "Vintagestory", "polis");
        var timestamp = DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss-fff");
        return Path.Combine(polisDir, $"screenshot-{timestamp}.png");
    }
}
