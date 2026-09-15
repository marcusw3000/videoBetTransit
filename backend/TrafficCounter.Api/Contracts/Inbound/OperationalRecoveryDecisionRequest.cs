namespace TrafficCounter.Api.Contracts.Inbound;

public sealed class OperationalRecoveryDecisionRequest
{
    public string Decision { get; set; } = "";
    public string ReasonCode { get; set; } = "";
    public string? Reason { get; set; }
}
