namespace TrafficCounter.Api.Domain.Entities;

public class CameraRoundState
{
    public string CameraId { get; set; } = "default";
    public string? ActiveStreamProfileId { get; set; }
    public string? LastSourceFingerprint { get; set; }
    public string? LastSourceUrl { get; set; }
    public string ActivationPhase { get; set; } = "ready";
    public bool ReadyForRounds { get; set; } = true;
    public string? ExpectedFrontendAckNonce { get; set; }
    public string? ActivationSessionId { get; set; }
    public string? LastReadyActivationSessionId { get; set; }
    public bool FrontendAckReceived { get; set; }
    public DateTime? FrontendAckedAt { get; set; }
    public string? LastFrontendAckSessionId { get; set; }
    public DateTime? ActivationRequestedAt { get; set; }
    public int RoundsSinceProfileSwitch { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public DateTime? LastProfileChangedAt { get; set; }
    public DateTime? LastSourceChangedAt { get; set; }
}
