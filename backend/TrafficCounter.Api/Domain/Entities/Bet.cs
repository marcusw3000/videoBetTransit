using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Domain.Entities;

public class Bet
{
    public Guid Id { get; set; }
    public string ProviderBetId { get; set; } = string.Empty;
    public string TransactionId { get; set; } = string.Empty;
    public string GameSessionId { get; set; } = string.Empty;
    public Guid RoundId { get; set; }
    public Round Round { get; set; } = null!;
    public string CameraId { get; set; } = string.Empty;
    public RoundMode RoundMode { get; set; } = RoundMode.Normal;
    public Guid MarketId { get; set; }
    public string MarketType { get; set; } = string.Empty;
    public string MarketLabel { get; set; } = string.Empty;
    public decimal Odds { get; set; }
    public int? Threshold { get; set; }
    public int? Min { get; set; }
    public int? Max { get; set; }
    public int? TargetValue { get; set; }
    public decimal StakeAmount { get; set; }
    public decimal PotentialPayout { get; set; }
    public string Currency { get; set; } = string.Empty;
    public BetStatus Status { get; set; } = BetStatus.Accepted;
    public DateTime PlacedAt { get; set; }
    public DateTime AcceptedAt { get; set; }
    public DateTime? SettledAt { get; set; }
    public DateTime? VoidedAt { get; set; }
    public string? RollbackOfTransactionId { get; set; }
    public string? PlayerRef { get; set; }
    public string? OperatorRef { get; set; }
    public string? MetadataJson { get; set; }
}
