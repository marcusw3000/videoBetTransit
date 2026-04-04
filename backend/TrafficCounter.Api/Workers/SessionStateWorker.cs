using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Hubs;

namespace TrafficCounter.Api.Workers;

public class SessionStateWorker : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IHubContext<MetricsHub> _hub;
    private readonly ILogger<SessionStateWorker> _logger;

    private static readonly TimeSpan TickInterval = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan StartingTimeout = TimeSpan.FromSeconds(60);
    private static readonly TimeSpan ValidatingTimeout = TimeSpan.FromSeconds(30);

    public SessionStateWorker(
        IServiceScopeFactory scopeFactory,
        IHubContext<MetricsHub> hub,
        ILogger<SessionStateWorker> logger)
    {
        _scopeFactory = scopeFactory;
        _hub = hub;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await CheckStuckSessionsAsync(stoppingToken);
                await PublishHeartbeatsAsync(stoppingToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                _logger.LogError(ex, "Error in SessionStateWorker tick");
            }

            await Task.Delay(TickInterval, stoppingToken);
        }
    }

    private async Task CheckStuckSessionsAsync(CancellationToken ct)
    {
        using var scope = _scopeFactory.CreateScope();
        var sessionService = scope.ServiceProvider.GetRequiredService<Services.StreamSessionService>();
        var db = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await using var ctx = await db.CreateDbContextAsync(ct);
        var now = DateTime.UtcNow;

        // Sessions stuck in Starting
        var stuckStarting = await ctx.StreamSessions
            .Where(s => s.Status == SessionStatus.Starting
                     && s.CreatedAt < now - StartingTimeout)
            .ToListAsync(ct);

        foreach (var s in stuckStarting)
        {
            _logger.LogWarning("Session {Id} stuck in Starting — transitioning to Failed", s.Id);
            await sessionService.TransitionStatusAsync(s.Id, SessionStatus.Failed, "Pipeline start timeout.");
        }

        // Sessions stuck in ValidatingSource
        var stuckValidating = await ctx.StreamSessions
            .Where(s => s.Status == SessionStatus.ValidatingSource
                     && s.CreatedAt < now - ValidatingTimeout)
            .ToListAsync(ct);

        foreach (var s in stuckValidating)
        {
            _logger.LogWarning("Session {Id} stuck in ValidatingSource — transitioning to Failed", s.Id);
            await sessionService.TransitionStatusAsync(s.Id, SessionStatus.Failed, "Source validation timeout.");
        }
    }

    private async Task PublishHeartbeatsAsync(CancellationToken ct)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await using var ctx = await db.CreateDbContextAsync(ct);
        var now = DateTime.UtcNow;
        var oneMinuteAgo = now.AddMinutes(-1);

        var activeSessions = await ctx.StreamSessions
            .Where(s => s.Status == SessionStatus.Running
                     || s.Status == SessionStatus.Degraded)
            .ToListAsync(ct);

        foreach (var session in activeSessions)
        {
            var lastMinuteCount = await ctx.VehicleCrossingEvents
                .CountAsync(e => e.SessionId == session.Id && e.TimestampUtc >= oneMinuteAgo, ct);

            var metrics = new SessionMetricsResponse
            {
                SessionId = session.Id,
                TotalCount = session.TotalCount,
                LastMinuteCount = lastMinuteCount,
                Status = session.Status.ToString(),
            };

            await _hub.Clients.Group($"session:{session.Id}")
                .SendAsync("metrics_updated", metrics, ct);
        }
    }
}
