using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
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

public sealed class RoundIntegrityTests(SqliteAppFactory factory) : IClassFixture<SqliteAppFactory>
{
    private IDbContextFactory<AppDbContext> Database => factory.Services.GetRequiredService<IDbContextFactory<AppDbContext>>();
    private HttpClient Worker()
    {
        var client = factory.CreateClient();
        client.DefaultRequestHeaders.Add("X-API-Key", AppWebApplicationFactory.WorkerKey);
        return client;
    }
    private static OperationalConfigurationDto Configuration() => new() {
        CameraId = "freeze_" + Guid.NewGuid().ToString("N"), StreamProfileId = "profile-v1",
        SourceUrl = "https://camera.example/feed?secret=never-store-this",
        Roi = new() { ["x"] = 0, ["y"] = 0, ["w"] = 640, ["h"] = 360 },
        Line = new() { ["x1"] = 0, ["y1"] = 180, ["x2"] = 640, ["y2"] = 180 }, CountDirection = "down"
    };
    private async Task<(HttpClient Worker, OperationalConfigurationDto Config, RoundResponse Round, string Version)> Start()
    {
        var worker = Worker(); var config = Configuration();
        var registered = await worker.PostAsJsonAsync("/internal/camera-config", config);
        registered.EnsureSuccessStatusCode();
        var version = (await registered.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("configurationVersion").GetString()!;
        (await worker.PostAsJsonAsync("/internal/rounds/profile-activated", new {
            config.CameraId, config.StreamProfileId, phase = "ready"
        })).EnsureSuccessStatusCode();
        var round = (await worker.GetFromJsonAsync<RoundResponse>($"/rounds/current?cameraId={config.CameraId}"))!;
        return (worker, config, round, version);
    }

    [Fact]
    public async Task Snapshot_is_historical_and_rules_match_market_boundaries()
    {
        var (_, config, response, _) = await Start();
        await using var db = await Database.CreateDbContextAsync();
        var round = await db.Rounds.Include(r => r.Markets).SingleAsync(r => r.RoundId == Guid.Parse(response.RoundId));
        Assert.DoesNotContain("never-store-this", round.OperationalSnapshotJson!);
        using var rules = JsonDocument.Parse(round.RulesSnapshotJson!);
        Assert.Equal((round.BetCloseAt - round.CreatedAt).TotalSeconds, rules.RootElement.GetProperty("betWindowSeconds").GetInt32());
        Assert.Equal((round.EndsAt - round.BetCloseAt).TotalSeconds, rules.RootElement.GetProperty("countAfterBetCloseSeconds").GetInt32());
        foreach (var market in round.Markets)
        {
            var bet = new Bet { MarketType = market.MarketType, Threshold = market.Threshold,
                Min = market.Min, Max = market.Max, TargetValue = market.TargetValue };
            if (market.MarketType == "under") {
                Assert.False(BetService.EvaluateBet(bet, market.Threshold!.Value));
                Assert.True(BetService.EvaluateBet(bet, market.Threshold.Value - 1));
            }
            if (market.MarketType == "over") Assert.True(BetService.EvaluateBet(bet, market.Threshold!.Value));
            if (market.MarketType == "range") {
                Assert.True(BetService.EvaluateBet(bet, market.Min!.Value));
                Assert.True(BetService.EvaluateBet(bet, market.Max!.Value));
            }
            if (market.MarketType == "exact") {
                Assert.True(BetService.EvaluateBet(bet, market.TargetValue!.Value));
                Assert.False(BetService.EvaluateBet(bet, market.TargetValue.Value + 1));
            }
        }
        var state = await db.CameraRoundStates.SingleAsync(s => s.CameraId == config.CameraId);
        state.OperationalConfigurationJson = "{}";
        await db.SaveChangesAsync();
        Assert.NotEqual(state.OperationalConfigurationJson, round.OperationalSnapshotJson);
        round.OperationalSnapshotJson = "{}";
        await Assert.ThrowsAsync<InvalidOperationException>(() => db.SaveChangesAsync());
    }

    [Theory]
    [InlineData("left")]
    [InlineData("right")]
    public void Horizontal_configuration_directions_are_valid(string direction)
    {
        var config = Configuration();
        config.CountDirection = direction;
        using var snapshot = JsonDocument.Parse(config.ToSnapshot());
        Assert.Equal(direction, snapshot.RootElement.GetProperty("countDirection").GetString());
    }

    [Theory]
    [InlineData(RoundStatus.Open)]
    [InlineData(RoundStatus.Closing)]
    [InlineData(RoundStatus.Settling)]
    public async Task Manual_configuration_changes_are_rejected_and_audited(RoundStatus status)
    {
        var (worker, config, round, _) = await Start();
        await using (var db = await Database.CreateDbContextAsync()) {
            var entity = await db.Rounds.FindAsync(Guid.Parse(round.RoundId)); entity!.Status = status; await db.SaveChangesAsync();
        }
        config.Line["y1"] = 181;
        Assert.Equal(HttpStatusCode.Conflict, (await worker.PostAsJsonAsync("/internal/camera-config", config)).StatusCode);
        using var admin = factory.AuthenticatedClient();
        var audit = await admin.GetFromJsonAsync<List<AdministrativeAudit>>($"/admin/audit?target={config.CameraId}");
        Assert.Contains(audit!, a => a.Actor == "worker" && a.Outcome == "blocked" && a.ReasonCode == "http_409");
    }

    [Fact]
    public async Task Boundary_preparation_preserves_old_snapshot_and_accepts_only_its_original_events()
    {
        var (worker, config, round, version) = await Start();
        string original;
        await using (var db = await Database.CreateDbContextAsync()) {
            var entity = await db.Rounds.FindAsync(Guid.Parse(round.RoundId));
            original = entity!.OperationalSnapshotJson!; entity.Status = RoundStatus.Settling; await db.SaveChangesAsync();
        }
        config.Line["y1"] = 190; config.AllowSettling = true;
        var change = await worker.PostAsJsonAsync("/internal/camera-config", config); change.EnsureSuccessStatusCode();
        var nextVersion = (await change.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("configurationVersion").GetString();
        var evt = new RoundCountEventDto { CameraId = config.CameraId, RoundId = round.RoundId,
            StreamProfileId = config.StreamProfileId, TrackId = "10", VehicleType = "car",
            CrossedAt = round.CreatedAt.UtcDateTime.AddMilliseconds(10), EventHash = Guid.NewGuid().ToString(), ConfigurationVersion = nextVersion };
        Assert.Equal(HttpStatusCode.Conflict, (await worker.PostAsJsonAsync("/internal/round-count-event", evt)).StatusCode);
        evt.ConfigurationVersion = version;
        (await worker.PostAsJsonAsync("/internal/round-count-event", evt)).EnsureSuccessStatusCode();
        await using var verify = await Database.CreateDbContextAsync();
        var persisted = await verify.Rounds.FindAsync(Guid.Parse(round.RoundId));
        Assert.Equal(original, persisted!.OperationalSnapshotJson); Assert.Equal(1, persisted.CurrentCount);
        Assert.NotEqual(original, (await verify.CameraRoundStates.SingleAsync(s => s.CameraId == config.CameraId)).OperationalConfigurationJson);
    }

    [Fact]
    public async Task Void_records_actor_code_and_bet_result_atomically_and_audit_is_private()
    {
        var (_, _, round, _) = await Start();
        using var player = factory.AuthenticatedClient("player");
        var placed = await player.PostAsJsonAsync("/bets", new CreateBetDto {
            TransactionId = Guid.NewGuid().ToString(), GameSessionId = "test", RoundId = round.RoundId,
            MarketId = round.Markets[0].MarketId, Currency = "BRL", StakeAmount = 1 });
        placed.EnsureSuccessStatusCode();
        Assert.Equal(HttpStatusCode.Forbidden, (await player.GetAsync("/admin/audit")).StatusCode);
        Assert.Equal(HttpStatusCode.Forbidden, (await player.GetAsync($"/admin/rounds/{round.RoundId}/configuration")).StatusCode);
        using var admin = factory.AuthenticatedClient();
        Assert.Equal(HttpStatusCode.BadRequest, (await admin.PostAsJsonAsync($"/admin/rounds/{round.RoundId}/void",
            new { reason = "test", reasonCode = "invented" })).StatusCode);
        (await admin.PostAsJsonAsync($"/admin/rounds/{round.RoundId}/void", new {
            reason = "Transmissao interrompida durante a rodada", reasonCode = "stream_loss" })).EnsureSuccessStatusCode();
        await using var db = await Database.CreateDbContextAsync();
        var id = Guid.Parse(round.RoundId);
        Assert.Equal("stream_loss", (await db.Rounds.FindAsync(id))!.VoidReasonCode);
        Assert.Equal(BetStatus.Void, (await db.Bets.SingleAsync(b => b.RoundId == id)).Status);
        var audit = await db.AdministrativeAudits.SingleAsync(a => a.Target == round.RoundId && a.Action == "round.void");
        Assert.Equal("admin", audit.Actor); Assert.Equal("stream_loss", audit.ReasonCode);
        audit.Reason = "changed";
        await Assert.ThrowsAsync<InvalidOperationException>(() => db.SaveChangesAsync());
    }

    [Fact]
    public async Task Failed_void_rolls_back_round_bet_and_decision_audit()
    {
        var (_, _, round, _) = await Start();
        using var player = factory.AuthenticatedClient("player");
        (await player.PostAsJsonAsync("/bets", new CreateBetDto { TransactionId = Guid.NewGuid().ToString(),
            GameSessionId = "rollback", RoundId = round.RoundId, MarketId = round.Markets[0].MarketId,
            Currency = "BRL", StakeAmount = 1 })).EnsureSuccessStatusCode();
        await using var db = await Database.CreateDbContextAsync();
        await db.Database.ExecuteSqlRawAsync("CREATE TRIGGER reject_audited_void BEFORE UPDATE ON Bets BEGIN SELECT RAISE(ABORT, 'injected failure'); END;");
        try {
            using var scope = factory.Services.CreateScope();
            await Assert.ThrowsAsync<DbUpdateException>(() => scope.ServiceProvider.GetRequiredService<RoundService>()
                .VoidRoundAsync(Guid.Parse(round.RoundId), "rollback test", "manual_intervention", "admin"));
        } finally { await db.Database.ExecuteSqlRawAsync("DROP TRIGGER reject_audited_void;"); }
        var id = Guid.Parse(round.RoundId);
        Assert.Equal(RoundStatus.Open, (await db.Rounds.FindAsync(id))!.Status);
        Assert.Equal(BetStatus.Accepted, (await db.Bets.SingleAsync(b => b.RoundId == id)).Status);
        Assert.False(await db.AdministrativeAudits.AnyAsync(a => a.Target == round.RoundId && a.Action == "round.void"));
    }

    [Fact]
    public async Task Legacy_snapshot_absence_is_explicit_and_unauthorized_attempt_is_logged()
    {
        using var visitor = factory.CreateClient();
        var round = (await visitor.GetFromJsonAsync<RoundResponse>($"/rounds/current?cameraId=legacy_{Guid.NewGuid():N}"))!;
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.PostAsJsonAsync($"/admin/rounds/{round.RoundId}/void", new { reason = "test" })).StatusCode);
        using var admin = factory.AuthenticatedClient();
        var snapshot = await admin.GetFromJsonAsync<JsonElement>($"/admin/rounds/{round.RoundId}/configuration");
        Assert.False(snapshot.GetProperty("available").GetBoolean());
        var audit = await admin.GetFromJsonAsync<List<AdministrativeAudit>>($"/admin/audit?target={round.RoundId}");
        Assert.Contains(audit!, a => a.Actor == "anonymous" && a.Outcome == "blocked");
    }

    [Fact]
    public async Task Administrative_request_audit_is_case_insensitive()
    {
        using var visitor = factory.CreateClient();
        var path = $"/ADMIN/rounds/{Guid.NewGuid()}/void";
        Assert.Equal(HttpStatusCode.Unauthorized, (await visitor.PostAsJsonAsync(path, new { reason = "test" })).StatusCode);
        await using var db = await Database.CreateDbContextAsync();
        Assert.True(await db.AdministrativeAudits.AnyAsync(a => a.Action == "request:POST:" + path && a.Outcome == "blocked"));
    }
}

public sealed class StrictConfigurationFactory : AppWebApplicationFactory
{
    protected override bool Relational => true;
    protected override bool RequireOperationalSnapshot => true;
}

public sealed class StrictConfigurationTests(StrictConfigurationFactory factory) : IClassFixture<StrictConfigurationFactory>
{
    [Fact]
    public async Task New_camera_cannot_open_round_until_worker_registers_configuration()
    {
        using var client = factory.CreateClient();
        var camera = "strict_" + Guid.NewGuid().ToString("N");
        Assert.Equal(HttpStatusCode.NotFound, (await client.GetAsync($"/rounds/current?cameraId={camera}")).StatusCode);
        client.DefaultRequestHeaders.Add("X-API-Key", AppWebApplicationFactory.WorkerKey);
        (await client.PostAsJsonAsync("/internal/camera-config", new OperationalConfigurationDto {
            CameraId = camera, StreamProfileId = "profile", SourceUrl = "https://camera.example/feed", CountDirection = "any",
            Roi = new() { ["x"] = 0, ["y"] = 0, ["w"] = 640, ["h"] = 360 },
            Line = new() { ["x1"] = 0, ["y1"] = 180, ["x2"] = 640, ["y2"] = 180 }
        })).EnsureSuccessStatusCode();
        Assert.Equal(HttpStatusCode.NotFound, (await client.GetAsync($"/rounds/current?cameraId={camera}")).StatusCode);
        (await client.PostAsJsonAsync("/internal/rounds/profile-activated", new { cameraId = camera, streamProfileId = "profile", phase = "ready" })).EnsureSuccessStatusCode();
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync($"/rounds/current?cameraId={camera}")).StatusCode);
    }
}
