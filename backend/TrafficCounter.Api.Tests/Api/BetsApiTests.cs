using System.Net;
using System.Net.Http.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Tests.Infrastructure;
using Xunit;

namespace TrafficCounter.Api.Tests.Api;

public class BetsApiTests : IClassFixture<AppWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly AppWebApplicationFactory _factory;

    public BetsApiTests(AppWebApplicationFactory factory)
    {
        _factory = factory;
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task CreateBet_accepts_valid_open_round_without_api_key()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_accept");

        Assert.NotNull(round);
        Assert.NotEmpty(round!.Markets);
        var market = round.Markets.First();

        var response = await _client.PostAsJsonAsync("/bets", new CreateBetDto
        {
            TransactionId = "tx-bet-accept-001",
            GameSessionId = "session-bet-001",
            RoundId = round.RoundId,
            MarketId = market.MarketId,
            StakeAmount = 10m,
            Currency = "brl",
        });

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var bet = await response.Content.ReadFromJsonAsync<BetResponse>();
        Assert.NotNull(bet);
        Assert.Equal("accepted", bet!.Status);
        Assert.Equal(round.RoundId, bet.RoundId);
        Assert.Equal(market.MarketId, bet.MarketId);
        Assert.Equal(10m, bet.StakeAmount);
        Assert.Equal("BRL", bet.Currency);
    }

    [Fact]
    public async Task CreateBet_returns_same_bet_for_duplicate_transaction_id()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_idempotent");

        Assert.NotNull(round);
        Assert.NotEmpty(round!.Markets);
        var market = round.Markets.First();
        var payload = new CreateBetDto
        {
            TransactionId = "tx-bet-idempotent-001",
            GameSessionId = "session-bet-idempotent",
            RoundId = round.RoundId,
            MarketId = market.MarketId,
            StakeAmount = 15m,
            Currency = "BRL",
        };

        var first = await _client.PostAsJsonAsync("/bets", payload);
        var second = await _client.PostAsJsonAsync("/bets", payload);

        first.EnsureSuccessStatusCode();
        second.EnsureSuccessStatusCode();

        var firstBet = await first.Content.ReadFromJsonAsync<BetResponse>();
        var secondBet = await second.Content.ReadFromJsonAsync<BetResponse>();

        Assert.NotNull(firstBet);
        Assert.NotNull(secondBet);
        Assert.Equal(firstBet!.Id, secondBet!.Id);
        Assert.Equal(firstBet.ProviderBetId, secondBet.ProviderBetId);
    }

    [Fact]
    public async Task CreateBet_returns_400_for_invalid_payload()
    {
        var response = await _client.PostAsJsonAsync("/bets", new CreateBetDto
        {
            TransactionId = "",
            GameSessionId = "",
            RoundId = "not-a-guid",
            MarketId = "not-a-guid",
            StakeAmount = 0m,
            Currency = "",
        });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task CreateBet_returns_409_after_bet_close()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_closed");

        Assert.NotNull(round);
        Assert.NotEmpty(round!.Markets);
        var market = round.Markets.First();

        using (var scope = _factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();

            var persisted = await db.Rounds.FirstAsync(r => r.RoundId == Guid.Parse(round.RoundId));
            persisted.BetCloseAt = DateTime.UtcNow.AddSeconds(-1);
            await db.SaveChangesAsync();
        }

        var response = await _client.PostAsJsonAsync("/bets", new CreateBetDto
        {
            TransactionId = "tx-bet-closed-001",
            GameSessionId = "session-bet-closed",
            RoundId = round.RoundId,
            MarketId = market.MarketId,
            StakeAmount = 20m,
            Currency = "BRL",
        });

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Theory]
    [InlineData("closing")]
    [InlineData("settling")]
    [InlineData("settled")]
    [InlineData("void")]
    public async Task CreateBet_returns_409_for_non_open_round_status(string targetStatus)
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>($"/rounds/current?cameraId=cam_bet_status_{targetStatus}");

        Assert.NotNull(round);
        Assert.NotEmpty(round!.Markets);
        var market = round.Markets.First();

        using var scope = _factory.Services.CreateScope();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        await using var db = await dbFactory.CreateDbContextAsync();

        var persisted = await db.Rounds.FirstAsync(r => r.RoundId == Guid.Parse(round.RoundId));
        persisted.Status = targetStatus switch
        {
            "closing" => RoundStatus.Closing,
            "settling" => RoundStatus.Settling,
            "settled" => RoundStatus.Settled,
            "void" => RoundStatus.Void,
            _ => persisted.Status,
        };
        if (persisted.Status == RoundStatus.Settled)
            persisted.SettledAt = DateTime.UtcNow;
        if (persisted.Status == RoundStatus.Void)
            persisted.VoidedAt = DateTime.UtcNow;

        await db.SaveChangesAsync();

        var response = await _client.PostAsJsonAsync("/bets", new CreateBetDto
        {
            TransactionId = $"tx-bet-status-{targetStatus}",
            GameSessionId = $"session-bet-status-{targetStatus}",
            RoundId = round.RoundId,
            MarketId = market.MarketId,
            StakeAmount = 8m,
            Currency = "BRL",
        });

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task CreateBet_returns_409_for_market_not_in_round()
    {
        var roundA = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_market_a");
        var roundB = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_market_b");

        Assert.NotNull(roundA);
        Assert.NotNull(roundB);
        Assert.NotEmpty(roundB!.Markets);
        var foreignMarket = roundB.Markets.First();

        var response = await _client.PostAsJsonAsync("/bets", new CreateBetDto
        {
            TransactionId = "tx-bet-foreign-market",
            GameSessionId = "session-bet-foreign-market",
            RoundId = roundA!.RoundId,
            MarketId = foreignMarket.MarketId,
            StakeAmount = 11m,
            Currency = "BRL",
        });

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task GetBetById_returns_created_bet()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_lookup");

        Assert.NotNull(round);
        Assert.NotEmpty(round!.Markets);
        var market = round.Markets.First();

        var createResponse = await _client.PostAsJsonAsync("/bets", new CreateBetDto
        {
            TransactionId = "tx-bet-lookup-001",
            GameSessionId = "session-bet-lookup",
            RoundId = round.RoundId,
            MarketId = market.MarketId,
            StakeAmount = 13m,
            Currency = "BRL",
        });

        createResponse.EnsureSuccessStatusCode();
        var createdBet = await createResponse.Content.ReadFromJsonAsync<BetResponse>();

        var fetchResponse = await _client.GetAsync($"/bets/{createdBet!.Id}");
        Assert.Equal(HttpStatusCode.OK, fetchResponse.StatusCode);
    }
}
