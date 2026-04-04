namespace TrafficCounter.Api.Contracts.Inbound;

public class CrossingEventInboundDto
{
    public string SessionId { get; set; } = string.Empty;
    public DateTime TimestampUtc { get; set; }
    public long TrackId { get; set; }
    public string ObjectClass { get; set; } = string.Empty;
    public string Direction { get; set; } = string.Empty;
    public string LineId { get; set; } = string.Empty;
    public double Confidence { get; set; }
    public long FrameNumber { get; set; }
    public string? PreviousEventHash { get; set; }
    public string EventHash { get; set; } = string.Empty;
}
