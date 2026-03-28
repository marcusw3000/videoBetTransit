using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Models;

namespace TrafficCounter.Api.Services;

public class RoundService
{
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
            return CloneRound(GetOrCreateCurrentTracked(db));
        }
    }

    public List<Round> GetHistory()
    {
        using var db = _dbContextFactory.CreateDbContext();
        return db.Rounds
            .AsNoTracking()
            .Include(r => r.Ranges)
            .Where(r => r.Status == "settled")
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

            if (current is null || current.Status == "settled")
                return null;

            current.Status = "settled";
            current.FinalCount = current.CurrentCount;

            var newRound = CreateNewRound();
            db.Rounds.Add(newRound);
            db.SaveChanges();

            return CloneRound(newRound);
        }
    }

    public Round SyncCount(CountEvent evt)
    {
        lock (_lock)
        {
            using var db = _dbContextFactory.CreateDbContext();
            var current = GetOrCreateCurrentTracked(db);

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

    private void EnsureCurrentRoundExists()
    {
        lock (_lock)
        {
            using var db = _dbContextFactory.CreateDbContext();
            var existing = db.Rounds
                .Include(r => r.Ranges)
                .OrderByDescending(r => r.CreatedAt)
                .FirstOrDefault(r => r.Status == "running");

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
            .FirstOrDefault(r => r.Status == "running");

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

        return new Round
        {
            Id = id,
            Status = "running",
            CurrentCount = 0,
            CreatedAt = DateTime.UtcNow,
            EndsAt = DateTime.UtcNow.AddMinutes(5),
            Ranges = new List<RoundRange>
            {
                new() { Id = $"{id}_r1", RoundId = id, Label = "0-10", Min = 0, Max = 10, Odds = 3.5 },
                new() { Id = $"{id}_r2", RoundId = id, Label = "11-20", Min = 11, Max = 20, Odds = 2.2 },
                new() { Id = $"{id}_r3", RoundId = id, Label = "21-35", Min = 21, Max = 35, Odds = 1.8 },
                new() { Id = $"{id}_r4", RoundId = id, Label = "36+", Min = 36, Max = 999, Odds = 4.0 },
            }
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
            EndsAt = round.EndsAt,
            FinalCount = round.FinalCount,
            Ranges = round.Ranges
                .Select(r => new RoundRange
                {
                    Id = r.Id,
                    RoundId = r.RoundId,
                    Label = r.Label,
                    Min = r.Min,
                    Max = r.Max,
                    Odds = r.Odds,
                })
                .ToList(),
        };
    }
}
