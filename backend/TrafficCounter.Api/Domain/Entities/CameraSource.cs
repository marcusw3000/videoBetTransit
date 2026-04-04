using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Domain.Entities;

public class CameraSource
{
    public Guid Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public string SourceUrl { get; set; } = string.Empty;
    public SourceProtocol Protocol { get; set; }
    public DateTime CreatedAt { get; set; }

    public List<StreamSession> Sessions { get; set; } = new();
}
