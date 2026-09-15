namespace TrafficCounter.Api.Services;

public sealed class RequestRejectedException(string message, int statusCode = 409) : Exception(message)
{
    public int StatusCode { get; } = statusCode;
}
