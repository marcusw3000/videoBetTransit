namespace TrafficCounter.Api.Contracts.Inbound;

public class StreamProfileActivatedDto
{
    public string CameraId { get; set; } = string.Empty;
    public string? StreamProfileId { get; set; }
}
