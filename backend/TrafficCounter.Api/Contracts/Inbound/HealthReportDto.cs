namespace TrafficCounter.Api.Contracts.Inbound;

public class HealthReportDto
{
    public string SessionId { get; set; } = string.Empty;
    public double FpsIn { get; set; }
    public double FpsOut { get; set; }
    public double LatencyMs { get; set; }
    public double GpuUsagePercent { get; set; }
    public int ReconnectCount { get; set; }
    public string? Notes { get; set; }
}
