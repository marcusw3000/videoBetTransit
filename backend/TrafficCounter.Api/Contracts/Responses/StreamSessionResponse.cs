namespace TrafficCounter.Api.Contracts.Responses;

public class StreamSessionResponse
{
    public Guid Id { get; set; }
    public string Status { get; set; } = string.Empty;
    public string CameraName { get; set; } = string.Empty;
    public string CameraId { get; set; } = string.Empty;
    public string SourceUrl { get; set; } = string.Empty;
    public string SourceProtocol { get; set; } = string.Empty;
    public int TotalCount { get; set; }
    public string? RawStreamPath { get; set; }
    public string? ProcessedStreamPath { get; set; }
    public CountLineResponse CountLine { get; set; } = new();
    public string CountDirection { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; }
    public DateTime? StartedAt { get; set; }
    public DateTime? StoppedAt { get; set; }
    public string? FailureReason { get; set; }
}

public class CountLineResponse
{
    public int X1 { get; set; }
    public int Y1 { get; set; }
    public int X2 { get; set; }
    public int Y2 { get; set; }
}
