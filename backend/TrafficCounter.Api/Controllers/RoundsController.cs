using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("rounds")]
public class RoundsController : ControllerBase
{
    private readonly IDbContextFactory<AppDbContext> _dbFactory;

    public RoundsController(IDbContextFactory<AppDbContext> dbFactory)
    {
        _dbFactory = dbFactory;
    }

    [HttpGet("current")]
    public async Task<IActionResult> GetCurrent()
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        // Round ativo (não settled e não void)
        var round = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.Status != RoundStatus.Settled && r.Status != RoundStatus.Void)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        // Fallback: último round encerrado
        round ??= await db.Rounds
            .Include(r => r.Markets)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefaultAsync();

        if (round is null)
            return NotFound(new { error = "Nenhum round disponível ainda." });

        return Ok(ToResponse(round));
    }

    [HttpGet("history")]
    public async Task<IActionResult> GetHistory([FromQuery] int limit = 20)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        var rounds = await db.Rounds
            .Include(r => r.Markets)
            .Where(r => r.Status == RoundStatus.Settled || r.Status == RoundStatus.Void)
            .OrderByDescending(r => r.SettledAt ?? r.VoidedAt)
            .Take(Math.Clamp(limit, 1, 100))
            .ToListAsync();

        return Ok(rounds.Select(ToResponse));
    }

    [HttpGet("{roundId:guid}/count-events")]
    public IActionResult GetCountEvents(Guid roundId)
    {
        // Stub — retorna lista vazia por ora
        return Ok(Array.Empty<object>());
    }

    // ── DTO mapping ─────────────────────────────────────────────────────────

    private static RoundResponse ToResponse(Domain.Entities.Round r) => new()
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
