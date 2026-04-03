namespace TrafficCounter.Api.Domain.Entities;

public class RecordingSegment
{
    public Guid Id { get; set; }
    public Guid SessionId { get; set; }
    public StreamSession Session { get; set; } = null!;
    public string SegmentType { get; set; } = string.Empty; // "raw" | "processed"
    public string FilePath { get; set; } = string.Empty;
    public DateTime StartedAt { get; set; }
    public DateTime? EndedAt { get; set; }
    public long? FileSizeBytes { get; set; }
}
