namespace TrafficCounter.Api.Domain.Entities;

// Singleton (Id=1) that deliberately survives restarts: normal rounds must never resume by accident.
public sealed class PipelineManagementState
{
    public int Id { get; set; } = 1;
    public bool IsActive { get; set; }
    public string? CameraId { get; set; }
    public string? StreamProfileId { get; set; }
    public string? Reason { get; set; }
    public string? ActivatedBy { get; set; }
    public DateTime? ActivatedAt { get; set; }
    public int Revision { get; set; }
    public string? DraftConfigurationJson { get; set; }
    public bool DraftApplied { get; set; } = true;
    public DateTime UpdatedAt { get; set; }
}
