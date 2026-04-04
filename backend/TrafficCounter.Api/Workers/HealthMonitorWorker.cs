using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Options;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Workers;

public class HealthMonitorWorker : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IMediaMtxClient _mediaMtx;
    private readonly IHttpClientFactory _httpFactory;
    private readonly VisionWorkerOptions _visionOptions;
    private readonly HealthMonitorOptions _healthOptions;
    private readonly ILogger<HealthMonitorWorker> _logger;

    private static readonly TimeSpan TickInterval = TimeSpan.FromSeconds(10);

    // Consecutive vision worker failure counter (in-memory, resets on restart — acceptable for MVP)
    private int _visionWorkerFailureCount = 0;

    public HealthMonitorWorker(
        IServiceScopeFactory scopeFactory,
        IMediaMtxClient mediaMtx,
        IHttpClientFactory httpFactory,
        IOptions<VisionWorkerOptions> visionOptions,
        IOptions<HealthMonitorOptions> healthOptions,
        ILogger<HealthMonitorWorker> logger)
    {
        _scopeFactory = scopeFactory;
        _mediaMtx = mediaMtx;
        _httpFactory = httpFactory;
        _visionOptions = visionOptions.Value;
        _healthOptions = healthOptions.Value;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await PollComponentHealthAsync(stoppingToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                _logger.LogError(ex, "Error in HealthMonitorWorker tick");
            }

            await Task.Delay(TickInterval, stoppingToken);
        }
    }

    private async Task PollComponentHealthAsync(CancellationToken ct)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        var sessionService = scope.ServiceProvider.GetRequiredService<StreamSessionService>();

        await using var ctx = await db.CreateDbContextAsync(ct);

        var runningSessions = await ctx.StreamSessions
            .Where(s => s.Status == SessionStatus.Running)
            .ToListAsync(ct);

        // Check MediaMTX paths for each running session
        foreach (var session in runningSessions)
        {
            if (session.RawStreamPath is not null)
            {
                var exists = await _mediaMtx.PathExistsAsync(session.RawStreamPath, ct);
                if (!exists)
                {
                    _logger.LogWarning(
                        "MediaMTX path '{Path}' missing for session {Id} — degrading",
                        session.RawStreamPath, session.Id);
                    await sessionService.TransitionStatusAsync(session.Id, SessionStatus.Degraded);
                }
            }
        }

        // Check vision worker health
        var visionHealthy = await CheckVisionWorkerHealthAsync(ct);
        if (!visionHealthy)
        {
            _visionWorkerFailureCount++;
            _logger.LogWarning("Vision worker health check failed ({Count}/{Threshold})",
                _visionWorkerFailureCount, _healthOptions.SourceMissingFailureThreshold);

            if (_visionWorkerFailureCount >= _healthOptions.SourceMissingFailureThreshold)
            {
                foreach (var session in runningSessions)
                    await sessionService.TransitionStatusAsync(session.Id, SessionStatus.Degraded);
            }
        }
        else
        {
            _visionWorkerFailureCount = 0;
        }
    }

    private async Task<bool> CheckVisionWorkerHealthAsync(CancellationToken ct)
    {
        try
        {
            var http = _httpFactory.CreateClient();
            var url = _visionOptions.BaseUrl + _visionOptions.HealthPath;
            var response = await http.GetAsync(url, ct);
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Vision worker health check failed");
            return false;
        }
    }
}
