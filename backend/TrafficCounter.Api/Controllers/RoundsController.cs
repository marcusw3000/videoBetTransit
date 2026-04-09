using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("rounds")]
public class RoundsController : ControllerBase
{
    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly RoundService _roundService;

    public RoundsController(IDbContextFactory<AppDbContext> dbFactory, RoundService roundService)
    {
        _dbFactory = dbFactory;
        _roundService = roundService;
    }

    [HttpGet("current")]
    public async Task<IActionResult> GetCurrent([FromQuery] string? cameraId = null)
    {
        var effectiveCameraId = string.IsNullOrWhiteSpace(cameraId) ? "default" : cameraId.Trim();
        var round = await _roundService.GetCurrentRoundAsync(effectiveCameraId);

        if (round is null)
            return NotFound(new { error = $"Nenhum round disponivel ainda para camera '{effectiveCameraId}'." });

        return Ok(ToResponse(round));
    }

    [HttpGet("history")]
    public async Task<IActionResult> GetHistory([FromQuery] int limit = 20, [FromQuery] string? cameraId = null)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var effectiveCameraId = string.IsNullOrWhiteSpace(cameraId) ? null : cameraId.Trim();

        var query = db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.Status == RoundStatus.Settled || r.Status == RoundStatus.Void)
            .AsQueryable();

        if (!string.IsNullOrWhiteSpace(effectiveCameraId))
            query = query.Where(r => r.CameraId == effectiveCameraId);

        var rounds = await query
            .OrderByDescending(r => r.SettledAt ?? r.VoidedAt)
            .Take(Math.Clamp(limit, 1, 100))
            .ToListAsync();

        return Ok(rounds.Select(ToResponse));
    }

    [HttpGet("{roundId:guid}/count-events")]
    public async Task<IActionResult> GetCountEvents(Guid roundId)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var events = await db.VehicleCrossingEvents
            .Where(e => e.RoundId == roundId)
            .OrderByDescending(e => e.TimestampUtc)
            .Take(500)
            .Select(e => new CrossingEventResponse
            {
                Id = e.Id,
                RoundId = e.RoundId,
                SessionId = e.SessionId ?? Guid.Empty,
                CameraId = e.CameraId,
                TimestampUtc = e.TimestampUtc,
                TrackId = e.TrackId,
                ObjectClass = e.ObjectClass,
                Direction = e.Direction,
                LineId = e.LineId,
                FrameNumber = e.FrameNumber,
                Confidence = e.Confidence,
                SnapshotUrl = e.SnapshotUrl,
                Source = e.Source,
                StreamProfileId = e.StreamProfileId,
                CountBefore = e.CountBefore,
                CountAfter = e.CountAfter,
                PreviousEventHash = e.PreviousEventHash,
                EventHash = e.EventHash,
            })
            .ToListAsync();

        return Ok(events);
    }

    [HttpGet("{roundId:guid}/timeline")]
    public async Task<IActionResult> GetTimeline(Guid roundId)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var roundEvents = await db.RoundEvents
            .Where(e => e.RoundId == roundId)
            .Select(e => new RoundTimelineItemResponse
            {
                Kind = "round_event",
                TimestampUtc = e.TimestampUtc,
                RoundId = e.RoundId,
                EventType = e.EventType,
                RoundStatus = e.RoundStatus,
                CountValue = e.CountValue,
                Reason = e.Reason,
                Source = e.Source,
            })
            .ToListAsync();

        var crossingEvents = await db.VehicleCrossingEvents
            .Where(e => e.RoundId == roundId)
            .Select(e => new RoundTimelineItemResponse
            {
                Kind = "crossing_event",
                TimestampUtc = e.TimestampUtc,
                RoundId = e.RoundId ?? roundId,
                EventType = "counted_vehicle",
                RoundStatus = string.Empty,
                CameraId = e.CameraId,
                TrackId = e.TrackId,
                ObjectClass = e.ObjectClass,
                Direction = e.Direction,
                LineId = e.LineId,
                SnapshotUrl = e.SnapshotUrl,
                Confidence = e.Confidence,
                Source = e.Source,
                EventHash = e.EventHash,
            })
            .ToListAsync();

        var timeline = roundEvents
            .Concat(crossingEvents)
            .OrderBy(item => item.TimestampUtc)
            .ThenBy(item => item.Kind)
            .ToList();

        return Ok(timeline);
    }

    private static RoundResponse ToResponse(Domain.Entities.Round r) => new()
    {
        RoundId = r.RoundId.ToString(),
        CameraId = r.CameraId,
        CameraIds = string.IsNullOrWhiteSpace(r.CameraId) ? [] : [r.CameraId],
        DisplayName = r.DisplayName,
        Status = r.Status.ToString().ToLowerInvariant(),
        IsSuspended = r.Status != RoundStatus.Open,
        CreatedAt = r.CreatedAt,
        BetCloseAt = r.BetCloseAt,
        EndsAt = r.EndsAt,
        SettledAt = r.SettledAt,
        VoidedAt = r.VoidedAt,
        VoidReason = r.VoidReason,
        CurrentCount = r.CurrentCount,
        FinalCount = r.FinalCount,
        Markets = r.Markets
            .OrderBy(m => m.SortOrder)
            .Select(ToMarketResponse)
            .ToList(),
    };

    private static RoundMarketResponse ToMarketResponse(Domain.Entities.RoundMarket m) => new()
    {
        MarketId = m.MarketId.ToString(),
        MarketType = m.MarketType,
        Label = m.Label,
        Odds = m.Odds,
        TargetValue = m.MarketType is "under" or "over" ? m.Threshold : m.TargetValue,
        Min = m.Min,
        Max = m.Max,
        IsWinner = m.IsWinner,
    };
}
