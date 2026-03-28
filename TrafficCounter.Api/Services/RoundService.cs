using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Models;

namespace TrafficCounter.Api.Services;

public class RoundService
{
    public const string StatusOpen = "open";
    public const string StatusClosing = "closing";
    public const string StatusSettling = "settling";
    public const string StatusSettled = "settled";
    public const string StatusVoid = "void";

    private readonly IDbContextFactory<TrafficCounterDbContext> _dbContextFactory;
    private readonly object _lock = new();

    public RoundService(IDbContextFactory<TrafficCounterDbContext> dbContextFactory)
    {
        _dbContextFactory = dbContextFactory;
        EnsureCurrentRoundExists();
    }

    public Round GetCurrent()
    {
        lock (_lock)
        {
            using var db = _dbContextFactory.CreateDbContext();
            var current = GetOrCreateCurrentTracked(db);
            var now = DateTime.UtcNow;

            if (ApplyLifecycleState(current, now))
            {
                db.SaveChanges();
            }

            if (current.Status == StatusSettling && now >= current.EndsAt)
            {
                current = FinalizeRound(db, current);
                db.SaveChanges();
            }

            return CloneRound(current);
        }
    }

    public List<Round> GetHistory()
    {
        using var db = _dbContextFactory.CreateDbContext();
        return db.Rounds
            .AsNoTracking()
            .Include(r => r.Ranges)
            .Where(r => r.Status == StatusSettled || r.Status == StatusVoid)
            .OrderByDescending(r => r.CreatedAt)
            .Take(20)
            .ToList();
    }

    public Round? Settle(string currentId)
    {
        lock (_lock)
        {
            using var db = _dbContextFactory.CreateDbContext();
            var current = db.Rounds
                .Include(r => r.Ranges)
                .SingleOrDefault(r => r.Id == currentId);

            if (current is null || current.Status == StatusSettled || current.Status == StatusVoid)
                return null;

            var newRound = FinalizeRound(db, current);
            db.SaveChanges();

            return CloneRound(newRound);
        }
    }

    public Round SyncCount(CountEvent evt)
    {
        lock (_lock)
        {
            using var db = _dbContextFactory.CreateDbContext();
            var now = DateTime.UtcNow;
            var current = GetOrCreateCurrentTracked(db);

            if (ApplyLifecycleState(current, now))
            {
                db.SaveChanges();
            }

            if (current.Status == StatusSettling && now >= current.EndsAt)
            {
                current = FinalizeRound(db, current);
                db.SaveChanges();
            }

            var alreadyRecorded = db.CountEvents.Any(x =>
                x.RoundId == current.Id &&
                x.TrackId == evt.TrackId
            );

            if (!alreadyRecorded)
            {
                evt.RoundId = current.Id;
                db.CountEvents.Add(evt);
            }

            if (evt.TotalCount > current.CurrentCount)
                current.CurrentCount = evt.TotalCount;

            db.SaveChanges();
            return CloneRound(current);
        }
    }

    public List<CountEvent> GetCountEvents(string roundId)
    {
        using var db = _dbContextFactory.CreateDbContext();
        return db.CountEvents
            .AsNoTracking()
            .Where(x => x.RoundId == roundId)
            .OrderBy(x => x.CrossedAt)
            .ToList();
    }

    public RoundTickResult Tick()
    {
        lock (_lock)
        {
            using var db = _dbContextFactory.CreateDbContext();
            var current = GetOrCreateCurrentTracked(db);
            var now = DateTime.UtcNow;
            Round? updatedRound = null;

            if (ApplyLifecycleState(current, now))
            {
                db.SaveChanges();
                updatedRound = CloneRound(current);
            }

            if (current.Status == StatusSettling && now >= current.EndsAt)
            {
                var newRound = FinalizeRound(db, current);
                db.SaveChanges();
                return new RoundTickResult(updatedRound, CloneRound(newRound));
            }

            return new RoundTickResult(updatedRound, null);
        }
    }

    private void EnsureCurrentRoundExists()
    {
        lock (_lock)
        {
            using var db = _dbContextFactory.CreateDbContext();
            var existing = db.Rounds
                .Include(r => r.Ranges)
                .OrderByDescending(r => r.CreatedAt)
                .FirstOrDefault(r =>
                    r.Status == StatusOpen ||
                    r.Status == StatusClosing ||
                    r.Status == StatusSettling
                );

            if (existing is not null)
                return;

            db.Rounds.Add(CreateNewRound());
            db.SaveChanges();
        }
    }

    private static Round GetOrCreateCurrentTracked(TrafficCounterDbContext db)
    {
        var round = db.Rounds
            .Include(r => r.Ranges)
            .OrderByDescending(r => r.CreatedAt)
            .FirstOrDefault(r =>
                r.Status == StatusOpen ||
                r.Status == StatusClosing ||
                r.Status == StatusSettling
            );

        if (round is null)
        {
            round = CreateNewRound();
            db.Rounds.Add(round);
            db.SaveChanges();
        }

        return round;
    }

    private static Round CreateNewRound()
    {
        var id = $"rnd_{Guid.NewGuid().ToString()[..8]}";
        const int targetValue = 20;
        var createdAt = DateTime.UtcNow;
        var betCloseAt = createdAt.AddSeconds(50);
        var endsAt = createdAt.AddSeconds(60);

        return new Round
        {
            Id = id,
            Status = StatusOpen,
            CurrentCount = 0,
            CreatedAt = createdAt,
            BetCloseAt = betCloseAt,
            EndsAt = endsAt,
            Ranges = new List<RoundRange>
            {
                new() { Id = $"{id}_m1", RoundId = id, MarketType = "under", Label = "Under", Min = 0, Max = targetValue - 1, TargetValue = targetValue, Odds = 3.0, IsWinner = null },
                new() { Id = $"{id}_m2", RoundId = id, MarketType = "range", Label = "11-20", Min = 11, Max = 20, TargetValue = null, Odds = 2.25, IsWinner = null },
                new() { Id = $"{id}_m3", RoundId = id, MarketType = "over", Label = "Over", Min = targetValue + 1, Max = 999, TargetValue = targetValue, Odds = 3.6, IsWinner = null },
                new() { Id = $"{id}_m4", RoundId = id, MarketType = "exact", Label = "20", Min = targetValue, Max = targetValue, TargetValue = targetValue, Odds = 18.0, IsWinner = null },
            }
        };
    }

    private static bool ApplyLifecycleState(Round round, DateTime now)
    {
        if (round.Status == StatusSettled || round.Status == StatusVoid)
            return false;

        var nextStatus = now >= round.EndsAt
            ? StatusSettling
            : now >= round.BetCloseAt
                ? StatusClosing
                : StatusOpen;

        if (round.Status == nextStatus)
            return false;

        round.Status = nextStatus;
        return true;
    }

    private static Round FinalizeRound(TrafficCounterDbContext db, Round current)
    {
        current.Status = StatusSettled;
        current.FinalCount = current.CurrentCount;

        foreach (var market in current.Ranges)
        {
            market.IsWinner = IsWinningMarket(market, current.CurrentCount);
        }

        var newRound = CreateNewRound();
        db.Rounds.Add(newRound);
        return newRound;
    }

    private static bool IsWinningMarket(RoundRange market, int finalCount)
    {
        return market.MarketType switch
        {
            "under" => market.TargetValue.HasValue && finalCount < market.TargetValue.Value,
            "range" => finalCount >= market.Min && finalCount <= market.Max,
            "over" => market.TargetValue.HasValue && finalCount > market.TargetValue.Value,
            "exact" => market.TargetValue.HasValue && finalCount == market.TargetValue.Value,
            _ => false,
        };
    }

    private static Round CloneRound(Round round)
    {
        return new Round
        {
            Id = round.Id,
            Status = round.Status,
            CurrentCount = round.CurrentCount,
            CreatedAt = round.CreatedAt,
            BetCloseAt = round.BetCloseAt,
            EndsAt = round.EndsAt,
            FinalCount = round.FinalCount,
            Ranges = round.Ranges
                .Select(r => new RoundRange
                {
                    Id = r.Id,
                    RoundId = r.RoundId,
                    MarketType = r.MarketType,
                    Label = r.Label,
                    Min = r.Min,
                    Max = r.Max,
                    TargetValue = r.TargetValue,
                    Odds = r.Odds,
                    IsWinner = r.IsWinner,
                })
                .ToList(),
        };
    }
}

public sealed record RoundTickResult(Round? UpdatedRound, Round? NewCurrentRound);
