namespace TrafficCounter.Api.Options;

public class HealthMonitorOptions
{
    public int SourceMissingFailureThreshold { get; set; } = 3;
    public double DegradedFpsThreshold { get; set; } = 5.0;
}
