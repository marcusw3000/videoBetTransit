using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Services;

public class BetService
{
    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly ILogger<BetService> _logger;

    public BetService(IDbContextFactory<AppDbContext> dbFactory, ILogger<BetService> logger)
    {
        _dbFactory = dbFactory;
        _logger = logger;
    }

    public async Task<BetResponse> PlaceBetAsync(CreateBetDto dto)
    {
        var transactionId = NormalizeRequired(dto.TransactionId, "transactionId");
        var gameSessionId = NormalizeRequired(dto.GameSessionId, "gameSessionId");
        var currency = NormalizeRequired(dto.Currency, "currency").ToUpperInvariant();
        var roundId = ParseGuid(dto.RoundId, "roundId");
        var marketId = ParseGuid(dto.MarketId, "marketId");

        if (dto.StakeAmount <= 0)
            throw new InvalidOperationException("stakeAmount must be greater than zero.");

        await using var db = await _dbFactory.CreateDbContextAsync();

        var duplicate = await db.Bets
            .AsNoTracking()
            .FirstOrDefaultAsync(b => b.TransactionId == transactionId);

        if (duplicate is not null)
            return ToResponse(duplicate);

        var round = await db.Rounds
            .Include(r => r.Markets)
            .FirstOrDefaultAsync(r => r.RoundId == roundId);

        if (round is null)
            throw new InvalidOperationException($"Round '{roundId}' nao encontrado.");
        if (round.Status != RoundStatus.Open)
            throw new InvalidOperationException("Aposta so pode ser aceita com round em status open.");
        if (DateTime.UtcNow >= round.BetCloseAt)
            throw new InvalidOperationException("Janela de apostas encerrada para este round.");

        var market = round.Markets.FirstOrDefault(m => m.MarketId == marketId);
        if (market is null)
            throw new InvalidOperationException($"Market '{marketId}' nao encontrado no round informado.");

        var now = DateTime.UtcNow;
        var bet = new Bet
        {
            Id = Guid.NewGuid(),
            ProviderBetId = BuildProviderBetId(),
            TransactionId = transactionId,
            GameSessionId = gameSessionId,
            RoundId = round.RoundId,
            CameraId = round.CameraId,
            RoundMode = round.RoundMode,
            MarketId = market.MarketId,
            MarketType = market.MarketType,
            MarketLabel = market.Label,
            Odds = market.Odds,
            Threshold = market.Threshold,
            Min = market.Min,
            Max = market.Max,
            TargetValue = market.TargetValue,
            StakeAmount = decimal.Round(dto.StakeAmount, 2, MidpointRounding.AwayFromZero),
            PotentialPayout = decimal.Round(dto.StakeAmount * market.Odds, 2, MidpointRounding.AwayFromZero),
            Currency = currency,
            Status = BetStatus.Accepted,
            PlacedAt = now,
            AcceptedAt = now,
            PlayerRef = NormalizeOptional(dto.PlayerRef),
            OperatorRef = NormalizeOptional(dto.OperatorRef),
            MetadataJson = NormalizeOptional(dto.MetadataJson),
        };

        db.Bets.Add(bet);
        await db.SaveChangesAsync();

        _logger.LogInformation(
            "[Bet {BetId}] Aceita para round {RoundId}, market {MarketId}, stake {Stake} {Currency}.",
            bet.Id,
            bet.RoundId,
            bet.MarketId,
            bet.StakeAmount,
            bet.Currency);

        return ToResponse(bet);
    }

    public async Task<BetResponse?> GetByIdAsync(Guid betId)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var bet = await db.Bets
            .AsNoTracking()
            .FirstOrDefaultAsync(b => b.Id == betId);

        return bet is null ? null : ToResponse(bet);
    }

    public async Task SettleAcceptedBetsForRoundAsync(Guid roundId, int finalCount, DateTime settledAtUtc)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var bets = await db.Bets
            .Where(b => b.RoundId == roundId && b.Status == BetStatus.Accepted)
            .ToListAsync();

        if (bets.Count == 0)
            return;

        foreach (var bet in bets)
        {
            bet.Status = EvaluateBet(bet, finalCount) ? BetStatus.SettledWin : BetStatus.SettledLoss;
            bet.SettledAt = settledAtUtc;
        }

        await db.SaveChangesAsync();
    }

    public async Task VoidAcceptedBetsForRoundAsync(Guid roundId, DateTime voidedAtUtc)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var bets = await db.Bets
            .Where(b => b.RoundId == roundId && b.Status == BetStatus.Accepted)
            .ToListAsync();

        if (bets.Count == 0)
            return;

        foreach (var bet in bets)
        {
            bet.Status = BetStatus.Void;
            bet.VoidedAt = voidedAtUtc;
        }

        await db.SaveChangesAsync();
    }

    private static bool EvaluateBet(Bet bet, int finalCount) =>
        bet.MarketType switch
        {
            "under" => bet.Threshold.HasValue && finalCount < bet.Threshold.Value,
            "over" => bet.Threshold.HasValue && finalCount >= bet.Threshold.Value,
            "range" => bet.Min.HasValue && bet.Max.HasValue && finalCount >= bet.Min.Value && finalCount <= bet.Max.Value,
            "exact" => bet.TargetValue.HasValue && finalCount == bet.TargetValue.Value,
            _ => false,
        };

    private static string NormalizeRequired(string? value, string fieldName)
    {
        var normalized = NormalizeOptional(value);
        return normalized ?? throw new InvalidOperationException($"{fieldName} is required.");
    }

    private static string? NormalizeOptional(string? value)
    {
        var normalized = string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        return string.IsNullOrWhiteSpace(normalized) ? null : normalized;
    }

    private static Guid ParseGuid(string? value, string fieldName)
    {
        if (Guid.TryParse(value, out var guid))
            return guid;

        throw new InvalidOperationException($"{fieldName} must be a valid guid.");
    }

    private static string BuildProviderBetId() => $"bet_{Guid.NewGuid():N}";

    private static BetResponse ToResponse(Bet bet) => new()
    {
        Id = bet.Id.ToString(),
        ProviderBetId = bet.ProviderBetId,
        TransactionId = bet.TransactionId,
        GameSessionId = bet.GameSessionId,
        RoundId = bet.RoundId.ToString(),
        CameraId = bet.CameraId,
        RoundMode = bet.RoundMode.ToString().ToLowerInvariant(),
        MarketId = bet.MarketId.ToString(),
        MarketType = bet.MarketType,
        MarketLabel = bet.MarketLabel,
        Odds = bet.Odds,
        Threshold = bet.Threshold,
        Min = bet.Min,
        Max = bet.Max,
        TargetValue = bet.TargetValue,
        StakeAmount = bet.StakeAmount,
        PotentialPayout = bet.PotentialPayout,
        Currency = bet.Currency,
        Status = ConvertBetStatus(bet.Status),
        PlacedAt = bet.PlacedAt,
        AcceptedAt = bet.AcceptedAt,
        SettledAt = bet.SettledAt,
        VoidedAt = bet.VoidedAt,
        RollbackOfTransactionId = bet.RollbackOfTransactionId,
        PlayerRef = bet.PlayerRef,
        OperatorRef = bet.OperatorRef,
        MetadataJson = bet.MetadataJson,
    };

    private static string ConvertBetStatus(BetStatus status) => status switch
    {
        BetStatus.Accepted => "accepted",
        BetStatus.SettledWin => "settled_win",
        BetStatus.SettledLoss => "settled_loss",
        BetStatus.Void => "void",
        BetStatus.Rollback => "rollback",
        _ => status.ToString().ToLowerInvariant(),
    };
}
