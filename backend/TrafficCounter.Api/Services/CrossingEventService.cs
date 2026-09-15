using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Options;

namespace TrafficCounter.Api.Services;

public class CrossingEventService
{
    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly IHubContext<MetricsHub> _hub;
    private readonly SecurityOptions _security;
    private readonly ILogger<CrossingEventService> _logger;
    private readonly RoundService _roundService;

    public CrossingEventService(
        IDbContextFactory<AppDbContext> dbFactory,
        IHubContext<MetricsHub> hub,
        IOptions<SecurityOptions> security,
        ILogger<CrossingEventService> logger,
        RoundService roundService)
    {
        _dbFactory = dbFactory;
        _hub = hub;
        _security = security.Value;
        _logger = logger;
        _roundService = roundService;
    }

    public async Task<bool> IngestAsync(CrossingEventInboundDto dto)
    {
        if (!Guid.TryParse(dto.SessionId, out var sessionId))
            return false;

        await using var db = await _dbFactory.CreateDbContextAsync();

        var session = await db.StreamSessions
            .Include(s => s.CameraSource)
            .FirstOrDefaultAsync(s => s.Id == sessionId);
        if (session is null || session.Status is not SessionStatus.Running and not SessionStatus.Degraded)
            return false;

        var cameraId = StreamPathNaming.ExtractCameraId(session);

        if (string.IsNullOrWhiteSpace(dto.EventHash)) return false;
        if (await db.EventReceipts.AnyAsync(e => e.Id == dto.EventHash)) return true;
        var previousEvent = await db.VehicleCrossingEvents.Where(e => e.SessionId == sessionId)
            .OrderByDescending(e => e.TimestampUtc).FirstOrDefaultAsync();
        var expectedHash = ComputeHash(dto, previousEvent?.EventHash);
        if (_security.EnforceHashChain && !string.Equals(expectedHash, dto.EventHash, StringComparison.OrdinalIgnoreCase))
            return false;
        await _roundService.RecordCountEventAsync(new RoundCountEventDto
        {
            ConfigurationVersion = dto.ConfigurationVersion,
            CameraId = cameraId, TrackId = dto.TrackId.ToString(), CrossedAt = dto.TimestampUtc,
            VehicleType = dto.ObjectClass, Direction = dto.Direction, LineId = dto.LineId,
            FrameNumber = dto.FrameNumber, Confidence = dto.Confidence, EventHash = dto.EventHash,
            PreviousEventHash = dto.PreviousEventHash, CountMethod = dto.CountMethod,
            FallbackBandPx = dto.FallbackBandPx, Source = "vision_worker_crossing_event",
        }, sessionId);
        await db.Entry(session).ReloadAsync();

        var oneMinuteAgo = DateTime.UtcNow.AddMinutes(-1);
        var lastMinuteCount = await db.VehicleCrossingEvents
            .CountAsync(e => e.SessionId == sessionId && e.TimestampUtc >= oneMinuteAgo);

        var metrics = new SessionMetricsResponse
        {
            SessionId = sessionId,
            TotalCount = session.TotalCount,
            LastMinuteCount = lastMinuteCount,
            Status = session.Status.ToString(),
        };

        await _hub.Clients.Group($"session:{sessionId}")
            .SendAsync("metrics_updated", metrics);

        return true;
    }

    /// <summary>
    /// Computes SHA-256 hash over the canonical event fields.
    /// </summary>
    public static string ComputeHash(CrossingEventInboundDto dto, string? previousHash)
    {
        var input = string.Join("|",
            dto.SessionId,
            dto.TimestampUtc.ToString("O"),
            dto.TrackId,
            dto.ObjectClass,
            dto.Direction,
            dto.LineId,
            dto.FrameNumber,
            dto.Confidence.ToString("F4"),
            previousHash ?? "GENESIS");

        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
