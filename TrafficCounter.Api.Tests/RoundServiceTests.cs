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
    public void GetCurrent_UsesV1Markets_AndSixtySecondRounds()
    {
        var service = new RoundService(CreateFactory());

        var round = service.GetCurrent();

        Assert.Equal(RoundService.StatusOpen, round.Status);
        Assert.Equal(4, round.Ranges.Count);
        Assert.Contains(round.Ranges, market => market.MarketType == "under" && market.TargetValue == 20);
        Assert.Contains(round.Ranges, market => market.MarketType == "range" && market.Min == 11 && market.Max == 20);
        Assert.Contains(round.Ranges, market => market.MarketType == "over" && market.TargetValue == 20);
        Assert.Contains(round.Ranges, market => market.MarketType == "exact" && market.TargetValue == 20 && market.Odds == 18.0);
        Assert.InRange((round.BetCloseAt - round.CreatedAt).TotalSeconds, 49, 51);
        Assert.InRange((round.EndsAt - round.CreatedAt).TotalSeconds, 59, 61);
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
