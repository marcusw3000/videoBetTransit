namespace TrafficCounter.Api.Services;

public class SystemRandomSource : IRandomSource
{
    public double NextDouble() => Random.Shared.NextDouble();
}
