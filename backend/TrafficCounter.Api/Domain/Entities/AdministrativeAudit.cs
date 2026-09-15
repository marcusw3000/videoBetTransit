namespace TrafficCounter.Api.Domain.Entities;

public sealed class AdministrativeAudit
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public DateTime TimestampUtc { get; set; } = DateTime.UtcNow;
    public string Actor { get; set; } = "system";
    public string Action { get; set; } = "";
    public string Target { get; set; } = "";
    public string Outcome { get; set; } = "";
    public string? ReasonCode { get; set; }
    public string? Reason { get; set; }
}
