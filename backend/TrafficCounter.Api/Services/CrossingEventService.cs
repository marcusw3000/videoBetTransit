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

        // Find previous event for hash chaining
        var previousEvent = await db.VehicleCrossingEvents
            .Where(e => e.SessionId == sessionId)
            .OrderByDescending(e => e.TimestampUtc)
            .FirstOrDefaultAsync();

        var previousHash = previousEvent?.EventHash;
        var expectedHash = ComputeHash(dto, previousHash);

        if (!string.Equals(expectedHash, dto.EventHash, StringComparison.OrdinalIgnoreCase))
        {
            _logger.LogWarning(
                "Hash mismatch for session {SessionId} trackId {TrackId}: expected {Expected}, got {Got}",
                sessionId, dto.TrackId, expectedHash, dto.EventHash);

            if (_security.EnforceHashChain)
                return false;
        }

        var round = await _roundService.IncrementCountAsync(cameraId);

        var @event = new VehicleCrossingEvent
        {
            Id = Guid.NewGuid(),
            RoundId = round?.RoundId,
            SessionId = sessionId,
            CameraId = cameraId,
            TimestampUtc = dto.TimestampUtc,
            TrackId = dto.TrackId,
            ObjectClass = dto.ObjectClass,
            Direction = dto.Direction,
            LineId = dto.LineId,
            FrameNumber = dto.FrameNumber,
            Confidence = dto.Confidence,
            SnapshotUrl = null,
            Source = "vision_worker_crossing_event",
            PreviousEventHash = previousHash,
            EventHash = expectedHash, // store the server-computed hash
        };

        db.VehicleCrossingEvents.Add(@event);
        session.TotalCount++;
        await db.SaveChangesAsync();

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
