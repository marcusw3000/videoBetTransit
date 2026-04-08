using System.Text;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Services;

public static class StreamPathNaming
{
    public static string NormalizeCameraId(string? value, string fallback = "cam_001")
    {
        var raw = string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
        var normalized = new StringBuilder(raw.Length);

        foreach (var ch in raw)
        {
            normalized.Append(char.IsLetterOrDigit(ch) || ch is '-' or '_' ? char.ToLowerInvariant(ch) : '_');
        }

        var result = normalized.ToString().Trim('_');
        return string.IsNullOrWhiteSpace(result) ? fallback : result;
    }

    public static string BuildRawPath(string cameraId) => $"raw/{NormalizeCameraId(cameraId)}";

    public static string BuildProcessedPath(string cameraId) => $"processed/{NormalizeCameraId(cameraId)}";

    public static string ExtractCameraId(StreamSession session)
        => ExtractCameraId(session.ProcessedStreamPath, session.RawStreamPath, session.CameraSource?.Name);

    public static string ExtractCameraId(StreamSessionResponse session)
        => ExtractCameraId(session.ProcessedStreamPath, session.RawStreamPath, session.CameraId, session.CameraName);

    public static string ExtractCameraId(string? processedPath, string? rawPath, params string?[] fallbacks)
    {
        var fromProcessed = ExtractFromPath(processedPath);
        if (!string.IsNullOrWhiteSpace(fromProcessed))
            return fromProcessed;

        var fromRaw = ExtractFromPath(rawPath);
        if (!string.IsNullOrWhiteSpace(fromRaw))
            return fromRaw;

        foreach (var fallback in fallbacks)
        {
            if (!string.IsNullOrWhiteSpace(fallback))
                return NormalizeCameraId(fallback);
        }

        return "cam_001";
    }

    private static string? ExtractFromPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
            return null;

        var trimmed = path.Trim().Trim('/');
        var parts = trimmed.Split('/', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length == 0)
            return null;

        return NormalizeCameraId(parts[^1]);
    }
}
