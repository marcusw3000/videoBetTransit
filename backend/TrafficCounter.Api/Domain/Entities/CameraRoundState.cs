namespace TrafficCounter.Api.Domain.Entities;

public class CameraRoundState
{
    public string CameraId { get; set; } = "default";
    public string? ActiveStreamProfileId { get; set; }
    public string? LastSourceFingerprint { get; set; }
    public string? LastSourceUrl { get; set; }
    public string ActivationPhase { get; set; } = "ready";
    public bool ReadyForRounds { get; set; } = true;
    public int RoundsSinceProfileSwitch { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public DateTime? LastProfileChangedAt { get; set; }
    public DateTime? LastSourceChangedAt { get; set; }
}
