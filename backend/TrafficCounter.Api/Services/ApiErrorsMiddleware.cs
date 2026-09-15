using Microsoft.EntityFrameworkCore;
using Microsoft.Data.Sqlite;
using Npgsql;

namespace TrafficCounter.Api.Services;

public sealed class ApiErrorsMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext context)
    {
        try { await next(context); }
        catch (RequestRejectedException ex)
        {
            context.Response.StatusCode = ex.StatusCode;
            await context.Response.WriteAsJsonAsync(new { error = ex.Message });
        }
        catch (Exception ex) when (IsRetryable(ex))
        {
            context.Response.StatusCode = 503;
            context.Response.Headers.RetryAfter = "1";
            await context.Response.WriteAsJsonAsync(new { error = "Conflito temporario. Repita a mesma solicitacao com o mesmo identificador." });
        }
    }

    private static bool IsRetryable(Exception ex) => ex is DbUpdateConcurrencyException
        || ex is SqliteException { SqliteErrorCode: 5 or 6 }
        || ex is SqliteException { SqliteExtendedErrorCode: 1555 or 2067 }
        || ex is PostgresException { SqlState: "40001" or "40P01" or "23505" }
        || ex.InnerException is not null && IsRetryable(ex.InnerException);
}
