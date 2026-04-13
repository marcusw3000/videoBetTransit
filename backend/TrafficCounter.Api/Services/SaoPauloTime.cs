namespace TrafficCounter.Api.Services;

internal static class SaoPauloTime
{
    private static readonly TimeZoneInfo TimeZone = ResolveTimeZone();

    public static DateTimeOffset FromUtc(DateTime value)
    {
        var utcValue = value.Kind switch
        {
            DateTimeKind.Utc => value,
            DateTimeKind.Local => value.ToUniversalTime(),
            _ => DateTime.SpecifyKind(value, DateTimeKind.Utc),
        };

        return TimeZoneInfo.ConvertTime(new DateTimeOffset(utcValue), TimeZone);
    }

    public static DateTimeOffset? FromUtc(DateTime? value)
    {
        return value.HasValue ? FromUtc(value.Value) : null;
    }

    private static TimeZoneInfo ResolveTimeZone()
    {
        foreach (var id in new[] { "America/Sao_Paulo", "E. South America Standard Time" })
        {
            try
            {
                return TimeZoneInfo.FindSystemTimeZoneById(id);
            }
            catch (TimeZoneNotFoundException)
            {
            }
            catch (InvalidTimeZoneException)
            {
            }
        }

        return TimeZoneInfo.Utc;
    }
}
