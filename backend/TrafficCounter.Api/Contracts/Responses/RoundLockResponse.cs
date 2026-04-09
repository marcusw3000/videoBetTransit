namespace TrafficCounter.Api.Contracts.Responses;

public class RoundLockResponse
{
    public string CameraId { get; set; } = string.Empty;
    public bool IsLocked { get; set; }
    public string? Reason { get; set; }
}
