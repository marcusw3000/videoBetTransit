namespace TrafficCounter.Api.Contracts.Responses;

public class CrossingEventResponse
{
    public Guid Id { get; set; }
    public Guid SessionId { get; set; }
    public DateTime TimestampUtc { get; set; }
    public long TrackId { get; set; }
    public string ObjectClass { get; set; } = string.Empty;
    public string Direction { get; set; } = string.Empty;
    public string LineId { get; set; } = string.Empty;
    public long FrameNumber { get; set; }
    public double Confidence { get; set; }
    public string EventHash { get; set; } = string.Empty;
}
