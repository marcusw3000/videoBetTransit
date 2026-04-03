namespace TrafficCounter.Api.Contracts.Responses;

public class SessionMetricsResponse
{
    public Guid SessionId { get; set; }
    public int TotalCount { get; set; }
    public int LastMinuteCount { get; set; }
    public string Status { get; set; } = string.Empty;
}
