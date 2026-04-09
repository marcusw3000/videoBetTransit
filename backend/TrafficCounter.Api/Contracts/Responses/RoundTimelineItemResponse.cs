namespace TrafficCounter.Api.Contracts.Responses;

public class RoundTimelineItemResponse
{
    public string Kind { get; set; } = string.Empty;
    public DateTime TimestampUtc { get; set; }
    public Guid RoundId { get; set; }
    public string EventType { get; set; } = string.Empty;
    public string RoundStatus { get; set; } = string.Empty;
    public int? CountValue { get; set; }
    public string? Reason { get; set; }
    public string? Source { get; set; }
    public string? CameraId { get; set; }
    public long? TrackId { get; set; }
    public string? ObjectClass { get; set; }
    public string? Direction { get; set; }
    public string? LineId { get; set; }
    public string? SnapshotUrl { get; set; }
    public double? Confidence { get; set; }
    public string? StreamProfileId { get; set; }
    public int? CountBefore { get; set; }
    public int? CountAfter { get; set; }
    public string? EventHash { get; set; }
}
