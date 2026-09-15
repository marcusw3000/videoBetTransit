using System.Security.Claims;
using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Security;

// Records request outcomes, including authorization/CSRF denials. No bodies, query strings or credentials.
public sealed class AdministrativeAuditMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext context, IDbContextFactory<AppDbContext> factory)
    {
        var path = context.Request.Path.Value ?? "";
        var relevant = context.Request.Method == "POST" &&
            (path.StartsWith("/admin/", StringComparison.OrdinalIgnoreCase) ||
             path.StartsWith("/streams", StringComparison.OrdinalIgnoreCase) ||
             path.StartsWith("/internal/camera-config", StringComparison.OrdinalIgnoreCase) ||
             path.Equals("/internal/rounds/profile-activated", StringComparison.OrdinalIgnoreCase) ||
             (path.StartsWith("/internal/rounds/", StringComparison.OrdinalIgnoreCase) &&
              path.EndsWith("/void", StringComparison.OrdinalIgnoreCase)));
        if (!relevant) { await next(context); return; }
        var failed = false;
        try { await next(context); }
        catch { failed = true; throw; }
        finally
        {
            await using var db = await factory.CreateDbContextAsync();
            db.AdministrativeAudits.Add(new AdministrativeAudit {
                Actor = context.User.FindFirstValue(ClaimTypes.NameIdentifier)
                    ?? (context.Items.ContainsKey("AuthenticatedWorker") ? "worker" : "anonymous"),
                Action = "request:" + context.Request.Method + ":" + path,
                Target = (context.Items["AuditTarget"] as string ?? path) is var target && target.Length > 256 ? target[..256] : target,
                Outcome = failed ? "failed" : context.Response.StatusCode < 400 ? "completed" : "blocked",
                ReasonCode = failed ? "exception" : "http_" + context.Response.StatusCode
            });
            await db.SaveChangesAsync();
        }
    }
}
