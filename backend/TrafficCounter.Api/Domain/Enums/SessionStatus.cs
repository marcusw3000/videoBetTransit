namespace TrafficCounter.Api.Domain.Enums;

public enum SessionStatus
{
    Created,
    ValidatingSource,
    Ready,
    Starting,
    Running,
    Degraded,
    Stopped,
    Failed
}
