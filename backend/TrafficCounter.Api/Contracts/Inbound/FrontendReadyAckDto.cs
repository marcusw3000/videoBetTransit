namespace TrafficCounter.Api.Contracts.Inbound;

public class FrontendReadyAckDto
{
    public string CameraId { get; set; } = string.Empty;
    public string? StreamProfileId { get; set; }
    public string GameSessionId { get; set; } = string.Empty;
    public string ActivationNonce { get; set; } = string.Empty;
    public string ActivationSessionId { get; set; } = string.Empty;
}
