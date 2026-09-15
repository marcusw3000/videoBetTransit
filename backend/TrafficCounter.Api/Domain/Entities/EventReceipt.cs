namespace TrafficCounter.Api.Domain.Entities;

// A separate unique receipt also covers databases containing legacy duplicate hashes.
public sealed class EventReceipt
{
    public string Id { get; set; } = "";
    public Guid RoundId { get; set; }
}
