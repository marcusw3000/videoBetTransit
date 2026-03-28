namespace TrafficCounter.Api.Models;

public class Round
{
    public string Id { get; set; } = string.Empty;
    public string DisplayName { get; set; } = "Rodada Turbo";
    public string Status { get; set; } = "open";
    public int CurrentCount { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime BetCloseAt { get; set; }
    public DateTime EndsAt { get; set; }
    public DateTime? SettledAt { get; set; }
    public DateTime? VoidedAt { get; set; }
    public string? VoidReason { get; set; }
    public int? FinalCount { get; set; }
    public List<RoundRange> Ranges { get; set; } = new();
}

public class RoundRange
{
    public string Id { get; set; } = string.Empty;
    public string RoundId { get; set; } = string.Empty;
    public string MarketType { get; set; } = "range";
    public string Label { get; set; } = string.Empty;
    public int Min { get; set; }
    public int Max { get; set; }
    public int? TargetValue { get; set; }
    public double Odds { get; set; }
    public bool? IsWinner { get; set; }
}

public class CountEvent
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string CameraId { get; set; } = string.Empty;
    public string RoundId { get; set; } = string.Empty;
    public string TrackId { get; set; } = string.Empty;
    public string VehicleType { get; set; } = string.Empty;
    public string CrossedAt { get; set; } = string.Empty;
    public string SnapshotUrl { get; set; } = string.Empty;
    public int TotalCount { get; set; }
}
