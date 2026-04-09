using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Domain.Entities;

public class Round
{
    public Guid RoundId { get; set; }
    public string CameraId { get; set; } = "default";
    public RoundStatus Status { get; set; }
    public string DisplayName { get; set; } = "Rodada Turbo";

    public DateTime CreatedAt { get; set; }
    public DateTime BetCloseAt { get; set; }   // CreatedAt + 70s
    public DateTime EndsAt { get; set; }       // CreatedAt + 180s
    public DateTime? SettledAt { get; set; }

    public int CurrentCount { get; set; }
    public int? FinalCount { get; set; }

    public DateTime? VoidedAt { get; set; }
    public string? VoidReason { get; set; }

    public ICollection<RoundMarket> Markets { get; set; } = [];
    public ICollection<RoundEvent> Events { get; set; } = [];
}
