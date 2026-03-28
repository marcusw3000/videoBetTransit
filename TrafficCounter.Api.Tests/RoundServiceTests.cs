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
