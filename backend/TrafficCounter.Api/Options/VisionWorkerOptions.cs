namespace TrafficCounter.Api.Options;

public class VisionWorkerOptions
{
    public string BaseUrl { get; set; } = "http://vision-worker:8000";
    public string HealthPath { get; set; } = "/health";
    public string StartPipelinePath { get; set; } = "/pipeline/start";
    public string StopPipelinePath { get; set; } = "/pipeline/stop";
}
