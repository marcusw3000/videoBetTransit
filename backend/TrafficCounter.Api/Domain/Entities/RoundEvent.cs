namespace TrafficCounter.Api.Domain.Entities;

public class RoundEvent
{
    public Guid Id { get; set; }
    public Guid RoundId { get; set; }
    public Round Round { get; set; } = null!;

    public string EventType { get; set; } = string.Empty;
    public string RoundStatus { get; set; } = string.Empty;
    public DateTime TimestampUtc { get; set; }
    public int? CountValue { get; set; }
    public string? Reason { get; set; }
    public string? Source { get; set; }
}
