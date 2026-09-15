using System.Net;
using System.Net.Http.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Services;
using TrafficCounter.Api.Tests.Infrastructure;
using Xunit;

namespace TrafficCounter.Api.Tests.Api;

public sealed class SqliteAppFactory : AppWebApplicationFactory
{
    protected override bool Relational => true;
}

public sealed class ReliabilityTests(SqliteAppFactory factory) : IClassFixture<SqliteAppFactory>
{
    private async Task<(HttpClient Client, RoundResponse Round, CreateBetDto Bet)> Setup()
    {
        var client = factory.AuthenticatedClient("player");
        var round = (await client.GetFromJsonAsync<RoundResponse>($"/rounds/current?cameraId=test_{Guid.NewGuid():N}"))!;
        return (client, round, new CreateBetDto { TransactionId = Guid.NewGuid().ToString(),
            GameSessionId = "test-session", RoundId = round.RoundId, MarketId = round.Markets[0].MarketId,
            StakeAmount = 10, Currency = "BRL" });
    }

    private static async Task<HttpResponseMessage> PostWithRetry<T>(HttpClient client, string path, T payload)
    {
        for (var attempt = 0; ; attempt++)
        {
            var response = await client.PostAsJsonAsync(path, payload);
            if (response.StatusCode != HttpStatusCode.ServiceUnavailable || attempt >= 20) return response;
            response.Dispose();
            await Task.Delay(10 * (attempt + 1));
        }
    }

    [Fact]
    public async Task Visitor_and_worker_cannot_place_bets_or_access_administration()
    {
        using var visitor = factory.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.PostAsJsonAsync("/bets", new CreateBetDto())).StatusCode);
        visitor.DefaultRequestHeaders.Add("X-API-Key", AppWebApplicationFactory.WorkerKey);
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.GetAsync("/streams")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await visitor.PostAsJsonAsync("/internal/bets", new CreateBetDto())).StatusCode);
        using var player = factory.AuthenticatedClient("player");
        Assert.Equal(HttpStatusCode.Forbidden, (await player.GetAsync("/streams")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await player.PostAsJsonAsync($"/admin/rounds/{Guid.NewGuid()}/void", new { reason = "test" })).StatusCode);
    }

    [Fact]
    public async Task Login_and_cookie_writes_require_csrf()
    {
        using var visitor = factory.CreateClient();
        Assert.Equal(HttpStatusCode.BadRequest, (await visitor.PostAsJsonAsync("/auth/login", new { username = "player", password = AppWebApplicationFactory.Password })).StatusCode);
        using var player = factory.AuthenticatedClient("player");
        player.DefaultRequestHeaders.Remove("X-CSRF-Token");
        Assert.Equal(HttpStatusCode.BadRequest, (await player.PostAsJsonAsync("/bets", new CreateBetDto())).StatusCode);
    }

    [Fact]
    public async Task Player_identity_is_server_owned_and_history_is_private()
    {
        var (client, _, payload) = await Setup();
        payload.PlayerRef = "other"; payload.OperatorRef = "forged";
        var response = await client.PostAsJsonAsync("/bets", payload);
        response.EnsureSuccessStatusCode();
        var bet = (await response.Content.ReadFromJsonAsync<BetResponse>())!;
        Assert.Equal("player", bet.PlayerRef); Assert.Equal("local", bet.OperatorRef);
        using var other = factory.AuthenticatedClient("other");
        Assert.Equal(HttpStatusCode.NotFound, (await other.GetAsync($"/bets/{bet.Id}")).StatusCode);
        var history = await other.GetFromJsonAsync<BetPage>("/bets");
        Assert.DoesNotContain(history!.Items, item => item.Id == bet.Id);
        using var reloaded = factory.AuthenticatedClient("player");
        Assert.Equal(HttpStatusCode.OK, (await reloaded.GetAsync($"/bets/{bet.Id}")).StatusCode);
    }

    [Theory]
    [InlineData("0.001")]
    [InlineData("0")]
    [InlineData("-1")]
    [InlineData("10000.01")]
    public async Task Invalid_amount_is_rejected(string amount)
    {
        var (client, _, payload) = await Setup();
        payload.StakeAmount = decimal.Parse(amount, System.Globalization.CultureInfo.InvariantCulture);
        Assert.Equal(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync("/bets", payload)).StatusCode);
    }

    [Fact]
    public async Task Currency_and_reused_key_with_different_payload_are_rejected()
    {
        var (client, _, payload) = await Setup();
        payload.Currency = "USD";
        Assert.Equal(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync("/bets", payload)).StatusCode);
        payload.Currency = "BRL";
        (await client.PostAsJsonAsync("/bets", payload)).EnsureSuccessStatusCode();
        payload.StakeAmount = 11;
        Assert.Equal(HttpStatusCode.Conflict, (await client.PostAsJsonAsync("/bets", payload)).StatusCode);
    }

    [Fact]
    public async Task Concurrent_retries_create_one_bet_and_keys_are_scoped_to_player()
    {
        var (client, _, payload) = await Setup();
        var responses = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => PostWithRetry(client, "/bets", payload)));
        var ids = new List<string>();
        foreach (var response in responses)
        { response.EnsureSuccessStatusCode(); ids.Add((await response.Content.ReadFromJsonAsync<BetResponse>())!.Id); }
        Assert.Single(ids.Distinct());
        using var other = factory.AuthenticatedClient("other");
        var otherResponse = await other.PostAsJsonAsync("/bets", payload);
        otherResponse.EnsureSuccessStatusCode();
        Assert.NotEqual(ids[0], (await otherResponse.Content.ReadFromJsonAsync<BetResponse>())!.Id);
    }

    [Fact]
    public async Task Concurrent_events_and_duplicates_preserve_exact_count()
    {
        var (_, round, _) = await Setup();
        using var worker = factory.CreateClient();
        worker.DefaultRequestHeaders.Add("X-API-Key", AppWebApplicationFactory.WorkerKey);
        var events = Enumerable.Range(1, 12).Select(i => new RoundCountEventDto {
            CameraId = round.CameraId, RoundId = round.RoundId, TrackId = i.ToString(),
            EventHash = Guid.NewGuid().ToString(), CrossedAt = DateTime.UtcNow, VehicleType = "car" }).ToList();
        var responses = await Task.WhenAll(events.Concat(events).Select(e => PostWithRetry(worker, "/internal/round-count-event", e)));
        foreach (var response in responses) response.EnsureSuccessStatusCode();
        var updated = await worker.GetFromJsonAsync<RoundResponse>($"/rounds/{round.RoundId}");
        Assert.Equal(12, updated!.CurrentCount);
        var persisted = await worker.GetFromJsonAsync<List<CrossingEventResponse>>($"/rounds/{round.RoundId}/count-events");
        Assert.Equal(12, persisted!.Count);
    }

    [Fact]
    public async Task Failed_settlement_rolls_back_round_and_bets_then_recovers()
    {
        var (client, round, payload) = await Setup();
        (await client.PostAsJsonAsync("/bets", payload)).EnsureSuccessStatusCode();
        using var scope = factory.Services.CreateScope();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        await using var db = await dbFactory.CreateDbContextAsync();
        var entity = await db.Rounds.SingleAsync(r => r.RoundId == Guid.Parse(round.RoundId));
        entity.Status = RoundStatus.Settling; entity.EndsAt = DateTime.UtcNow.AddMinutes(-1);
        await db.SaveChangesAsync();
        await db.Database.ExecuteSqlRawAsync("CREATE TRIGGER reject_settlement BEFORE UPDATE ON Bets BEGIN SELECT RAISE(ABORT, 'injected failure'); END;");
        try
        {
            await Assert.ThrowsAsync<DbUpdateException>(() => scope.ServiceProvider.GetRequiredService<RoundService>().TickAsync());
            await db.Entry(entity).ReloadAsync();
            Assert.Equal(RoundStatus.Settling, entity.Status);
            Assert.Equal(BetStatus.Accepted, (await db.Bets.SingleAsync(b => b.RoundId == entity.RoundId)).Status);
        }
        finally { await db.Database.ExecuteSqlRawAsync("DROP TRIGGER reject_settlement;"); }
        await scope.ServiceProvider.GetRequiredService<RoundService>().TickAsync();
        await db.Entry(entity).ReloadAsync();
        Assert.Equal(RoundStatus.Settled, entity.Status);
        db.ChangeTracker.Clear();
        Assert.NotEqual(BetStatus.Accepted, (await db.Bets.SingleAsync(b => b.RoundId == entity.RoundId)).Status);
    }

    [Fact]
    public async Task Late_event_cannot_increment_replacement_round()
    {
        var (_, round, _) = await Setup();
        using var worker = factory.CreateClient();
        worker.DefaultRequestHeaders.Add("X-API-Key", AppWebApplicationFactory.WorkerKey);
        var occurredAt = DateTime.UtcNow;
        (await worker.PostAsJsonAsync($"/internal/rounds/{round.RoundId}/void", new { reason = "test" })).EnsureSuccessStatusCode();
        var result = await worker.PostAsJsonAsync("/internal/round-count-event", new RoundCountEventDto {
            CameraId = round.CameraId, RoundId = round.RoundId, CrossedAt = occurredAt,
            TrackId = "late", EventHash = Guid.NewGuid().ToString() });
        Assert.Equal(HttpStatusCode.Conflict, result.StatusCode);
        var next = await worker.GetFromJsonAsync<RoundResponse>($"/rounds/current?cameraId={round.CameraId}");
        Assert.Equal(0, next!.CurrentCount);
    }

    [Fact]
    public async Task Admin_can_record_an_append_only_recovery_decision()
    {
        const string eventId = "rejected-event-001";
        using var admin = factory.AuthenticatedClient();
        var response = await admin.PostAsJsonAsync($"/admin/recovery-events/{eventId}/decision", new {
            decision = "closed", reasonCode = "round_finalized", reason = "Rodada ja foi liquidada."
        });
        response.EnsureSuccessStatusCode();

        var decisions = await admin.GetFromJsonAsync<List<OperationalRecoveryDecision>>(
            $"/admin/recovery-decisions?eventId={eventId}");
        var decision = Assert.Single(decisions!);
        Assert.Equal("closed", decision.Decision);
        Assert.Equal("admin", decision.Actor);

        using var scope = factory.Services.CreateScope();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        await using var db = await dbFactory.CreateDbContextAsync();
        Assert.True(await db.AdministrativeAudits.AnyAsync(a => a.Target == "recovery:" + eventId &&
            a.Action == "recovery.decision" && a.Outcome == "closed"));
        var persisted = await db.OperationalRecoveryDecisions.SingleAsync(d => d.EventId == eventId);
        persisted.Decision = "acknowledged";
        await Assert.ThrowsAsync<InvalidOperationException>(() => db.SaveChangesAsync());
    }

    private sealed record BetPage(List<BetResponse> Items, int Total);
}
