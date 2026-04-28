namespace TrafficCounter.Api.Domain.Entities;

public class VehicleCrossingEvent
{
    public Guid Id { get; set; }
    public Guid? RoundId { get; set; }
    public Guid? SessionId { get; set; }
    public StreamSession? Session { get; set; }
    public string CameraId { get; set; } = "default";
    public DateTime TimestampUtc { get; set; }
    public long TrackId { get; set; }
    public string ObjectClass { get; set; } = string.Empty;
    public string Direction { get; set; } = string.Empty;
    public string LineId { get; set; } = string.Empty;
    public long FrameNumber { get; set; }
    public double Confidence { get; set; }
    public string? SnapshotUrl { get; set; }
    public string? Source { get; set; }
    public string? StreamProfileId { get; set; }
    public string? CountMethod { get; set; }
    public int? FallbackBandPx { get; set; }
    public int? CountBefore { get; set; }
    public int? CountAfter { get; set; }
    public string? PreviousEventHash { get; set; }
    public string EventHash { get; set; } = string.Empty;
}
