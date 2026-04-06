namespace TrafficCounter.Api.Contracts.Inbound;

/// <summary>
/// Payload enviado pelo vision worker Python a cada veículo cruzando a linha.
/// </summary>
public class RoundCountEventDto
{
    public string CameraId { get; set; } = string.Empty;
    public string? RoundId { get; set; }
    public string TrackId { get; set; } = string.Empty;
    public string VehicleType { get; set; } = string.Empty;
    public DateTime CrossedAt { get; set; }
    public string? SnapshotUrl { get; set; }
    public int TotalCount { get; set; }
}
