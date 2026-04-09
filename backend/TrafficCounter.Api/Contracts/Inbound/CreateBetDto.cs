namespace TrafficCounter.Api.Contracts.Inbound;

public class CreateBetDto
{
    public string TransactionId { get; set; } = string.Empty;
    public string GameSessionId { get; set; } = string.Empty;
    public string RoundId { get; set; } = string.Empty;
    public string MarketId { get; set; } = string.Empty;
    public decimal StakeAmount { get; set; }
    public string Currency { get; set; } = string.Empty;
    public string? PlayerRef { get; set; }
    public string? OperatorRef { get; set; }
    public string? MetadataJson { get; set; }
}
