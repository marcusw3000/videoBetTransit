namespace TrafficCounter.Api.Models;

public class Round
{
    public string Id { get; set; } = string.Empty;
    public string Status { get; set; } = "running";
    public int CurrentCount { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime EndsAt { get; set; }
    public int? FinalCount { get; set; }
    public List<RoundRange> Ranges { get; set; } = new();
}

public class RoundRange
{
    public string Id { get; set; } = string.Empty;
    public string RoundId { get; set; } = string.Empty;
    public string Label { get; set; } = string.Empty;
    public int Min { get; set; }
    public int Max { get; set; }
    public double Odds { get; set; }
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
