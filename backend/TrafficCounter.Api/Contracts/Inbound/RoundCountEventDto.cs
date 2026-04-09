namespace TrafficCounter.Api.Contracts.Inbound;

/// <summary>
/// Payload enviado pelo vision worker Python a cada veículo cruzando a linha.
/// </summary>
public class RoundCountEventDto
{
    public string CameraId { get; set; } = string.Empty;
    public string? RoundId { get; set; }
    public string? StreamProfileId { get; set; }
    public string TrackId { get; set; } = string.Empty;
    public string VehicleType { get; set; } = string.Empty;
    public string? Direction { get; set; }
    public string? LineId { get; set; }
    public double? Confidence { get; set; }
    public long? FrameNumber { get; set; }
    public DateTime CrossedAt { get; set; }
    public string? SnapshotUrl { get; set; }
    public string? Source { get; set; }
    public string? PreviousEventHash { get; set; }
    public string? EventHash { get; set; }
    public int? CountBefore { get; set; }
    public int? CountAfter { get; set; }
    public int TotalCount { get; set; }
}
