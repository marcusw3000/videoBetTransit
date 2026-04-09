namespace TrafficCounter.Api.Contracts.Responses;

public class BetResponse
{
    public string Id { get; set; } = string.Empty;
    public string ProviderBetId { get; set; } = string.Empty;
    public string TransactionId { get; set; } = string.Empty;
    public string GameSessionId { get; set; } = string.Empty;
    public string RoundId { get; set; } = string.Empty;
    public string CameraId { get; set; } = string.Empty;
    public string RoundMode { get; set; } = string.Empty;
    public string MarketId { get; set; } = string.Empty;
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
    public string Status { get; set; } = string.Empty;
    public DateTime PlacedAt { get; set; }
    public DateTime AcceptedAt { get; set; }
    public DateTime? SettledAt { get; set; }
    public DateTime? VoidedAt { get; set; }
    public string? RollbackOfTransactionId { get; set; }
    public string? PlayerRef { get; set; }
    public string? OperatorRef { get; set; }
    public string? MetadataJson { get; set; }
}
