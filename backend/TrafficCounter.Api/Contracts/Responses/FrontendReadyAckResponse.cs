namespace TrafficCounter.Api.Contracts.Responses;

public class FrontendReadyAckResponse
{
    public bool Accepted { get; set; }
    public bool RoundCreated { get; set; }
    public string CameraId { get; set; } = string.Empty;
    public string ActivationPhase { get; set; } = string.Empty;
    public string ActivationSessionId { get; set; } = string.Empty;
}
