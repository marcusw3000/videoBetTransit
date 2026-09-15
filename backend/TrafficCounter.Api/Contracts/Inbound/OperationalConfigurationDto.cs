using System.ComponentModel.DataAnnotations;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace TrafficCounter.Api.Contracts.Inbound;

public sealed class OperationalConfigurationDto
{
    [Required, StringLength(128)] public string CameraId { get; set; } = "";
    [Required, StringLength(128)] public string StreamProfileId { get; set; } = "";
    [Required, StringLength(4096)] public string SourceUrl { get; set; } = "";
    public Dictionary<string, double> Roi { get; set; } = [];
    public Dictionary<string, double> Line { get; set; } = [];
    public string CountDirection { get; set; } = "";
    public bool SecondaryVerificationEnabled { get; set; }
    public int SecondaryVerificationBandPx { get; set; }
    public bool AllowSettling { get; set; }

    public string ToSnapshot()
    {
        if (string.IsNullOrWhiteSpace(CameraId) || string.IsNullOrWhiteSpace(StreamProfileId)
            || string.IsNullOrWhiteSpace(SourceUrl) || CountDirection is not ("up" or "down" or "left" or "right" or "any")
            || !Valid(Roi, ["x", "y", "w", "h"]) || !Valid(Line, ["x1", "y1", "x2", "y2"])
            || Roi["w"] <= 0 || Roi["h"] <= 0 || SecondaryVerificationBandPx < 0)
            throw new ArgumentException("Configuracao operacional incompleta ou invalida.");
        return JsonSerializer.Serialize(new {
            schemaVersion = 1, cameraId = CameraId.Trim(), streamProfileId = StreamProfileId.Trim(),
            sourceFingerprint = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(SourceUrl.Trim()))).ToLowerInvariant(),
            roi = Roi.OrderBy(p => p.Key).ToDictionary(p => p.Key, p => p.Value),
            line = Line.OrderBy(p => p.Key).ToDictionary(p => p.Key, p => p.Value),
            countDirection = CountDirection, secondaryVerificationEnabled = SecondaryVerificationEnabled,
            secondaryVerificationBandPx = SecondaryVerificationBandPx
        });
    }

    private static bool Valid(Dictionary<string, double>? values, string[] keys) =>
        values is not null && values.Count == keys.Length && keys.All(k => values.TryGetValue(k, out var n) && double.IsFinite(n));
}
