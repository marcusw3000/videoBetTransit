namespace TrafficCounter.Api.Domain.Entities;

public class StreamHealthLog
{
    public Guid Id { get; set; }
    public Guid SessionId { get; set; }
    public StreamSession Session { get; set; } = null!;
    public DateTime TimestampUtc { get; set; }
    public double FpsIn { get; set; }
    public double FpsOut { get; set; }
    public double LatencyMs { get; set; }
    public double GpuUsagePercent { get; set; }
    public int ReconnectCount { get; set; }
    public string? Notes { get; set; }
}
