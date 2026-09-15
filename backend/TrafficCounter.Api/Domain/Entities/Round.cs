using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Domain.Entities;

public class Round
{
    public Guid RoundId { get; set; }
    public string? OperationalSnapshotJson { get; set; }
    public string? RulesSnapshotJson { get; set; }
    public string? VoidReasonCode { get; set; }
    public Guid Revision { get; set; }
    public string CameraId { get; set; } = "default";
    public RoundMode RoundMode { get; set; } = RoundMode.Normal;
    public RoundStatus Status { get; set; }
    public string DisplayName { get; set; } = "Rodada Normal";

    public DateTime CreatedAt { get; set; }
    public DateTime BetCloseAt { get; set; }   // CreatedAt + betWindowSeconds
    public DateTime EndsAt { get; set; }       // BetCloseAt + roundDurationSeconds
    public DateTime? SettledAt { get; set; }

    public int CurrentCount { get; set; }
    public int? FinalCount { get; set; }

    public DateTime? VoidedAt { get; set; }
    public string? VoidReason { get; set; }

    public ICollection<RoundMarket> Markets { get; set; } = [];
    public ICollection<RoundEvent> Events { get; set; } = [];
    public ICollection<Bet> Bets { get; set; } = [];
}
