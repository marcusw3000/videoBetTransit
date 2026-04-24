namespace TrafficCounter.Api.Contracts.Inbound;

public class StreamProfileActivatedDto
{
    public string CameraId { get; set; } = string.Empty;
    public string? StreamProfileId { get; set; }
    public bool AllowSettling { get; set; } = false;
    public bool AutoSwitchRound { get; set; } = false;
    public string Phase { get; set; } = "requested";
}
