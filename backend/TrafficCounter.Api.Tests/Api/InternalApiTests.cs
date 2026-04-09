using System.Net;
using System.Net.Http.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Requests;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Services;
using TrafficCounter.Api.Tests.Infrastructure;
using Xunit;

namespace TrafficCounter.Api.Tests.Api;

public class InternalApiTests : IClassFixture<AppWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly AppWebApplicationFactory _factory;

    public InternalApiTests(AppWebApplicationFactory factory)
    {
        _factory = factory;
        _client = factory.CreateClient();
        _client.DefaultRequestHeaders.Add("X-API-Key", "CHANGE_ME");

        using var scope = _factory.Services.CreateScope();
        scope.ServiceProvider.GetRequiredService<FakeRandomSource>().Reset();
    }

    [Fact]
    public async Task CrossingEvent_without_api_key_returns_401()
    {
        var clientNoKey = _factory.CreateClient(); // no API key
        var response = await clientNoKey.PostAsJsonAsync("/internal/crossing-events", new CrossingEventInboundDto());
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task CrossingEvent_for_unknown_session_returns_409()
    {
        var dto = new CrossingEventInboundDto
        {
            SessionId = Guid.NewGuid().ToString(),
            TimestampUtc = DateTime.UtcNow,
            TrackId = 1,
            ObjectClass = "car",
            Direction = "down_to_up",
            LineId = "main",
            Confidence = 0.9,
            FrameNumber = 100,
            EventHash = "abc",
        };

        var response = await _client.PostAsJsonAsync("/internal/crossing-events", dto);
        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task HealthReport_without_api_key_returns_401()
    {
        var clientNoKey = _factory.CreateClient(); // no API key
        var response = await clientNoKey.PostAsJsonAsync("/internal/health-report", new HealthReportDto());
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task HealthReport_for_unknown_session_returns_404()
    {
        var dto = new HealthReportDto
        {
            SessionId = Guid.NewGuid().ToString(),
            FpsIn = 25,
            FpsOut = 24,
        };

        var response = await _client.PostAsJsonAsync("/internal/health-report", dto);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task RoundCountEvent_creates_and_increments_round_for_camera()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_round_count_smoke",
            TrackId = "track-1",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        var countResponse = await _client.PostAsJsonAsync("/internal/round-count-event", dto);
        countResponse.EnsureSuccessStatusCode();

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_round_count_smoke");

        Assert.NotNull(round);
        Assert.Equal("cam_round_count_smoke", round!.CameraId);
        Assert.Contains("cam_round_count_smoke", round.CameraIds);
        Assert.Equal(1, round.CurrentCount);
        Assert.Equal("open", round.Status);
    }

    [Fact]
    public async Task RoundCountEvent_persists_crossing_event_for_round()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_events",
            TrackId = "42",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        var response = await _client.PostAsJsonAsync("/internal/round-count-event", dto);
        response.EnsureSuccessStatusCode();

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_events");
        Assert.NotNull(round);

        var events = await _client.GetFromJsonAsync<List<CrossingEventResponse>>($"/rounds/{round!.RoundId}/count-events");

        Assert.NotNull(events);
        Assert.Single(events!);
        Assert.Equal(Guid.Parse(round.RoundId), events[0].RoundId);
        Assert.Equal(42, events[0].TrackId);
        Assert.Equal("car", events[0].ObjectClass);
    }

    [Fact]
    public async Task RoundLifecycle_persists_round_events()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_round_events",
            TrackId = "7",
            VehicleType = "truck",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        var response = await _client.PostAsJsonAsync("/internal/round-count-event", dto);
        response.EnsureSuccessStatusCode();

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_round_events");
        Assert.NotNull(round);

        using var scope = _factory.Services.CreateScope();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        await using var db = await dbFactory.CreateDbContextAsync();

        var persistedEvents = db.RoundEvents
            .Where(e => e.RoundId == Guid.Parse(round!.RoundId))
            .OrderBy(e => e.TimestampUtc)
            .ToList();

        Assert.NotEmpty(persistedEvents);
        Assert.Contains(persistedEvents, e => e.EventType == "opened" && e.RoundStatus == "open");
    }

    [Fact]
    public async Task RoundCountEvent_uses_explicit_round_id_when_present()
    {
        var firstEvent = new RoundCountEventDto
        {
            CameraId = "cam_explicit_round",
            TrackId = "11",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        var firstResponse = await _client.PostAsJsonAsync("/internal/round-count-event", firstEvent);
        firstResponse.EnsureSuccessStatusCode();

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_explicit_round");
        Assert.NotNull(round);

        var secondEvent = new RoundCountEventDto
        {
            CameraId = "cam_explicit_round",
            RoundId = round!.RoundId,
            TrackId = "12",
            VehicleType = "bus",
            CrossedAt = DateTime.UtcNow.AddSeconds(1),
            SnapshotUrl = "snapshots/test-bus.jpg",
            TotalCount = 2,
        };

        var secondResponse = await _client.PostAsJsonAsync("/internal/round-count-event", secondEvent);
        secondResponse.EnsureSuccessStatusCode();

        var events = await _client.GetFromJsonAsync<List<CrossingEventResponse>>($"/rounds/{round.RoundId}/count-events");
        Assert.NotNull(events);
        Assert.Equal(2, events!.Count);
        Assert.Contains(events, e => e.TrackId == 12 && e.SnapshotUrl == "snapshots/test-bus.jpg");
    }

    [Fact]
    public async Task RoundCountEvent_ignores_explicit_round_id_from_other_camera()
    {
        var seedCameraOne = new RoundCountEventDto
        {
            CameraId = "cam_001",
            TrackId = "101",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };
        var seedCameraTwo = new RoundCountEventDto
        {
            CameraId = "cam_002",
            TrackId = "201",
            VehicleType = "bus",
            CrossedAt = DateTime.UtcNow.AddSeconds(1),
            TotalCount = 1,
        };

        (await _client.PostAsJsonAsync("/internal/round-count-event", seedCameraOne)).EnsureSuccessStatusCode();
        (await _client.PostAsJsonAsync("/internal/round-count-event", seedCameraTwo)).EnsureSuccessStatusCode();

        var cameraOneRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_001");
        var cameraTwoRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_002");

        Assert.NotNull(cameraOneRound);
        Assert.NotNull(cameraTwoRound);
        Assert.NotEqual(cameraOneRound!.RoundId, cameraTwoRound!.RoundId);

        var conflictingEvent = new RoundCountEventDto
        {
            CameraId = "cam_001",
            RoundId = cameraTwoRound.RoundId,
            TrackId = "102",
            VehicleType = "truck",
            CrossedAt = DateTime.UtcNow.AddSeconds(2),
            TotalCount = 2,
        };

        (await _client.PostAsJsonAsync("/internal/round-count-event", conflictingEvent)).EnsureSuccessStatusCode();

        var updatedCameraOneRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_001");
        var updatedCameraTwoRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_002");

        Assert.NotNull(updatedCameraOneRound);
        Assert.NotNull(updatedCameraTwoRound);
        Assert.Equal(2, updatedCameraOneRound!.CurrentCount);
        Assert.Equal(1, updatedCameraTwoRound!.CurrentCount);

        var cameraOneEvents = await _client.GetFromJsonAsync<List<CrossingEventResponse>>($"/rounds/{updatedCameraOneRound.RoundId}/count-events");
        Assert.NotNull(cameraOneEvents);
        Assert.Contains(cameraOneEvents!, e => e.TrackId == 102);
    }

    [Fact]
    public async Task RoundCountEvent_is_idempotent_for_duplicate_event_hash()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_idempotent",
            RoundId = null,
            TrackId = "500",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            EventHash = "event-hash-idempotent-001",
            CountBefore = 0,
            CountAfter = 1,
            TotalCount = 1,
        };

        (await _client.PostAsJsonAsync("/internal/round-count-event", dto)).EnsureSuccessStatusCode();
        (await _client.PostAsJsonAsync("/internal/round-count-event", dto)).EnsureSuccessStatusCode();

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_idempotent");
        Assert.NotNull(round);
        Assert.Equal(1, round!.CurrentCount);

        var events = await _client.GetFromJsonAsync<List<CrossingEventResponse>>($"/rounds/{round.RoundId}/count-events");
        Assert.NotNull(events);
        Assert.Single(events!);
        Assert.Equal("event-hash-idempotent-001", events[0].EventHash);
    }

    [Fact]
    public async Task GetCurrentRound_creates_round_for_requested_camera()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_001");

        Assert.NotNull(round);
        Assert.Equal("cam_001", round!.CameraId);
        Assert.Equal("normal", round.RoundMode);
        Assert.Equal("open", round.Status);
        Assert.NotEmpty(round.RoundId);
    }

    [Fact]
    public async Task RoundResponse_exposes_normal_mode_by_default()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_round_mode_default",
            TrackId = "10",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        (await _client.PostAsJsonAsync("/internal/round-count-event", dto)).EnsureSuccessStatusCode();

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_round_mode_default");

        Assert.NotNull(round);
        Assert.Equal("normal", round!.RoundMode);
        Assert.Equal("Rodada Normal", round.DisplayName);
        Assert.Equal(180, (int)Math.Round((round.EndsAt - round.CreatedAt).TotalSeconds));
        Assert.Equal(70, (int)Math.Round((round.BetCloseAt - round.CreatedAt).TotalSeconds));
    }

    [Fact]
    public async Task Turbo_round_is_not_selected_before_warmup_rounds()
    {
        using var scope = _factory.Services.CreateScope();
        scope.ServiceProvider.GetRequiredService<FakeRandomSource>().Enqueue(0.0);

        await _client.PostAsJsonAsync("/internal/rounds/profile-activated", new StreamProfileActivatedDto
        {
            CameraId = "cam_turbo_warmup",
            StreamProfileId = "profile-a",
        });

        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        await roundService.EnsureActiveRoundAsync("cam_turbo_warmup");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_turbo_warmup");

        Assert.NotNull(round);
        Assert.Equal("normal", round!.RoundMode);
    }

    [Fact]
    public async Task Turbo_round_is_selected_after_warmup_when_probability_hits()
    {
        using var scope = _factory.Services.CreateScope();
        var random = scope.ServiceProvider.GetRequiredService<FakeRandomSource>();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        (await _client.PostAsJsonAsync("/internal/rounds/profile-activated", new StreamProfileActivatedDto
        {
            CameraId = "cam_turbo_enabled",
            StreamProfileId = "profile-a",
        })).EnsureSuccessStatusCode();

        for (var index = 0; index < 5; index++)
        {
            await roundService.EnsureActiveRoundAsync("cam_turbo_enabled");
            await ForceSettleCurrentRoundAsync(dbFactory, "cam_turbo_enabled");
        }

        random.Enqueue(0.0);
        await roundService.EnsureActiveRoundAsync("cam_turbo_enabled");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_turbo_enabled");

        Assert.NotNull(round);
        Assert.Equal("turbo", round!.RoundMode);
        Assert.Equal("Rodada Turbo", round.DisplayName);
        Assert.Equal(120, (int)Math.Round((round.EndsAt - round.CreatedAt).TotalSeconds));
        Assert.Equal(30, (int)Math.Round((round.BetCloseAt - round.CreatedAt).TotalSeconds));
    }

    [Fact]
    public async Task Stream_profile_change_resets_turbo_warmup()
    {
        using var scope = _factory.Services.CreateScope();
        var random = scope.ServiceProvider.GetRequiredService<FakeRandomSource>();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        (await _client.PostAsJsonAsync("/internal/rounds/profile-activated", new StreamProfileActivatedDto
        {
            CameraId = "cam_turbo_reset",
            StreamProfileId = "profile-a",
        })).EnsureSuccessStatusCode();

        for (var index = 0; index < 5; index++)
        {
            await roundService.EnsureActiveRoundAsync("cam_turbo_reset");
            await ForceSettleCurrentRoundAsync(dbFactory, "cam_turbo_reset");
        }

        random.Enqueue(0.0);
        await roundService.EnsureActiveRoundAsync("cam_turbo_reset");
        await ForceSettleCurrentRoundAsync(dbFactory, "cam_turbo_reset");

        (await _client.PostAsJsonAsync("/internal/rounds/profile-activated", new StreamProfileActivatedDto
        {
            CameraId = "cam_turbo_reset",
            StreamProfileId = "profile-b",
        })).EnsureSuccessStatusCode();

        random.Enqueue(0.0);
        await roundService.EnsureActiveRoundAsync("cam_turbo_reset");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_turbo_reset");

        Assert.NotNull(round);
        Assert.Equal("normal", round!.RoundMode);
    }

    [Fact]
    public async Task RoundLock_returns_locked_when_camera_has_active_round()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_lock_round");
        Assert.NotNull(round);

        var response = await _client.GetAsync("/internal/cameras/cam_lock_round/round-lock");
        response.EnsureSuccessStatusCode();

        var payload = await response.Content.ReadFromJsonAsync<RoundLockResponse>();
        Assert.NotNull(payload);
        Assert.True(payload!.IsLocked);
        Assert.Equal("cam_lock_round", payload.CameraId);
    }

    [Fact]
    public async Task ValidateCameraConfigChange_returns_conflict_when_camera_has_active_round()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_lock_config");
        Assert.NotNull(round);

        var response = await _client.PostAsJsonAsync("/internal/camera-config/validate-change", new CameraConfigChangeDto
        {
            CameraId = "cam_lock_config",
        });

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task ValidateCameraConfigChange_allows_camera_without_active_round()
    {
        var response = await _client.PostAsJsonAsync("/internal/camera-config/validate-change", new CameraConfigChangeDto
        {
            CameraId = "cam_unlock_config",
        });

        response.EnsureSuccessStatusCode();
    }

    [Fact]
    public async Task NotifyStreamProfileActivated_returns_conflict_when_camera_has_active_round()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_lock_profile");
        Assert.NotNull(round);

        var response = await _client.PostAsJsonAsync("/internal/rounds/profile-activated", new StreamProfileActivatedDto
        {
            CameraId = "cam_lock_profile",
            StreamProfileId = "profile-z",
        });

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task GetRoundById_returns_requested_round()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_round_lookup",
            TrackId = "901",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        (await _client.PostAsJsonAsync("/internal/round-count-event", dto)).EnsureSuccessStatusCode();

        var currentRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_round_lookup");
        Assert.NotNull(currentRound);

        var byId = await _client.GetFromJsonAsync<RoundResponse>($"/rounds/{currentRound!.RoundId}");

        Assert.NotNull(byId);
        Assert.Equal(currentRound.RoundId, byId!.RoundId);
        Assert.Equal("cam_round_lookup", byId.CameraId);
        Assert.Equal(1, byId.CurrentCount);
    }

    [Fact]
    public async Task GetRecentRounds_returns_active_and_closed_rounds_for_camera()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_recent_rounds",
            TrackId = "700",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        (await _client.PostAsJsonAsync("/internal/round-count-event", dto)).EnsureSuccessStatusCode();

        var currentRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_recent_rounds");
        Assert.NotNull(currentRound);

        using (var scope = _factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();

            var persistedRound = await db.Rounds.FirstAsync(r => r.RoundId == Guid.Parse(currentRound!.RoundId));
            persistedRound.Status = Domain.Enums.RoundStatus.Settled;
            persistedRound.SettledAt = DateTime.UtcNow;
            persistedRound.FinalCount = persistedRound.CurrentCount;
            await db.SaveChangesAsync();
        }

        using (var scope = _factory.Services.CreateScope())
        {
            var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
            await roundService.EnsureActiveRoundAsync("cam_recent_rounds");
        }

        var recentRounds = await _client.GetFromJsonAsync<List<RoundResponse>>("/rounds/recent?cameraId=cam_recent_rounds&limit=10");

        Assert.NotNull(recentRounds);
        Assert.True(recentRounds!.Count >= 2);
        Assert.Contains(recentRounds, item => item.Status == "settled");
        Assert.Contains(recentRounds, item => item.Status == "open");
    }

    [Fact]
    public async Task RoundTimeline_returns_round_and_crossing_events()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_timeline",
            TrackId = "21",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            SnapshotUrl = "snapshots/timeline.jpg",
            TotalCount = 1,
        };

        var response = await _client.PostAsJsonAsync("/internal/round-count-event", dto);
        response.EnsureSuccessStatusCode();

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_timeline");
        Assert.NotNull(round);

        var timeline = await _client.GetFromJsonAsync<List<RoundTimelineItemResponse>>($"/rounds/{round!.RoundId}/timeline");

        Assert.NotNull(timeline);
        Assert.Contains(timeline!, item => item.Kind == "round_event" && item.EventType == "opened");
        Assert.Contains(timeline!, item => item.Kind == "crossing_event" && item.TrackId == 21 && item.SnapshotUrl == "snapshots/timeline.jpg");
    }

    [Fact]
    public async Task RoundLifecycle_transitions_through_settling_before_settled()
    {
        var dto = new RoundCountEventDto
        {
            CameraId = "cam_settling",
            TrackId = "88",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        (await _client.PostAsJsonAsync("/internal/round-count-event", dto)).EnsureSuccessStatusCode();

        using var scope = _factory.Services.CreateScope();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        await using var db = await dbFactory.CreateDbContextAsync();

        var round = await db.Rounds.FirstAsync(r => r.CameraId == "cam_settling" && r.Status == Domain.Enums.RoundStatus.Open);
        round.BetCloseAt = DateTime.UtcNow.AddSeconds(-5);
        round.EndsAt = DateTime.UtcNow.AddSeconds(-1);
        await db.SaveChangesAsync();

        await roundService.TickAsync();
        await roundService.TickAsync();

        var settlingRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_settling");
        Assert.NotNull(settlingRound);
        Assert.Equal("settling", settlingRound!.Status);

        await using var db2 = await dbFactory.CreateDbContextAsync();
        var persistedRound = await db2.Rounds.FirstAsync(r => r.RoundId == Guid.Parse(settlingRound.RoundId));
        persistedRound.EndsAt = DateTime.UtcNow.AddSeconds(-10);
        await db2.SaveChangesAsync();

        await roundService.TickAsync();

        await using var db3 = await dbFactory.CreateDbContextAsync();
        var settledRound = await db3.Rounds.FirstAsync(r => r.RoundId == persistedRound.RoundId);
        Assert.Equal(Domain.Enums.RoundStatus.Settled, settledRound.Status);
        Assert.NotNull(settledRound.SettledAt);
    }

    [Fact]
    public async Task CreateBet_accepts_market_purchase_for_open_round()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_create");
        Assert.NotNull(round);
        var market = Assert.Single(round!.Markets, m => m.MarketType == "exact");

        var response = await _client.PostAsJsonAsync("/internal/bets", new CreateBetDto
        {
            TransactionId = "txn-bet-create-001",
            GameSessionId = "session-bet-create-001",
            RoundId = round.RoundId,
            MarketId = market.MarketId,
            StakeAmount = 12.50m,
            Currency = "BRL",
            PlayerRef = "player-123",
            OperatorRef = "brand-a",
        });

        response.EnsureSuccessStatusCode();
        var bet = await response.Content.ReadFromJsonAsync<BetResponse>();

        Assert.NotNull(bet);
        Assert.Equal(round.RoundId, bet!.RoundId);
        Assert.Equal(market.MarketId, bet.MarketId);
        Assert.Equal("accepted", bet.Status);
        Assert.Equal("BRL", bet.Currency);
        Assert.Equal(market.Odds, bet.Odds);
        Assert.Equal(12.50m, bet.StakeAmount);
        Assert.Equal(decimal.Round(12.50m * market.Odds, 2, MidpointRounding.AwayFromZero), bet.PotentialPayout);
        Assert.Equal("player-123", bet.PlayerRef);
    }

    [Fact]
    public async Task CreateBet_is_idempotent_for_duplicate_transaction_id()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_idempotent");
        Assert.NotNull(round);
        var market = round!.Markets.First();

        var payload = new CreateBetDto
        {
            TransactionId = "txn-bet-idempotent-001",
            GameSessionId = "session-bet-idempotent-001",
            RoundId = round.RoundId,
            MarketId = market.MarketId,
            StakeAmount = 20m,
            Currency = "BRL",
        };

        var first = await _client.PostAsJsonAsync("/internal/bets", payload);
        var second = await _client.PostAsJsonAsync("/internal/bets", payload);

        first.EnsureSuccessStatusCode();
        second.EnsureSuccessStatusCode();

        var firstBet = await first.Content.ReadFromJsonAsync<BetResponse>();
        var secondBet = await second.Content.ReadFromJsonAsync<BetResponse>();

        Assert.NotNull(firstBet);
        Assert.NotNull(secondBet);
        Assert.Equal(firstBet!.Id, secondBet!.Id);
        Assert.Equal(firstBet.ProviderBetId, secondBet.ProviderBetId);

        using var scope = _factory.Services.CreateScope();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        await using var db = await dbFactory.CreateDbContextAsync();
        Assert.Equal(1, await db.Bets.CountAsync(b => b.TransactionId == "txn-bet-idempotent-001"));
    }

    [Fact]
    public async Task CreateBet_rejects_request_after_bet_close()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_closed");
        Assert.NotNull(round);

        using (var scope = _factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();
            var persistedRound = await db.Rounds.FirstAsync(r => r.RoundId == Guid.Parse(round!.RoundId));
            persistedRound.BetCloseAt = DateTime.UtcNow.AddSeconds(-1);
            await db.SaveChangesAsync();
        }

        var response = await _client.PostAsJsonAsync("/internal/bets", new CreateBetDto
        {
            TransactionId = "txn-bet-closed-001",
            GameSessionId = "session-bet-closed-001",
            RoundId = round!.RoundId,
            MarketId = round.Markets.First().MarketId,
            StakeAmount = 10m,
            Currency = "BRL",
        });

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task CreateBet_rejects_unknown_market_for_round()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_market_validation");
        Assert.NotNull(round);

        var response = await _client.PostAsJsonAsync("/internal/bets", new CreateBetDto
        {
            TransactionId = "txn-bet-market-miss-001",
            GameSessionId = "session-bet-market-miss-001",
            RoundId = round!.RoundId,
            MarketId = Guid.NewGuid().ToString(),
            StakeAmount = 15m,
            Currency = "BRL",
        });

        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
    }

    [Fact]
    public async Task GetBetById_returns_frozen_market_snapshot()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_lookup");
        Assert.NotNull(round);
        var market = round!.Markets.First();

        var createResponse = await _client.PostAsJsonAsync("/internal/bets", new CreateBetDto
        {
            TransactionId = "txn-bet-lookup-001",
            GameSessionId = "session-bet-lookup-001",
            RoundId = round.RoundId,
            MarketId = market.MarketId,
            StakeAmount = 7m,
            Currency = "BRL",
        });

        createResponse.EnsureSuccessStatusCode();
        var createdBet = await createResponse.Content.ReadFromJsonAsync<BetResponse>();
        Assert.NotNull(createdBet);

        using (var scope = _factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();
            var persistedMarket = await db.RoundMarkets.FirstAsync(m => m.MarketId == Guid.Parse(market.MarketId));
            persistedMarket.Label = "Alterado depois";
            persistedMarket.Odds = 9.99m;
            await db.SaveChangesAsync();
        }

        var fetchedBet = await _client.GetFromJsonAsync<BetResponse>($"/bets/{createdBet!.Id}");

        Assert.NotNull(fetchedBet);
        Assert.Equal(market.Label, fetchedBet!.MarketLabel);
        Assert.Equal(market.Odds, fetchedBet.Odds);
    }

    [Fact]
    public async Task Settled_round_updates_accepted_bets_to_win_or_loss()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_settlement");
        Assert.NotNull(round);

        var winningMarket = round!.Markets.First(m => m.MarketType == "exact");
        var losingMarket = round.Markets.First(m => m.MarketType == "under");

        var winningResponse = await _client.PostAsJsonAsync("/internal/bets", new CreateBetDto
        {
            TransactionId = "txn-bet-win-001",
            GameSessionId = "session-bet-settlement-001",
            RoundId = round.RoundId,
            MarketId = winningMarket.MarketId,
            StakeAmount = 10m,
            Currency = "BRL",
        });
        var losingResponse = await _client.PostAsJsonAsync("/internal/bets", new CreateBetDto
        {
            TransactionId = "txn-bet-loss-001",
            GameSessionId = "session-bet-settlement-001",
            RoundId = round.RoundId,
            MarketId = losingMarket.MarketId,
            StakeAmount = 10m,
            Currency = "BRL",
        });

        winningResponse.EnsureSuccessStatusCode();
        losingResponse.EnsureSuccessStatusCode();

        using (var scope = _factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();
            var persistedRound = await db.Rounds.FirstAsync(r => r.RoundId == Guid.Parse(round.RoundId));
            persistedRound.CurrentCount = winningMarket.TargetValue ?? winningMarket.Min ?? 0;
            persistedRound.BetCloseAt = DateTime.UtcNow.AddSeconds(-120);
            persistedRound.EndsAt = DateTime.UtcNow.AddSeconds(-120);
            await db.SaveChangesAsync();
        }

        using (var scope = _factory.Services.CreateScope())
        {
            var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
            await roundService.TickAsync();
            await roundService.TickAsync();
            await roundService.TickAsync();
        }

        var winningBet = await winningResponse.Content.ReadFromJsonAsync<BetResponse>();
        var losingBet = await losingResponse.Content.ReadFromJsonAsync<BetResponse>();
        var settledWinning = await _client.GetFromJsonAsync<BetResponse>($"/bets/{winningBet!.Id}");
        var settledLosing = await _client.GetFromJsonAsync<BetResponse>($"/bets/{losingBet!.Id}");

        Assert.NotNull(settledWinning);
        Assert.NotNull(settledLosing);
        Assert.Equal("settled_win", settledWinning!.Status);
        Assert.Equal("settled_loss", settledLosing!.Status);
        Assert.NotNull(settledWinning.SettledAt);
        Assert.NotNull(settledLosing.SettledAt);
    }

    [Fact]
    public async Task Void_round_voids_accepted_bets()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_bet_void");
        Assert.NotNull(round);

        var createResponse = await _client.PostAsJsonAsync("/internal/bets", new CreateBetDto
        {
            TransactionId = "txn-bet-void-001",
            GameSessionId = "session-bet-void-001",
            RoundId = round!.RoundId,
            MarketId = round.Markets.First().MarketId,
            StakeAmount = 9m,
            Currency = "BRL",
        });
        createResponse.EnsureSuccessStatusCode();
        var createdBet = await createResponse.Content.ReadFromJsonAsync<BetResponse>();

        var voidResponse = await _client.PostAsJsonAsync($"/internal/rounds/{round.RoundId}/void", new VoidRoundRequest
        {
            Reason = "Operacao manual",
        });
        voidResponse.EnsureSuccessStatusCode();

        var voidedBet = await _client.GetFromJsonAsync<BetResponse>($"/bets/{createdBet!.Id}");

        Assert.NotNull(voidedBet);
        Assert.Equal("void", voidedBet!.Status);
        Assert.NotNull(voidedBet.VoidedAt);
    }

    private static async Task ForceSettleCurrentRoundAsync(IDbContextFactory<AppDbContext> dbFactory, string cameraId)
    {
        await using var db = await dbFactory.CreateDbContextAsync();
        var round = await db.Rounds
            .Where(r => r.CameraId == cameraId)
            .Where(r => r.Status == Domain.Enums.RoundStatus.Open
                     || r.Status == Domain.Enums.RoundStatus.Closing
                     || r.Status == Domain.Enums.RoundStatus.Settling)
            .OrderByDescending(r => r.CreatedAt)
            .FirstAsync();

        round.Status = Domain.Enums.RoundStatus.Settled;
        round.SettledAt = DateTime.UtcNow;
        round.FinalCount = round.CurrentCount;
        await db.SaveChangesAsync();
    }
}
