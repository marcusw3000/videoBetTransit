namespace TrafficCounter.Api.Contracts.Inbound;

public class CameraConfigChangeDto
{
    public string CameraId { get; set; } = string.Empty;
    public bool AllowSettling { get; set; } = false;
}
