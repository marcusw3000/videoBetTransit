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

public class RoundService
{
    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly IHubContext<RoundHub> _hub;
    private readonly ILogger<RoundService> _logger;
    private readonly RoundOptions _options;

    public RoundService(
        IDbContextFactory<AppDbContext> dbFactory,
        IHubContext<RoundHub> hub,
        ILogger<RoundService> logger,
        IOptions<RoundOptions> options)
    {
        _dbFactory = dbFactory;
        _hub = hub;
        _logger = logger;
        _options = options.Value;
    }

    public async Task<bool> EnsureActiveRoundAsync(string cameraId = "default")
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var active = await db.Rounds.AnyAsync(r =>
            r.CameraId == cameraId &&
            r.Status != RoundStatus.Settled &&
            r.Status != RoundStatus.Void);
        if (active) return false;

        await CreateNewRoundAsync(db, cameraId);
        return true;
    }

    public async Task<bool> TickAsync()
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var now = DateTime.UtcNow;

        var rounds = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
            .OrderBy(r => r.CameraId)
            .ThenByDescending(r => r.CreatedAt)
            .ToListAsync();

        if (rounds.Count == 0) return false;

        var changed = false;
        var settledRounds = new List<Round>();

        foreach (var round in rounds)
        {
            if (round.Status == RoundStatus.Open && now >= round.BetCloseAt)
            {
                round.Status = RoundStatus.Closing;
                db.RoundEvents.Add(CreateRoundEvent(round, "bet_closed", now, source: "round_manager"));
                changed = true;
                _logger.LogInformation("[Round {Id}] Apostas fechadas.", round.RoundId);
            }

            if (round.Status == RoundStatus.Closing && now >= round.EndsAt)
            {
                round.Status = RoundStatus.Settled;
                round.FinalCount = round.CurrentCount;
                round.SettledAt = now;
                db.RoundEvents.Add(CreateRoundEvent(round, "settled", now, round.FinalCount, source: "round_manager"));
                changed = true;

                foreach (var market in round.Markets)
                    market.IsWinner = EvaluateMarket(market, round.FinalCount.Value);

                settledRounds.Add(round);
                _logger.LogInformation("[Round {Id}] Encerrado. Total: {Count}", round.RoundId, round.FinalCount);
            }
        }

        if (changed)
            await db.SaveChangesAsync();

        foreach (var round in settledRounds)
        {
            await BroadcastAsync("round_settled", round);
            await using var db2 = await _dbFactory.CreateDbContextAsync();
            await CreateNewRoundAsync(db2, round.CameraId);
        }

        return changed;
    }

    public async Task<Round?> IncrementCountAsync(string cameraId = "default")
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var round = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
            .Where(r => r.CameraId == cameraId)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        if (round is null)
        {
            await CreateNewRoundAsync(db, cameraId);
            round = await db.Rounds
                .Include(r => r.Markets)
                .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
                .Where(r => r.CameraId == cameraId)
                .OrderByDescending(r => r.CreatedAt)
                .FirstAsync();
        }

        round.CurrentCount++;
        await db.SaveChangesAsync();

        await BroadcastAsync("count_updated", round);
        return round;
    }

    public async Task<Round?> RecordCountEventAsync(RoundCountEventDto dto)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var cameraId = string.IsNullOrWhiteSpace(dto.CameraId) ? "default" : dto.CameraId.Trim();
        Round? round = null;

        if (Guid.TryParse(dto.RoundId, out var explicitRoundId))
        {
            round = await db.Rounds
                .Include(r => r.Markets)
                .Where(r => r.RoundId == explicitRoundId)
                .Where(r => r.CameraId == cameraId)
                .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
                .FirstOrDefaultAsync();
        }

        round ??= await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
            .Where(r => r.CameraId == cameraId)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        if (round is null)
        {
            await CreateNewRoundAsync(db, cameraId);
            round = await db.Rounds
                .Include(r => r.Markets)
                .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
                .Where(r => r.CameraId == cameraId)
                .OrderByDescending(r => r.CreatedAt)
                .FirstAsync();
        }

        round.CurrentCount++;

        db.VehicleCrossingEvents.Add(new VehicleCrossingEvent
        {
            Id = Guid.NewGuid(),
            RoundId = round.RoundId,
            SessionId = null,
            CameraId = cameraId,
            TimestampUtc = dto.CrossedAt == default ? DateTime.UtcNow : dto.CrossedAt,
            TrackId = long.TryParse(dto.TrackId, out var trackId) ? trackId : 0,
            ObjectClass = string.IsNullOrWhiteSpace(dto.VehicleType) ? "unknown" : dto.VehicleType.Trim(),
            Direction = "unknown",
            LineId = "round_count_event",
            FrameNumber = 0,
            Confidence = 1.0,
            SnapshotUrl = string.IsNullOrWhiteSpace(dto.SnapshotUrl) ? null : dto.SnapshotUrl.Trim(),
            Source = "vision_worker_round_count",
            PreviousEventHash = null,
            EventHash = BuildSyntheticCountEventHash(dto, round.RoundId),
        });

        await db.SaveChangesAsync();
        await BroadcastAsync("count_updated", round);
        return round;
    }

    public async Task<Round?> GetCurrentRoundAsync(string cameraId = "default")
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var normalizedCameraId = string.IsNullOrWhiteSpace(cameraId) ? "default" : cameraId.Trim();

        var round = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.CameraId == normalizedCameraId)
            .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        round ??= await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.CameraId == normalizedCameraId)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        if (round is null)
        {
            await CreateNewRoundAsync(db, normalizedCameraId);
            round = await db.Rounds
                .Include(r => r.Markets)
                .Where(r => r.CameraId == normalizedCameraId)
                .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
                .OrderByDescending(r => r.CreatedAt)
                .FirstOrDefaultAsync();
        }

        return round;
    }

    public async Task<bool> VoidRoundAsync(Guid roundId, string reason)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var round = await db.Rounds
            .Include(r => r.Markets)
            .FirstOrDefaultAsync(r => r.RoundId == roundId);

        if (round is null) return false;
        if (round.Status == RoundStatus.Settled || round.Status == RoundStatus.Void) return false;

        round.Status = RoundStatus.Void;
        round.VoidedAt = DateTime.UtcNow;
        round.VoidReason = reason;
        db.RoundEvents.Add(CreateRoundEvent(round, "voided", round.VoidedAt.Value, round.CurrentCount, reason, "internal_api"));

        await db.SaveChangesAsync();
        _logger.LogInformation("[Round {Id}] Anulado. Motivo: {Reason}", round.RoundId, reason);

        await BroadcastAsync("round_voided", round);

        await using var db2 = await _dbFactory.CreateDbContextAsync();
        await CreateNewRoundAsync(db2, round.CameraId);

        return true;
    }

    private async Task CreateNewRoundAsync(AppDbContext db, string cameraId)
    {
        var now = DateTime.UtcNow;
        var round = new Round
        {
            RoundId = Guid.NewGuid(),
            CameraId = string.IsNullOrWhiteSpace(cameraId) ? "default" : cameraId.Trim(),
            Status = RoundStatus.Open,
            DisplayName = "Rodada Turbo",
            CreatedAt = now,
            BetCloseAt = now.AddSeconds(_options.BetWindowSeconds),
            EndsAt = now.AddSeconds(_options.DurationSeconds),
            CurrentCount = 0,
        };

        var markets = _options.Markets.Select((t, i) => new RoundMarket
        {
            MarketId = Guid.NewGuid(),
            RoundId = round.RoundId,
            MarketType = t.Type.ToLowerInvariant(),
            Label = t.Label,
            Odds = t.Odds,
            Threshold = t.Threshold,
            Min = t.Min,
            Max = t.Max,
            TargetValue = t.TargetValue,
            IsWinner = null,
            SortOrder = i,
        }).ToList();

        db.Rounds.Add(round);
        db.RoundMarkets.AddRange(markets);
        db.RoundEvents.Add(CreateRoundEvent(round, "opened", now, 0, source: "round_manager"));
        await db.SaveChangesAsync();

        _logger.LogInformation(
            "[Round {Id}] Iniciado para camera {CameraId} com {Count} mercado(s). Encerra as {EndsAt:HH:mm:ss} UTC.",
            round.RoundId, round.CameraId, markets.Count, round.EndsAt);
    }

    private static bool EvaluateMarket(RoundMarket market, int finalCount) =>
        market.MarketType switch
        {
            "under" => finalCount < market.Threshold!.Value,
            "over" => finalCount >= market.Threshold!.Value,
            "range" => finalCount >= market.Min!.Value && finalCount <= market.Max!.Value,
            "exact" => finalCount == market.TargetValue!.Value,
            _ => false,
        };

    private async Task BroadcastAsync(string eventName, Round round)
    {
        await _hub.Clients.All.SendAsync(eventName, ToResponse(round));
    }

    private static RoundEvent CreateRoundEvent(
        Round round,
        string eventType,
        DateTime timestampUtc,
        int? countValue = null,
        string? reason = null,
        string? source = null)
    {
        return new RoundEvent
        {
            Id = Guid.NewGuid(),
            RoundId = round.RoundId,
            EventType = eventType,
            RoundStatus = round.Status.ToString().ToLowerInvariant(),
            TimestampUtc = timestampUtc,
            CountValue = countValue ?? round.CurrentCount,
            Reason = reason,
            Source = source,
        };
    }

    private static string BuildSyntheticCountEventHash(RoundCountEventDto dto, Guid roundId)
    {
        var input = string.Join("|",
            roundId,
            dto.CameraId,
            dto.TrackId,
            dto.VehicleType,
            dto.CrossedAt.ToString("O"),
            dto.TotalCount);
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(input))).ToLowerInvariant();
    }

    private static RoundResponse ToResponse(Round r) => new()
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

    private static RoundMarketResponse ToMarketResponse(RoundMarket m) => new()
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
