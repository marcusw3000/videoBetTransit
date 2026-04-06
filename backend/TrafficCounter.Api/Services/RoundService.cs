using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
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

    // ── API pública ─────────────────────────────────────────────────────────

    /// <summary>Garante que existe um round ativo. Cria um se não houver.</summary>
    public async Task<bool> EnsureActiveRoundAsync()
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var active = await db.Rounds.AnyAsync(r =>
            r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void);
        if (active) return false;

        await CreateNewRoundAsync(db);
        return true;
    }

    /// <summary>Avança fases do round baseado no tempo. Chamado a cada segundo.</summary>
    public async Task<bool> TickAsync()
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var now = DateTime.UtcNow;

        var round = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        if (round is null) return false;

        bool changed = false;

        // Open → Closing
        if (round.Status == RoundStatus.Open && now >= round.BetCloseAt)
        {
            round.Status = RoundStatus.Closing;
            changed = true;
            _logger.LogInformation("[Round {Id}] Apostas fechadas.", round.RoundId);
        }

        // Closing → Settled
        if (round.Status == RoundStatus.Closing && now >= round.EndsAt)
        {
            round.Status = RoundStatus.Settled;
            round.FinalCount = round.CurrentCount;
            round.SettledAt = now;
            changed = true;

            // Avalia cada mercado
            foreach (var market in round.Markets)
                market.IsWinner = EvaluateMarket(market, round.FinalCount.Value);

            _logger.LogInformation("[Round {Id}] Encerrado. Total: {Count}", round.RoundId, round.FinalCount);
        }

        if (changed)
            await db.SaveChangesAsync();

        if (round.Status == RoundStatus.Settled)
        {
            await BroadcastAsync("round_settled", round);
            await using var db2 = await _dbFactory.CreateDbContextAsync();
            await CreateNewRoundAsync(db2);
            return true;
        }

        return false;
    }

    /// <summary>Incrementa a contagem do round ativo e envia count_updated.</summary>
    public async Task IncrementCountAsync()
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var round = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        if (round is null) return;

        round.CurrentCount++;
        await db.SaveChangesAsync();

        await BroadcastAsync("count_updated", round);
    }

    /// <summary>Anula um round. Retorna false se não encontrado ou já finalizado.</summary>
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

        // Mercados permanecem com IsWinner = null (anulados)

        await db.SaveChangesAsync();
        _logger.LogInformation("[Round {Id}] Anulado. Motivo: {Reason}", round.RoundId, reason);

        await BroadcastAsync("round_voided", round);

        // Inicia novo round para não deixar a UI parada
        await using var db2 = await _dbFactory.CreateDbContextAsync();
        await CreateNewRoundAsync(db2);

        return true;
    }

    // ── Internos ────────────────────────────────────────────────────────────

    private async Task CreateNewRoundAsync(AppDbContext db)
    {
        var now = DateTime.UtcNow;
        var round = new Round
        {
            RoundId = Guid.NewGuid(),
            Status = RoundStatus.Open,
            DisplayName = "Rodada Turbo",
            CreatedAt = now,
            BetCloseAt = now.AddSeconds(_options.BetWindowSeconds),
            EndsAt = now.AddSeconds(_options.DurationSeconds),
            CurrentCount = 0,
        };

        // Gera mercados a partir da configuração
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
        await db.SaveChangesAsync();

        _logger.LogInformation(
            "[Round {Id}] Iniciado com {Count} mercado(s). Encerra às {EndsAt:HH:mm:ss} UTC.",
            round.RoundId, markets.Count, round.EndsAt);
    }

    private static bool EvaluateMarket(RoundMarket market, int finalCount) =>
        market.MarketType switch
        {
            "under" => finalCount < market.Threshold!.Value,
            "over"  => finalCount >= market.Threshold!.Value,
            "range" => finalCount >= market.Min!.Value && finalCount <= market.Max!.Value,
            "exact" => finalCount == market.TargetValue!.Value,
            _       => false,
        };

    private async Task BroadcastAsync(string eventName, Round round)
    {
        await _hub.Clients.All.SendAsync(eventName, ToResponse(round));
    }

    // ── DTO mapping ─────────────────────────────────────────────────────────

    private static RoundResponse ToResponse(Round r) => new()
    {
        RoundId = r.RoundId.ToString(),
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
        // under/over: TargetValue = Threshold; range: Min/Max; exact: TargetValue
        TargetValue = m.MarketType is "under" or "over" ? m.Threshold : m.TargetValue,
        Min = m.Min,
        Max = m.Max,
        IsWinner = m.IsWinner,
    };
}
