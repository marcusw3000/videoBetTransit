namespace TrafficCounter.Api.Domain.Entities;

public class CameraRoundState
{
    public string CameraId { get; set; } = "default";
    public string? ActiveStreamProfileId { get; set; }
    public int RoundsSinceProfileSwitch { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public DateTime? LastProfileChangedAt { get; set; }
}
