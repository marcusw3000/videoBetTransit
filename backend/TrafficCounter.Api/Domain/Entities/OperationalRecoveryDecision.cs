namespace TrafficCounter.Api.Domain.Entities;

// Append-only operational record. It references the worker event identifier but
// deliberately does not copy its payload or mutate the worker outbox.
public sealed class OperationalRecoveryDecision
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public DateTime TimestampUtc { get; set; } = DateTime.UtcNow;
    public string EventId { get; set; } = "";
    public string Decision { get; set; } = "";
    public string Actor { get; set; } = "system";
    public string ReasonCode { get; set; } = "";
    public string? Reason { get; set; }
}
