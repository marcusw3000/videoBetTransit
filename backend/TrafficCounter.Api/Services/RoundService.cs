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
    public const string CameraLockedMessage = "Camera locked while round is active; try again after settlement.";

    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly IHubContext<RoundHub> _hub;
    private readonly ILogger<RoundService> _logger;
    private readonly RoundOptions _options;
    private readonly IRandomSource _randomSource;
    private readonly BetService _betService;
    private readonly DynamicMarketLineService _dynamicMarketLineService;

    public RoundService(
        IDbContextFactory<AppDbContext> dbFactory,
        IHubContext<RoundHub> hub,
        ILogger<RoundService> logger,
        IOptions<RoundOptions> options,
        IRandomSource randomSource,
        BetService betService,
        DynamicMarketLineService dynamicMarketLineService)
    {
        _dbFactory = dbFactory;
        _hub = hub;
        _logger = logger;
        _options = options.Value;
        _randomSource = randomSource;
        _betService = betService;
        _dynamicMarketLineService = dynamicMarketLineService;
    }

    public async Task<bool> EnsureActiveRoundAsync(string cameraId = "default")
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var normalizedCameraId = NormalizeCameraId(cameraId);
        var active = await db.Rounds.AnyAsync(r =>
            r.CameraId == normalizedCameraId &&
            r.Status != RoundStatus.Settled &&
            r.Status != RoundStatus.Void);

        if (active)
            return false;

        await CreateNewRoundAsync(db, normalizedCameraId);
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

        if (rounds.Count == 0)
            return false;

        var changed = false;
        var updatedRounds = new List<Round>();
        var settledRounds = new List<Round>();

        foreach (var round in rounds)
        {
            if (round.Status == RoundStatus.Open && now >= round.BetCloseAt)
            {
                round.Status = RoundStatus.Closing;
                db.RoundEvents.Add(CreateRoundEvent(round, "bet_closed", now, source: "round_manager"));
                updatedRounds.Add(round);
                changed = true;
                _logger.LogInformation("[Round {Id}] Apostas fechadas.", round.RoundId);
                continue;
            }

            if (round.Status == RoundStatus.Closing && now >= round.EndsAt)
            {
                round.Status = RoundStatus.Settling;
                db.RoundEvents.Add(CreateRoundEvent(round, "settling_started", now, source: "round_manager"));
                updatedRounds.Add(round);
                changed = true;
                _logger.LogInformation("[Round {Id}] Entrou em apuracao.", round.RoundId);
                continue;
            }

            if (round.Status == RoundStatus.Settling && now >= round.EndsAt.AddSeconds(_options.SettleDelaySeconds))
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

        foreach (var round in updatedRounds)
            await BroadcastAsync("round_updated", round);

        foreach (var round in settledRounds)
        {
            if (round.FinalCount.HasValue && round.SettledAt.HasValue)
                await _betService.SettleAcceptedBetsForRoundAsync(round.RoundId, round.FinalCount.Value, round.SettledAt.Value);

            await BroadcastAsync("round_settled", round);
            await using var db2 = await _dbFactory.CreateDbContextAsync();
            await CreateNewRoundAsync(db2, round.CameraId);
        }

        return changed;
    }

    public async Task<Round?> IncrementCountAsync(string cameraId = "default")
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var normalizedCameraId = NormalizeCameraId(cameraId);

        var round = await FindCountableRoundAsync(db, normalizedCameraId);
        if (round is null)
        {
            await CreateNewRoundAsync(db, normalizedCameraId);
            round = await FindCountableRoundAsync(db, normalizedCameraId);
        }

        if (round is null)
            return null;

        round.CurrentCount++;
        await db.SaveChangesAsync();

        await BroadcastAsync("count_updated", round);
        return round;
    }

    public async Task<Round?> RecordCountEventAsync(RoundCountEventDto dto)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var cameraId = NormalizeCameraId(dto.CameraId);
        var crossedAt = dto.CrossedAt == default ? DateTime.UtcNow : dto.CrossedAt;
        var trackId = long.TryParse(dto.TrackId, out var parsedTrackId) ? parsedTrackId : 0;
        var eventHash = BuildEventHash(dto, cameraId, crossedAt, trackId);

        var duplicate = await db.VehicleCrossingEvents
            .AsNoTracking()
            .Where(e => e.EventHash == eventHash)
            .Select(e => new { e.RoundId, e.CameraId })
            .FirstOrDefaultAsync();

        if (duplicate is not null)
        {
            _logger.LogInformation(
                "[RoundCountEvent] Duplicado ignorado para camera {CameraId} com hash {EventHash}.",
                duplicate.CameraId,
                eventHash);

            return await db.Rounds
                .Include(r => r.Markets)
                .Where(r => r.RoundId == duplicate.RoundId)
                .FirstOrDefaultAsync();
        }

        var round = await ResolveRoundForCountEventAsync(db, cameraId, dto.RoundId);
        if (round is null)
        {
            _logger.LogWarning(
                "[RoundCountEvent] Evento recebido durante settling para camera {CameraId}; ignorando count ate o proximo round oficial.",
                cameraId);
            return await GetCurrentRoundAsync(cameraId);
        }

        var officialCountBefore = round.CurrentCount;
        var officialCountAfter = officialCountBefore + 1;

        round.CurrentCount = officialCountAfter;

        db.VehicleCrossingEvents.Add(new VehicleCrossingEvent
        {
            Id = Guid.NewGuid(),
            RoundId = round.RoundId,
            SessionId = null,
            CameraId = cameraId,
            TimestampUtc = crossedAt,
            TrackId = trackId,
            ObjectClass = NormalizeVehicleType(dto.VehicleType),
            Direction = string.IsNullOrWhiteSpace(dto.Direction) ? "unknown" : dto.Direction.Trim(),
            LineId = string.IsNullOrWhiteSpace(dto.LineId) ? "round_count_event" : dto.LineId.Trim(),
            FrameNumber = dto.FrameNumber ?? 0,
            Confidence = dto.Confidence ?? 1.0,
            SnapshotUrl = string.IsNullOrWhiteSpace(dto.SnapshotUrl) ? null : dto.SnapshotUrl.Trim(),
            Source = string.IsNullOrWhiteSpace(dto.Source) ? "vision_worker_round_count" : dto.Source.Trim(),
            StreamProfileId = string.IsNullOrWhiteSpace(dto.StreamProfileId) ? null : dto.StreamProfileId.Trim(),
            CountBefore = dto.CountBefore ?? officialCountBefore,
            CountAfter = dto.CountAfter ?? officialCountAfter,
            PreviousEventHash = string.IsNullOrWhiteSpace(dto.PreviousEventHash) ? null : dto.PreviousEventHash.Trim(),
            EventHash = eventHash,
        });

        db.RoundEvents.Add(CreateRoundEvent(
            round,
            "count_recorded",
            crossedAt,
            officialCountAfter,
            source: "vision_worker_round_count"));

        await db.SaveChangesAsync();
        await BroadcastAsync("count_updated", round);
        return round;
    }

    public async Task<Round?> GetCurrentRoundAsync(string cameraId = "default")
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var normalizedCameraId = NormalizeCameraId(cameraId);

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

        if (round is null)
            return false;
        return await VoidRoundAsync(db, round, reason, "internal_api");
    }

    public async Task NotifyStreamProfileActivatedAsync(
        string cameraId,
        string? streamProfileId,
        bool allowSettling = false,
        bool autoSwitchRound = false)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var normalizedCameraId = NormalizeCameraId(cameraId);
        if (!autoSwitchRound)
        {
            var locked = allowSettling
                ? await IsCameraLockedForBoundaryChangeAsync(normalizedCameraId, db)
                : await IsCameraLockedForRoundAsync(normalizedCameraId, db);
            if (locked)
                throw new InvalidOperationException(CameraLockedMessage);
        }

        var normalizedProfileId = NormalizeOptional(streamProfileId);
        var state = await GetOrCreateCameraRoundStateAsync(db, normalizedCameraId);
        var previousProfileId = state.ActiveStreamProfileId;

        if (string.Equals(state.ActiveStreamProfileId, normalizedProfileId, StringComparison.Ordinal))
            return;

        state.ActiveStreamProfileId = normalizedProfileId;
        state.RoundsSinceProfileSwitch = 0;
        state.LastProfileChangedAt = DateTime.UtcNow;
        state.UpdatedAt = DateTime.UtcNow;

        var activeRound = autoSwitchRound
            ? await db.Rounds
                .Include(r => r.Markets)
                .Where(r => r.CameraId == normalizedCameraId)
                .Where(r => r.Status == RoundStatus.Open || r.Status == RoundStatus.Closing || r.Status == RoundStatus.Settling)
                .OrderByDescending(r => r.CreatedAt)
                .FirstOrDefaultAsync()
            : null;

        if (activeRound is null)
        {
            await db.SaveChangesAsync();
            return;
        }

        var reason =
            $"previousProfileId={previousProfileId ?? "none"};newProfileId={normalizedProfileId ?? "none"}";
        await VoidRoundAsync(
            db,
            activeRound,
            "Stream profile changed during active round",
            "stream_profile_activation",
            "stream_profile_changed",
            reason);
    }

    public async Task HandleCameraSourceActivationAsync(string cameraId, string sourceUrl)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var normalizedCameraId = NormalizeCameraId(cameraId);
        var normalizedSourceUrl = NormalizeRequiredSourceUrl(sourceUrl);
        var sourceFingerprint = BuildSourceFingerprint(normalizedSourceUrl);
        var now = DateTime.UtcNow;
        var state = await GetOrCreateCameraRoundStateAsync(db, normalizedCameraId);

        if (string.IsNullOrWhiteSpace(state.LastSourceFingerprint))
        {
            state.LastSourceFingerprint = sourceFingerprint;
            state.LastSourceUrl = normalizedSourceUrl;
            state.LastSourceChangedAt = now;
            state.UpdatedAt = now;
            await db.SaveChangesAsync();
            return;
        }

        if (string.Equals(state.LastSourceFingerprint, sourceFingerprint, StringComparison.Ordinal))
        {
            if (!string.Equals(state.LastSourceUrl, normalizedSourceUrl, StringComparison.Ordinal))
            {
                state.LastSourceUrl = normalizedSourceUrl;
                state.UpdatedAt = now;
                await db.SaveChangesAsync();
            }

            return;
        }

        var previousFingerprint = state.LastSourceFingerprint;
        state.ActiveStreamProfileId = null;
        state.RoundsSinceProfileSwitch = 0;
        state.LastProfileChangedAt = now;
        state.LastSourceFingerprint = sourceFingerprint;
        state.LastSourceUrl = normalizedSourceUrl;
        state.LastSourceChangedAt = now;
        state.UpdatedAt = now;

        var activeRound = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.CameraId == normalizedCameraId)
            .Where(r => r.Status == RoundStatus.Open || r.Status == RoundStatus.Closing || r.Status == RoundStatus.Settling)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        if (activeRound is null)
        {
            await db.SaveChangesAsync();
            _logger.LogInformation(
                "[CameraSource] Source alterada para camera {CameraId}. Nenhum round ativo; baseline resetada.",
                normalizedCameraId);
            return;
        }

        var sourceChangeReason =
            $"previousFingerprint={previousFingerprint};newFingerprint={sourceFingerprint};sourceChangedAt={now:O}";

        await VoidRoundAsync(
            db,
            activeRound,
            "Camera source changed during active round",
            "pipeline_orchestrator",
            "camera_source_changed",
            sourceChangeReason);
    }

    public async Task<bool> IsCameraLockedForRoundAsync(string cameraId = "default")
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        return await IsCameraLockedForRoundAsync(NormalizeCameraId(cameraId), db);
    }

    public async Task EnsureCameraUnlockedAsync(string cameraId = "default")
    {
        if (await IsCameraLockedForRoundAsync(cameraId))
            throw new InvalidOperationException(CameraLockedMessage);
    }

    public async Task EnsureCameraUnlockedForBoundaryChangeAsync(string cameraId = "default")
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        if (await IsCameraLockedForBoundaryChangeAsync(NormalizeCameraId(cameraId), db))
            throw new InvalidOperationException(CameraLockedMessage);
    }

    private async Task CreateNewRoundAsync(AppDbContext db, string cameraId)
    {
        var now = DateTime.UtcNow;
        var normalizedCameraId = NormalizeCameraId(cameraId);
        var state = await GetOrCreateCameraRoundStateAsync(db, normalizedCameraId);
        var selection = SelectRoundMode(state);
        var timing = GetTiming(selection.RoundMode);
        var marketLine = await _dynamicMarketLineService.BuildTemplatesAsync(
            db,
            normalizedCameraId,
            timing.DurationSeconds,
            selection.RoundsSinceProfileSwitch,
            state.LastProfileChangedAt,
            GetMarketTemplates(selection.RoundMode));
        var round = new Round
        {
            RoundId = Guid.NewGuid(),
            CameraId = normalizedCameraId,
            RoundMode = selection.RoundMode,
            Status = RoundStatus.Open,
            DisplayName = GetDisplayName(selection.RoundMode),
            CreatedAt = now,
            BetCloseAt = now.AddSeconds(timing.BetWindowSeconds),
            EndsAt = now.AddSeconds(timing.DurationSeconds),
            CurrentCount = 0,
        };

        var markets = marketLine.Templates.Select((t, i) => new RoundMarket
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

        state.RoundsSinceProfileSwitch += 1;
        state.UpdatedAt = now;

        db.Rounds.Add(round);
        db.RoundMarkets.AddRange(markets);
        db.RoundEvents.Add(CreateRoundEvent(
            round,
            "round_mode_selected",
            now,
            0,
            $"roundMode={selection.RoundMode.ToString().ToLowerInvariant()};eligible={selection.WasEligibleForTurbo.ToString().ToLowerInvariant()};streamProfileId={state.ActiveStreamProfileId ?? "none"};roundsSinceSwitchBeforeCreate={selection.RoundsSinceProfileSwitch}",
            "round_manager"));
        db.RoundEvents.Add(CreateRoundEvent(
            round,
            "market_line_computed",
            now,
            0,
            marketLine.ToAuditReason(),
            "round_manager"));
        db.RoundEvents.Add(CreateRoundEvent(round, "opened", now, 0, source: "round_manager"));
        await db.SaveChangesAsync();

        _logger.LogInformation(
            "[Round {Id}] Iniciado para camera {CameraId} no modo {RoundMode} com {Count} mercado(s). Encerra as {EndsAt:HH:mm:ss} UTC.",
            round.RoundId,
            round.CameraId,
            round.RoundMode,
            markets.Count,
            round.EndsAt);
    }

    private async Task<Round?> ResolveRoundForCountEventAsync(AppDbContext db, string cameraId, string? explicitRoundId)
    {
        if (Guid.TryParse(explicitRoundId, out var parsedRoundId))
        {
            var explicitRound = await db.Rounds
                .Include(r => r.Markets)
                .Where(r => r.RoundId == parsedRoundId)
                .Where(r => r.CameraId == cameraId)
                .Where(r => r.Status == RoundStatus.Open || r.Status == RoundStatus.Closing)
                .FirstOrDefaultAsync();

            if (explicitRound is not null)
                return explicitRound;
        }

        var countableRound = await FindCountableRoundAsync(db, cameraId);
        if (countableRound is not null)
            return countableRound;

        var settlingRound = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.CameraId == cameraId)
            .Where(r => r.Status == RoundStatus.Settling)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        if (settlingRound is not null)
            return null;

        await CreateNewRoundAsync(db, cameraId);
        return await FindCountableRoundAsync(db, cameraId);
    }

    private static Task<Round?> FindCountableRoundAsync(AppDbContext db, string cameraId)
    {
        return db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.CameraId == cameraId)
            .Where(r => r.Status == RoundStatus.Open || r.Status == RoundStatus.Closing)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();
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

    private static string BuildEventHash(RoundCountEventDto dto, string cameraId, DateTime crossedAt, long trackId)
    {
        if (!string.IsNullOrWhiteSpace(dto.EventHash))
            return dto.EventHash.Trim();

        var input = string.Join("|",
            dto.RoundId,
            cameraId,
            dto.StreamProfileId,
            dto.LineId,
            trackId,
            dto.VehicleType,
            crossedAt.ToString("O"),
            dto.TotalCount,
            dto.CountBefore,
            dto.CountAfter);

        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(input))).ToLowerInvariant();
    }

    private static string NormalizeCameraId(string cameraId)
    {
        return string.IsNullOrWhiteSpace(cameraId) ? "default" : cameraId.Trim();
    }

    private static string NormalizeRequiredSourceUrl(string sourceUrl)
    {
        var normalized = NormalizeOptional(sourceUrl);
        return normalized ?? throw new InvalidOperationException("sourceUrl is required.");
    }

    private static string? NormalizeOptional(string? value)
    {
        var normalized = string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        return string.IsNullOrWhiteSpace(normalized) ? null : normalized;
    }

    private static string BuildSourceFingerprint(string normalizedSourceUrl)
    {
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(normalizedSourceUrl))).ToLowerInvariant();
    }

    private static string NormalizeVehicleType(string vehicleType)
    {
        return string.IsNullOrWhiteSpace(vehicleType) ? "unknown" : vehicleType.Trim();
    }

    private static RoundResponse ToResponse(Round r) => new()
    {
        RoundId = r.RoundId.ToString(),
        CameraId = r.CameraId,
        CameraIds = string.IsNullOrWhiteSpace(r.CameraId) ? [] : [r.CameraId],
        RoundMode = r.RoundMode.ToString().ToLowerInvariant(),
        DisplayName = r.DisplayName,
        Status = r.Status.ToString().ToLowerInvariant(),
        IsSuspended = r.Status != RoundStatus.Open,
        CreatedAt = SaoPauloTime.FromUtc(r.CreatedAt),
        BetCloseAt = SaoPauloTime.FromUtc(r.BetCloseAt),
        EndsAt = SaoPauloTime.FromUtc(r.EndsAt),
        SettledAt = SaoPauloTime.FromUtc(r.SettledAt),
        VoidedAt = SaoPauloTime.FromUtc(r.VoidedAt),
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

    private async Task<CameraRoundState> GetOrCreateCameraRoundStateAsync(AppDbContext db, string cameraId)
    {
        var state = await db.CameraRoundStates.FirstOrDefaultAsync(x => x.CameraId == cameraId);
        if (state is not null)
            return state;

        state = new CameraRoundState
        {
            CameraId = cameraId,
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
            RoundsSinceProfileSwitch = 0,
        };

        db.CameraRoundStates.Add(state);
        return state;
    }

    private RoundModeSelection SelectRoundMode(CameraRoundState state)
    {
        var warmupRounds = Math.Max(0, _options.Turbo.WarmupRoundsAfterProfileSwitch);
        var roundsSinceProfileSwitch = Math.Max(0, state.RoundsSinceProfileSwitch);
        var eligibleForTurbo = _options.Turbo.Enabled
            && roundsSinceProfileSwitch >= warmupRounds
            && GetMarketTemplates(RoundMode.Turbo).Count > 0;

        var selectedMode = eligibleForTurbo && _randomSource.NextDouble() < Math.Clamp(_options.Turbo.Probability, 0.0, 1.0)
            ? RoundMode.Turbo
            : RoundMode.Normal;

        return new RoundModeSelection(selectedMode, eligibleForTurbo, roundsSinceProfileSwitch);
    }

    private List<MarketTemplate> GetMarketTemplates(RoundMode roundMode)
    {
        var preferred = roundMode == RoundMode.Turbo
            ? _options.MarketSets.Turbo
            : _options.MarketSets.Normal;

        if (preferred is { Count: > 0 })
            return preferred;

        if (_options.Markets.Count > 0)
            return _options.Markets;

        return [];
    }

    private static string GetDisplayName(RoundMode roundMode) => roundMode switch
    {
        RoundMode.Turbo => "Rodada Turbo",
        _ => "Rodada Normal",
    };

    private RoundModeTimingOptions GetTiming(RoundMode roundMode)
    {
        var configured = roundMode == RoundMode.Turbo
            ? _options.Timing.Turbo
            : _options.Timing.Normal;

        if (configured.DurationSeconds > 0 && configured.BetWindowSeconds > 0)
            return configured;

        return new RoundModeTimingOptions
        {
            DurationSeconds = Math.Max(1, _options.DurationSeconds),
            BetWindowSeconds = Math.Max(1, _options.BetWindowSeconds),
        };
    }

    private readonly record struct RoundModeSelection(
        RoundMode RoundMode,
        bool WasEligibleForTurbo,
        int RoundsSinceProfileSwitch);

    private async Task<bool> VoidRoundAsync(
        AppDbContext db,
        Round round,
        string reason,
        string source,
        string? preVoidEventType = null,
        string? preVoidEventReason = null)
    {
        if (round.Status == RoundStatus.Settled || round.Status == RoundStatus.Void)
            return false;

        var voidedAt = DateTime.UtcNow;
        if (!string.IsNullOrWhiteSpace(preVoidEventType))
        {
            db.RoundEvents.Add(CreateRoundEvent(
                round,
                preVoidEventType,
                voidedAt,
                round.CurrentCount,
                preVoidEventReason,
                source));
        }

        round.Status = RoundStatus.Void;
        round.VoidedAt = voidedAt;
        round.VoidReason = reason;
        db.RoundEvents.Add(CreateRoundEvent(round, "voided", voidedAt, round.CurrentCount, reason, source));

        await db.SaveChangesAsync();
        _logger.LogInformation("[Round {Id}] Anulado. Motivo: {Reason}", round.RoundId, reason);

        await _betService.VoidAcceptedBetsForRoundAsync(round.RoundId, voidedAt);
        await BroadcastAsync("round_voided", round);

        await using var db2 = await _dbFactory.CreateDbContextAsync();
        await CreateNewRoundAsync(db2, round.CameraId);

        return true;
    }

    private static Task<bool> IsCameraLockedForRoundAsync(string cameraId, AppDbContext db) =>
        db.Rounds.AnyAsync(r =>
            r.CameraId == cameraId &&
            (r.Status == RoundStatus.Open ||
             r.Status == RoundStatus.Closing ||
             r.Status == RoundStatus.Settling));

    private static Task<bool> IsCameraLockedForBoundaryChangeAsync(string cameraId, AppDbContext db) =>
        db.Rounds.AnyAsync(r =>
            r.CameraId == cameraId &&
            (r.Status == RoundStatus.Open ||
             r.Status == RoundStatus.Closing));
}
