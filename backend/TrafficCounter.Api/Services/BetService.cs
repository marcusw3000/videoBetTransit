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

    public async Task<BetResponse> PlaceBetAsync(CreateBetDto dto, string playerRef, string operatorRef)
    {
        var transactionId = NormalizeRequired(dto.TransactionId, "transactionId");
        var gameSessionId = NormalizeRequired(dto.GameSessionId, "gameSessionId");
        var currency = NormalizeRequired(dto.Currency, "currency").ToUpperInvariant();
        var roundId = ParseGuid(dto.RoundId, "roundId");
        var marketId = ParseGuid(dto.MarketId, "marketId");

        if (dto.StakeAmount < 0.01m || dto.StakeAmount > 10000m || decimal.Round(dto.StakeAmount, 2) != dto.StakeAmount)
            throw new RequestRejectedException("Valor deve estar entre 0,01 e 10.000,00, com no maximo duas casas decimais.", 400);
        if (currency != "BRL") throw new RequestRejectedException("Moeda permitida: BRL.", 400);
        if (transactionId.Length > 128 || gameSessionId.Length > 128 || (dto.MetadataJson?.Length ?? 0) > 4096)
            throw new RequestRejectedException("Solicitacao excede os limites de tamanho.", 400);
        if (string.IsNullOrWhiteSpace(playerRef) || string.IsNullOrWhiteSpace(operatorRef))
            throw new RequestRejectedException("Identidade obrigatoria.", 401);

        await using var db = await _dbFactory.CreateDbContextAsync();

        var duplicate = await db.Bets
            .AsNoTracking()
            .FirstOrDefaultAsync(b => b.TransactionId == transactionId && b.PlayerRef == playerRef && b.OperatorRef == operatorRef);

        if (duplicate is not null)
        {
            if (duplicate.RoundId != roundId || duplicate.MarketId != marketId
                || duplicate.StakeAmount != dto.StakeAmount || duplicate.Currency != currency
                || duplicate.GameSessionId != gameSessionId || duplicate.MetadataJson != NormalizeOptional(dto.MetadataJson))
                throw new RequestRejectedException("Identificador ja utilizado com dados diferentes.");
            return ToResponse(duplicate);
        }

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
            PlayerRef = playerRef,
            OperatorRef = operatorRef,
            MetadataJson = NormalizeOptional(dto.MetadataJson),
        };

        // Participate in the round revision check even though its status does not change.
        db.Entry(round).Property(r => r.Status).IsModified = true;
        if (DateTime.UtcNow >= round.BetCloseAt)
            throw new RequestRejectedException("Janela de apostas encerrada.");
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

    public async Task<BetResponse?> GetByIdAsync(Guid betId, string playerRef, string operatorRef)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var bet = await db.Bets
            .AsNoTracking()
            .FirstOrDefaultAsync(b => b.Id == betId && b.PlayerRef == playerRef && b.OperatorRef == operatorRef);

        return bet is null ? null : ToResponse(bet);
    }

    public async Task<object> ListAsync(string playerRef, string operatorRef, string? status,
        DateTime? from, DateTime? to, int page, int pageSize)
    {
        if (page < 1 || pageSize < 1 || pageSize > 100 || (from.HasValue && to.HasValue && from > to))
            throw new RequestRejectedException("Paginacao ou periodo invalido.", 400);
        await using var db = await _dbFactory.CreateDbContextAsync();
        var query = db.Bets.AsNoTracking().Where(b => b.PlayerRef == playerRef && b.OperatorRef == operatorRef);
        if (status == "open") query = query.Where(b => b.Status == BetStatus.Accepted);
        else if (status == "closed") query = query.Where(b => b.Status != BetStatus.Accepted);
        else if (!string.IsNullOrEmpty(status) && status != "all") throw new RequestRejectedException("Filtro invalido.", 400);
        if (from.HasValue) query = query.Where(b => b.PlacedAt >= from.Value.ToUniversalTime());
        if (to.HasValue) query = query.Where(b => b.PlacedAt <= to.Value.ToUniversalTime());
        var total = await query.CountAsync();
        var items = await query.OrderByDescending(b => b.PlacedAt).ThenBy(b => b.Id)
            .Skip((page - 1) * pageSize).Take(pageSize).ToListAsync();
        return new { items = items.Select(ToResponse), total, page, pageSize };
    }

    public async Task ReconcileAsync()
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var bets = await db.Bets.Include(b => b.Round).Where(b => b.Status == BetStatus.Accepted
            && (b.Round.Status == RoundStatus.Settled || b.Round.Status == RoundStatus.Void)).ToListAsync();
        foreach (var bet in bets) AppDbContext.ApplyResult(bet, bet.Round);
        await db.SaveChangesAsync();
    }

    public static bool EvaluateBet(Bet bet, int finalCount) =>
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
