using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Services;
using Xunit;

namespace TrafficCounter.Api.Tests;

public class RoundServiceTests
{
    [Fact]
    public void Settle_ReturnsNull_WhenRoundWasAlreadySettled()
    {
        var service = new RoundService(CreateFactory());
        var firstRound = service.GetCurrent();

        var newRound = service.Settle(firstRound.Id);
        var secondAttempt = service.Settle(firstRound.Id);

        Assert.NotNull(newRound);
        Assert.Null(secondAttempt);
    }

    [Fact]
    public void GetCurrent_UsesV1Markets_AndTurboTwoMinuteRounds()
    {
        var service = new RoundService(CreateFactory());

        var round = service.GetCurrent();

        Assert.Equal(RoundService.StatusOpen, round.Status);
        Assert.Equal(4, round.Ranges.Count);
        Assert.Contains(round.Ranges, market => market.MarketType == "under" && market.TargetValue == 20);
        Assert.Contains(round.Ranges, market => market.MarketType == "range" && market.Min == 11 && market.Max == 20);
        Assert.Contains(round.Ranges, market => market.MarketType == "over" && market.TargetValue == 20);
        Assert.Contains(round.Ranges, market => market.MarketType == "exact" && market.TargetValue == 20 && market.Odds == 18.0);
        Assert.InRange((round.BetCloseAt - round.CreatedAt).TotalSeconds, 89, 91);
        Assert.InRange((round.EndsAt - round.CreatedAt).TotalSeconds, 119, 121);
    }

    [Fact]
    public void Settle_ComputesWinningMarkets()
    {
        var service = new RoundService(CreateFactory());
        var round = service.GetCurrent();

        service.SyncCount(new TrafficCounter.Api.Models.CountEvent
        {
            CameraId = "cam-1",
            RoundId = round.Id,
            TrackId = "trk-1",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow.ToString("O"),
            SnapshotUrl = "",
            TotalCount = 20,
        });

        service.Settle(round.Id);
        var settled = service.GetHistory().Single(x => x.Id == round.Id);

        Assert.Contains(settled.Ranges, market => market.MarketType == "range" && market.IsWinner == true);
        Assert.Contains(settled.Ranges, market => market.MarketType == "exact" && market.IsWinner == true);
        Assert.Contains(settled.Ranges, market => market.MarketType == "under" && market.IsWinner == false);
        Assert.Contains(settled.Ranges, market => market.MarketType == "over" && market.IsWinner == false);
        Assert.NotNull(settled.SettledAt);
        Assert.Null(settled.VoidedAt);
    }

    [Fact]
    public void GetCurrent_MovesRoundToClosing_WhenBetCloseIsReached()
    {
        var factory = CreateFactory();
        var service = new RoundService(factory);
        var round = service.GetCurrent();

        using (var db = factory.CreateDbContext())
        {
            var tracked = db.Rounds.Single(x => x.Id == round.Id);
            tracked.BetCloseAt = DateTime.UtcNow.AddSeconds(-1);
            tracked.EndsAt = DateTime.UtcNow.AddSeconds(30);
            db.SaveChanges();
        }

        var updated = service.GetCurrent();

        Assert.Equal(RoundService.StatusClosing, updated.Status);
    }

    [Fact]
    public void GetCurrent_FinalizesExpiredRound_AndStartsNewOpenRound()
    {
        var factory = CreateFactory();
        var service = new RoundService(factory);
        var round = service.GetCurrent();

        using (var db = factory.CreateDbContext())
        {
            var tracked = db.Rounds.Single(x => x.Id == round.Id);
            tracked.BetCloseAt = DateTime.UtcNow.AddSeconds(-20);
            tracked.EndsAt = DateTime.UtcNow.AddSeconds(-1);
            db.SaveChanges();
        }

        var updated = service.GetCurrent();

        Assert.Equal(RoundService.StatusOpen, updated.Status);
        Assert.NotEqual(round.Id, updated.Id);
    }

    [Fact]
    public void SyncCount_IgnoresEventFromPreviousRound_AfterRollover()
    {
        var factory = CreateFactory();
        var service = new RoundService(factory);
        var originalRound = service.GetCurrent();

        using (var db = factory.CreateDbContext())
        {
            var tracked = db.Rounds.Single(x => x.Id == originalRound.Id);
            tracked.BetCloseAt = DateTime.UtcNow.AddSeconds(-20);
            tracked.EndsAt = DateTime.UtcNow.AddSeconds(-1);
            db.SaveChanges();
        }

        var current = service.SyncCount(new TrafficCounter.Api.Models.CountEvent
        {
            CameraId = "cam-1",
            RoundId = originalRound.Id,
            TrackId = "trk-late",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow.ToString("O"),
            SnapshotUrl = "",
            TotalCount = 99,
        });

        Assert.NotEqual(originalRound.Id, current.Id);
        Assert.Equal(0, current.CurrentCount);

        using var verifyDb = factory.CreateDbContext();
        var lateEventPersisted = verifyDb.CountEvents.Any(x => x.TrackId == "trk-late");
        Assert.False(lateEventPersisted);
    }

    [Fact]
    public void Void_MarksRoundAsVoid_WithReason_AndStartsNewRound()
    {
        var service = new RoundService(CreateFactory());
        var round = service.GetCurrent();

        var nextRound = service.Void(round.Id, "Camera offline");
        var history = service.GetHistory();
        var voided = history.Single(x => x.Id == round.Id);

        Assert.NotNull(nextRound);
        Assert.Equal(RoundService.StatusOpen, nextRound.Status);
        Assert.Equal(RoundService.StatusVoid, voided.Status);
        Assert.Equal("Camera offline", voided.VoidReason);
        Assert.NotNull(voided.VoidedAt);
        Assert.Null(voided.SettledAt);
        Assert.All(voided.Ranges, market => Assert.Null(market.IsWinner));
    }

    private static IDbContextFactory<TrafficCounterDbContext> CreateFactory()
    {
        var options = new DbContextOptionsBuilder<TrafficCounterDbContext>()
            .UseInMemoryDatabase($"round-service-tests-{Guid.NewGuid()}")
            .Options;

        return new TestDbContextFactory(options);
    }

    private sealed class TestDbContextFactory : IDbContextFactory<TrafficCounterDbContext>
    {
        private readonly DbContextOptions<TrafficCounterDbContext> _options;

        public TestDbContextFactory(DbContextOptions<TrafficCounterDbContext> options)
        {
            _options = options;
        }

        public TrafficCounterDbContext CreateDbContext()
        {
            return new TrafficCounterDbContext(_options);
        }
    }
}
