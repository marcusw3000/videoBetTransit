using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Options;
using TrafficCounter.Api.Security;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("internal")]
[RequireApiKey]
public class InternalController : ControllerBase
{
    private readonly CrossingEventService _crossingEventService;
    private readonly StreamSessionService _sessionService;
    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly HealthMonitorOptions _healthOptions;

    public InternalController(
        CrossingEventService crossingEventService,
        StreamSessionService sessionService,
        IDbContextFactory<AppDbContext> dbFactory,
        IOptions<HealthMonitorOptions> healthOptions)
    {
        _crossingEventService = crossingEventService;
        _sessionService = sessionService;
        _dbFactory = dbFactory;
        _healthOptions = healthOptions.Value;
    }

    [HttpPost("crossing-events")]
    public async Task<IActionResult> ReceiveCrossingEvent([FromBody] CrossingEventInboundDto dto)
    {
        var accepted = await _crossingEventService.IngestAsync(dto);
        if (!accepted)
            return Conflict(new { error = "Session not found or not in a running state." });

        return Ok(new { received = true });
    }

    [HttpPost("health-report")]
    public async Task<IActionResult> ReceiveHealthReport([FromBody] HealthReportDto dto)
    {
        if (!Guid.TryParse(dto.SessionId, out var sessionId))
            return BadRequest(new { error = "Invalid sessionId." });

        await using var db = await _dbFactory.CreateDbContextAsync();

        var session = await db.StreamSessions.FindAsync(sessionId);
        if (session is null) return NotFound();

        var log = new StreamHealthLog
        {
            Id = Guid.NewGuid(),
            SessionId = sessionId,
            TimestampUtc = DateTime.UtcNow,
            FpsIn = dto.FpsIn,
            FpsOut = dto.FpsOut,
            LatencyMs = dto.LatencyMs,
            GpuUsagePercent = dto.GpuUsagePercent,
            ReconnectCount = dto.ReconnectCount,
            Notes = dto.Notes,
        };

        db.StreamHealthLogs.Add(log);
        await db.SaveChangesAsync();

        // Transition to Degraded if FPS is below threshold
        if (dto.FpsIn < _healthOptions.DegradedFpsThreshold && session.Status == SessionStatus.Running)
        {
            await _sessionService.TransitionStatusAsync(sessionId, SessionStatus.Degraded);
        }
        else if (dto.FpsIn >= _healthOptions.DegradedFpsThreshold && session.Status == SessionStatus.Degraded)
        {
            await _sessionService.TransitionStatusAsync(sessionId, SessionStatus.Running);
        }

        return Ok(new { received = true });
    }
}
