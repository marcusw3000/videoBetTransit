using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Domain.Entities;

public class StreamSession
{
    public Guid Id { get; set; }
    public Guid CameraSourceId { get; set; }
    public CameraSource CameraSource { get; set; } = null!;
    public SessionStatus Status { get; set; }

    public int CountLineX1 { get; set; }
    public int CountLineY1 { get; set; }
    public int CountLineX2 { get; set; }
    public int CountLineY2 { get; set; }
    public string CountDirection { get; set; } = "down_to_up";

    public string? RawStreamPath { get; set; }
    public string? ProcessedStreamPath { get; set; }

    public int TotalCount { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? StartedAt { get; set; }
    public DateTime? StoppedAt { get; set; }
    public string? FailureReason { get; set; }

    public List<VehicleCrossingEvent> CrossingEvents { get; set; } = new();
    public List<StreamHealthLog> HealthLogs { get; set; } = new();
    public List<RecordingSegment> RecordingSegments { get; set; } = new();
}
