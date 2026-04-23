using System.Net;
using System.Net.Http.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Requests;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Options;
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
        Assert.Equal(60, (int)Math.Round((round.EndsAt - round.CreatedAt).TotalSeconds));
        Assert.Equal(15, (int)Math.Round((round.BetCloseAt - round.CreatedAt).TotalSeconds));
    }

    [Fact]
    public async Task Dynamic_market_lines_fall_back_to_static_templates_without_history()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await roundService.EnsureActiveRoundAsync("cam_dynamic_fallback");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_fallback");

        Assert.NotNull(round);
        AssertMarketLine(round!, underThreshold: 10, rangeMin: 10, rangeMax: 14, exactTarget: 12, overThreshold: 15);

        await using var db = await dbFactory.CreateDbContextAsync();
        var auditEvent = await db.RoundEvents
            .Where(e => e.RoundId == Guid.Parse(round!.RoundId))
            .SingleAsync(e => e.EventType == "market_line_computed");

        Assert.Contains("forecastSource=fallback", auditEvent.Reason);
        Assert.Contains("sampleSize=0", auditEvent.Reason);
    }

    [Fact]
    public async Task Dynamic_market_lines_move_up_with_recent_high_history()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_dynamic_high",
            roundsSinceProfileSwitch: 3,
            lastProfileChangedAt: null,
            new SeededHistoricalRound(RoundMode.Normal, 29),
            new SeededHistoricalRound(RoundMode.Normal, 37),
            new SeededHistoricalRound(RoundMode.Normal, 40));

        await roundService.EnsureActiveRoundAsync("cam_dynamic_high");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_high");

        Assert.NotNull(round);
        AssertMarketLine(round!, underThreshold: 11, rangeMin: 11, rangeMax: 15, exactTarget: 13, overThreshold: 16);

        await using var db = await dbFactory.CreateDbContextAsync();
        var auditEvent = await db.RoundEvents
            .Where(e => e.RoundId == Guid.Parse(round!.RoundId))
            .SingleAsync(e => e.EventType == "market_line_computed");

        Assert.Contains("forecastSource=history", auditEvent.Reason);
        Assert.Contains("sampleSize=3", auditEvent.Reason);
        Assert.Contains("center=13", auditEvent.Reason);
    }

    [Fact]
    public async Task Dynamic_market_lines_move_down_with_recent_low_history()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_dynamic_low",
            roundsSinceProfileSwitch: 3,
            lastProfileChangedAt: null,
            new SeededHistoricalRound(RoundMode.Normal, 0),
            new SeededHistoricalRound(RoundMode.Normal, 1),
            new SeededHistoricalRound(RoundMode.Normal, 2));

        await roundService.EnsureActiveRoundAsync("cam_dynamic_low");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_low");

        Assert.NotNull(round);
        AssertMarketLine(round!, underThreshold: 1, rangeMin: 1, rangeMax: 3, exactTarget: 1, overThreshold: 4);
    }

    [Fact]
    public async Task Dynamic_market_lines_normalize_counts_from_mixed_round_modes()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_dynamic_mixed_modes",
            roundsSinceProfileSwitch: 3,
            lastProfileChangedAt: null,
            new SeededHistoricalRound(RoundMode.Normal, 18),
            new SeededHistoricalRound(RoundMode.Turbo, 12),
            new SeededHistoricalRound(RoundMode.Turbo, 12));

        await roundService.EnsureActiveRoundAsync("cam_dynamic_mixed_modes");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_mixed_modes");

        Assert.NotNull(round);
        Assert.Equal("normal", round!.RoundMode);
        AssertMarketLine(round, underThreshold: 4, rangeMin: 4, rangeMax: 8, exactTarget: 6, overThreshold: 9);
    }

    [Fact]
    public async Task Dynamic_market_lines_keep_partial_fallback_anchor_during_profile_warmup()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        var lastProfileChangedAt = DateTime.UtcNow.AddHours(-1);

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_dynamic_warmup_anchor",
            roundsSinceProfileSwitch: 1,
            lastProfileChangedAt: lastProfileChangedAt,
            new SeededHistoricalRound(RoundMode.Normal, 40));

        await roundService.EnsureActiveRoundAsync("cam_dynamic_warmup_anchor");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_warmup_anchor");

        Assert.NotNull(round);
        AssertMarketLine(round!, underThreshold: 10, rangeMin: 10, rangeMax: 14, exactTarget: 12, overThreshold: 15);
    }

    [Fact]
    public async Task Dynamic_market_lines_ignore_non_settled_history()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_dynamic_ignore_non_settled",
            roundsSinceProfileSwitch: 4,
            lastProfileChangedAt: null,
            new SeededHistoricalRound(RoundMode.Normal, 18),
            new SeededHistoricalRound(RoundMode.Normal, 18),
            new SeededHistoricalRound(RoundMode.Normal, 18));
        await SeedHistoricalRoundWithStatusAsync(
            dbFactory,
            "cam_dynamic_ignore_non_settled",
            RoundStatus.Void,
            120);

        await roundService.EnsureActiveRoundAsync("cam_dynamic_ignore_non_settled");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_ignore_non_settled");

        Assert.NotNull(round);
        AssertMarketLine(round!, underThreshold: 4, rangeMin: 4, rangeMax: 8, exactTarget: 6, overThreshold: 9);
    }

    [Fact]
    public async Task Dynamic_market_lines_smooth_single_outlier()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_dynamic_outlier",
            roundsSinceProfileSwitch: 6,
            lastProfileChangedAt: null,
            new SeededHistoricalRound(RoundMode.Normal, 30),
            new SeededHistoricalRound(RoundMode.Normal, 31),
            new SeededHistoricalRound(RoundMode.Normal, 120),
            new SeededHistoricalRound(RoundMode.Normal, 30),
            new SeededHistoricalRound(RoundMode.Normal, 31),
            new SeededHistoricalRound(RoundMode.Normal, 32));

        await roundService.EnsureActiveRoundAsync("cam_dynamic_outlier");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_outlier");

        Assert.NotNull(round);
        AssertMarketLine(round!, underThreshold: 9, rangeMin: 9, rangeMax: 13, exactTarget: 11, overThreshold: 14);

        await using var db = await dbFactory.CreateDbContextAsync();
        var auditEvent = await db.RoundEvents
            .Where(e => e.RoundId == Guid.Parse(round!.RoundId))
            .SingleAsync(e => e.EventType == "market_line_computed");

        Assert.Contains("outlierAdjustedSamples=1", auditEvent.Reason);
        Assert.Contains("forecastSource=history", auditEvent.Reason);
    }

    [Fact]
    public async Task Dynamic_market_lines_widen_range_for_volatile_camera()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_dynamic_volatile",
            roundsSinceProfileSwitch: 6,
            lastProfileChangedAt: null,
            new SeededHistoricalRound(RoundMode.Normal, 9),
            new SeededHistoricalRound(RoundMode.Normal, 45),
            new SeededHistoricalRound(RoundMode.Normal, 12),
            new SeededHistoricalRound(RoundMode.Normal, 48),
            new SeededHistoricalRound(RoundMode.Normal, 15),
            new SeededHistoricalRound(RoundMode.Normal, 42));

        await roundService.EnsureActiveRoundAsync("cam_dynamic_volatile");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_volatile");

        Assert.NotNull(round);
        var range = Assert.Single(round!.Markets, market => market.MarketType == "range");
        Assert.Equal(12, range.Max - range.Min);

        await using var db = await dbFactory.CreateDbContextAsync();
        var auditEvent = await db.RoundEvents
            .Where(e => e.RoundId == Guid.Parse(round.RoundId))
            .SingleAsync(e => e.EventType == "market_line_computed");

        Assert.Contains("halfRange=6", auditEvent.Reason);
        Assert.Contains("volatilityCount=", auditEvent.Reason);
    }

    [Fact]
    public async Task Dynamic_market_lines_keep_base_range_for_stable_camera()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_dynamic_stable",
            roundsSinceProfileSwitch: 6,
            lastProfileChangedAt: null,
            new SeededHistoricalRound(RoundMode.Normal, 30),
            new SeededHistoricalRound(RoundMode.Normal, 30),
            new SeededHistoricalRound(RoundMode.Normal, 31),
            new SeededHistoricalRound(RoundMode.Normal, 30),
            new SeededHistoricalRound(RoundMode.Normal, 31),
            new SeededHistoricalRound(RoundMode.Normal, 30));

        await roundService.EnsureActiveRoundAsync("cam_dynamic_stable");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_dynamic_stable");

        Assert.NotNull(round);
        var range = Assert.Single(round!.Markets, market => market.MarketType == "range");
        Assert.Equal(4, range.Max - range.Min);

        await using var db = await dbFactory.CreateDbContextAsync();
        var auditEvent = await db.RoundEvents
            .Where(e => e.RoundId == Guid.Parse(round.RoundId))
            .SingleAsync(e => e.EventType == "market_line_computed");

        Assert.Contains("halfRange=2", auditEvent.Reason);
    }

    [Fact]
    public void Dynamic_market_options_expose_robust_defaults()
    {
        var options = new DynamicMarketOptions();

        Assert.Equal(2, options.MinHalfRange);
        Assert.Equal(6, options.MaxHalfRange);
        Assert.Equal(1.25m, options.VolatilityRangeMultiplier);
        Assert.Equal(2.50m, options.OutlierMadMultiplier);
        Assert.Equal(5, options.MinSamplesForOutlierAdjustment);
        Assert.True(options.EmaWeight >= options.LastRoundWeight);
    }

    [Fact]
    public async Task First_source_activation_initializes_snapshot_without_voiding_active_round()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await roundService.EnsureActiveRoundAsync("cam_source_first_start");
        var roundBefore = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_source_first_start");

        await roundService.HandleCameraSourceActivationAsync("cam_source_first_start", "rtsp://camera-a/live");

        var roundAfter = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_source_first_start");

        Assert.NotNull(roundBefore);
        Assert.NotNull(roundAfter);
        Assert.Equal(roundBefore!.RoundId, roundAfter!.RoundId);
        Assert.Equal("open", roundAfter.Status);

        await using var db = await dbFactory.CreateDbContextAsync();
        var state = await db.CameraRoundStates.SingleAsync(item => item.CameraId == "cam_source_first_start");
        Assert.Equal("rtsp://camera-a/live", state.LastSourceUrl);
        Assert.False(string.IsNullOrWhiteSpace(state.LastSourceFingerprint));
        Assert.NotNull(state.LastSourceChangedAt);
    }

    [Fact]
    public async Task Same_source_activation_does_not_reset_state_or_void_round()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_source_same_restart",
            roundsSinceProfileSwitch: 3,
            lastProfileChangedAt: DateTime.UtcNow.AddHours(-2),
            new SeededHistoricalRound(RoundMode.Normal, 20),
            new SeededHistoricalRound(RoundMode.Normal, 22),
            new SeededHistoricalRound(RoundMode.Normal, 24));
        await SetCameraSourceSnapshotAsync(dbFactory, "cam_source_same_restart", "rtsp://camera-a/live");

        await roundService.EnsureActiveRoundAsync("cam_source_same_restart");
        var roundBefore = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_source_same_restart");

        await roundService.HandleCameraSourceActivationAsync("cam_source_same_restart", "rtsp://camera-a/live");

        var roundAfter = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_source_same_restart");

        Assert.NotNull(roundBefore);
        Assert.NotNull(roundAfter);
        Assert.Equal(roundBefore!.RoundId, roundAfter!.RoundId);
        Assert.Equal("open", roundAfter.Status);

        await using var db = await dbFactory.CreateDbContextAsync();
        var state = await db.CameraRoundStates.SingleAsync(item => item.CameraId == "cam_source_same_restart");
        Assert.Equal(4, state.RoundsSinceProfileSwitch);
        Assert.Equal("rtsp://camera-a/live", state.LastSourceUrl);
        Assert.Equal(0, await db.Rounds.CountAsync(r => r.CameraId == "cam_source_same_restart" && r.Status == RoundStatus.Void));
    }

    [Fact]
    public async Task Different_source_without_active_round_resets_learning_and_next_round_uses_fallback()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_source_reset_idle",
            roundsSinceProfileSwitch: 3,
            lastProfileChangedAt: DateTime.UtcNow.AddHours(-2),
            new SeededHistoricalRound(RoundMode.Normal, 29),
            new SeededHistoricalRound(RoundMode.Normal, 37),
            new SeededHistoricalRound(RoundMode.Normal, 40));
        await SetCameraSourceSnapshotAsync(dbFactory, "cam_source_reset_idle", "rtsp://camera-a/live");

        await roundService.HandleCameraSourceActivationAsync("cam_source_reset_idle", "rtsp://camera-b/live");
        await roundService.EnsureActiveRoundAsync("cam_source_reset_idle");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_source_reset_idle");

        Assert.NotNull(round);
        AssertMarketLine(round!, underThreshold: 10, rangeMin: 10, rangeMax: 14, exactTarget: 12, overThreshold: 15);

        await using var db = await dbFactory.CreateDbContextAsync();
        var state = await db.CameraRoundStates.SingleAsync(item => item.CameraId == "cam_source_reset_idle");
        Assert.Equal(1, state.RoundsSinceProfileSwitch);
        Assert.Equal("rtsp://camera-b/live", state.LastSourceUrl);
        Assert.NotNull(state.LastSourceChangedAt);
    }

    [Fact]
    public async Task Different_source_with_active_round_voids_current_round_and_resets_next_round()
    {
        using var scope = _factory.Services.CreateScope();
        var roundService = scope.ServiceProvider.GetRequiredService<RoundService>();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();

        await SeedSettledRoundHistoryAsync(
            dbFactory,
            "cam_source_reset_active",
            roundsSinceProfileSwitch: 3,
            lastProfileChangedAt: DateTime.UtcNow.AddHours(-2),
            new SeededHistoricalRound(RoundMode.Normal, 29),
            new SeededHistoricalRound(RoundMode.Normal, 37),
            new SeededHistoricalRound(RoundMode.Normal, 40));
        await SetCameraSourceSnapshotAsync(dbFactory, "cam_source_reset_active", "rtsp://camera-a/live");

        await roundService.EnsureActiveRoundAsync("cam_source_reset_active");
        var activeRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_source_reset_active");
        Assert.NotNull(activeRound);

        var betResponse = await _client.PostAsJsonAsync("/internal/bets", new CreateBetDto
        {
            TransactionId = "txn-source-swap-001",
            GameSessionId = "session-source-swap-001",
            RoundId = activeRound!.RoundId,
            MarketId = activeRound.Markets.First().MarketId,
            StakeAmount = 5m,
            Currency = "BRL",
        });
        betResponse.EnsureSuccessStatusCode();
        var createdBet = await betResponse.Content.ReadFromJsonAsync<BetResponse>();

        await roundService.HandleCameraSourceActivationAsync("cam_source_reset_active", "rtsp://camera-b/live");

        var currentRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_source_reset_active");
        var voidedBet = await _client.GetFromJsonAsync<BetResponse>($"/bets/{createdBet!.Id}");

        Assert.NotNull(currentRound);
        Assert.NotEqual(activeRound.RoundId, currentRound!.RoundId);
        Assert.Equal("open", currentRound.Status);
        AssertMarketLine(currentRound, underThreshold: 10, rangeMin: 10, rangeMax: 14, exactTarget: 12, overThreshold: 15);

        Assert.NotNull(voidedBet);
        Assert.Equal("void", voidedBet!.Status);

        await using var db = await dbFactory.CreateDbContextAsync();
        var oldRound = await db.Rounds.SingleAsync(r => r.RoundId == Guid.Parse(activeRound.RoundId));
        Assert.Equal(RoundStatus.Void, oldRound.Status);
        Assert.Equal("Camera source changed during active round", oldRound.VoidReason);
        Assert.True(await db.RoundEvents.AnyAsync(e => e.RoundId == oldRound.RoundId && e.EventType == "camera_source_changed"));
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
    public async Task Turbo_round_is_frozen_even_after_warmup_when_probability_hits()
    {
        using var scope = _factory.Services.CreateScope();
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

        await roundService.EnsureActiveRoundAsync("cam_turbo_enabled");

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_turbo_enabled");

        Assert.NotNull(round);
        Assert.Equal("normal", round!.RoundMode);
        Assert.Equal("Rodada Normal", round.DisplayName);
        Assert.Equal(60, (int)Math.Round((round.EndsAt - round.CreatedAt).TotalSeconds));
        Assert.Equal(15, (int)Math.Round((round.BetCloseAt - round.CreatedAt).TotalSeconds));
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
    public async Task ValidateCameraConfigChange_allows_boundary_change_during_settling()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_boundary_config");
        Assert.NotNull(round);

        using (var scope = _factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();
            var persisted = await db.Rounds.SingleAsync(r => r.RoundId == Guid.Parse(round!.RoundId));
            persisted.Status = RoundStatus.Settling;
            await db.SaveChangesAsync();
        }

        var response = await _client.PostAsJsonAsync("/internal/camera-config/validate-change", new CameraConfigChangeDto
        {
            CameraId = "cam_boundary_config",
            AllowSettling = true,
        });

        response.EnsureSuccessStatusCode();
    }

    [Fact]
    public async Task ValidateCameraConfigChange_without_boundary_flag_blocks_settling_round()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_settling_config");
        Assert.NotNull(round);

        using (var scope = _factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();
            var persisted = await db.Rounds.SingleAsync(r => r.RoundId == Guid.Parse(round!.RoundId));
            persisted.Status = RoundStatus.Settling;
            await db.SaveChangesAsync();
        }

        var response = await _client.PostAsJsonAsync("/internal/camera-config/validate-change", new CameraConfigChangeDto
        {
            CameraId = "cam_settling_config",
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
    public async Task NotifyStreamProfileActivated_with_auto_switch_voids_active_round_and_opens_next()
    {
        var activeRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_auto_profile");
        Assert.NotNull(activeRound);

        var response = await _client.PostAsJsonAsync("/internal/rounds/profile-activated", new StreamProfileActivatedDto
        {
            CameraId = "cam_auto_profile",
            StreamProfileId = "profile-auto",
            AutoSwitchRound = true,
        });

        response.EnsureSuccessStatusCode();

        var currentRound = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_auto_profile");
        Assert.NotNull(currentRound);
        Assert.NotEqual(activeRound!.RoundId, currentRound!.RoundId);
        Assert.Equal("open", currentRound.Status);

        using var verifyScope = _factory.Services.CreateScope();
        var verifyDbFactory = verifyScope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        await using var verifyDb = await verifyDbFactory.CreateDbContextAsync();

        var oldRound = await verifyDb.Rounds.SingleAsync(r => r.RoundId == Guid.Parse(activeRound.RoundId));
        Assert.Equal(RoundStatus.Void, oldRound.Status);
        Assert.Equal("Stream profile changed during active round", oldRound.VoidReason);
        Assert.True(await verifyDb.RoundEvents.AnyAsync(e => e.RoundId == oldRound.RoundId && e.EventType == "stream_profile_changed"));

        var state = await verifyDb.CameraRoundStates.SingleAsync(item => item.CameraId == "cam_auto_profile");
        Assert.Equal("profile-auto", state.ActiveStreamProfileId);
        Assert.Equal(1, state.RoundsSinceProfileSwitch);
        Assert.NotNull(state.LastProfileChangedAt);
    }

    [Fact]
    public async Task NotifyStreamProfileActivated_with_boundary_flag_updates_state_during_settling()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_boundary_profile");
        Assert.NotNull(round);

        using (var scope = _factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();
            var persisted = await db.Rounds.SingleAsync(r => r.RoundId == Guid.Parse(round!.RoundId));
            persisted.Status = RoundStatus.Settling;
            await db.SaveChangesAsync();
        }

        var response = await _client.PostAsJsonAsync("/internal/rounds/profile-activated", new StreamProfileActivatedDto
        {
            CameraId = "cam_boundary_profile",
            StreamProfileId = "profile-boundary",
            AllowSettling = true,
        });

        response.EnsureSuccessStatusCode();

        using var verifyScope = _factory.Services.CreateScope();
        var verifyDbFactory = verifyScope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        await using var verifyDb = await verifyDbFactory.CreateDbContextAsync();
        var state = await verifyDb.CameraRoundStates.SingleAsync(item => item.CameraId == "cam_boundary_profile");

        Assert.Equal("profile-boundary", state.ActiveStreamProfileId);
        Assert.Equal(0, state.RoundsSinceProfileSwitch);
        Assert.NotNull(state.LastProfileChangedAt);
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

    private static void AssertMarketLine(
        RoundResponse round,
        int underThreshold,
        int rangeMin,
        int rangeMax,
        int exactTarget,
        int overThreshold)
    {
        var under = Assert.Single(round.Markets, market => market.MarketType == "under");
        var range = Assert.Single(round.Markets, market => market.MarketType == "range");
        var exact = Assert.Single(round.Markets, market => market.MarketType == "exact");
        var over = Assert.Single(round.Markets, market => market.MarketType == "over");

        Assert.Equal($"Menos de {underThreshold}", under.Label);
        Assert.Equal(underThreshold, under.TargetValue);

        Assert.Equal($"{rangeMin} a {rangeMax}", range.Label);
        Assert.Equal(rangeMin, range.Min);
        Assert.Equal(rangeMax, range.Max);

        Assert.Equal($"Exato {exactTarget}", exact.Label);
        Assert.Equal(exactTarget, exact.TargetValue);

        Assert.Equal($"{overThreshold} ou mais", over.Label);
        Assert.Equal(overThreshold, over.TargetValue);
    }

    private static async Task SeedSettledRoundHistoryAsync(
        IDbContextFactory<AppDbContext> dbFactory,
        string cameraId,
        int roundsSinceProfileSwitch,
        DateTime? lastProfileChangedAt,
        params SeededHistoricalRound[] rounds)
    {
        await using var db = await dbFactory.CreateDbContextAsync();
        var now = DateTime.UtcNow;
        var state = await db.CameraRoundStates.FirstOrDefaultAsync(item => item.CameraId == cameraId);

        if (state is null)
        {
            state = new CameraRoundState
            {
                CameraId = cameraId,
                CreatedAt = now,
                UpdatedAt = now,
            };
            db.CameraRoundStates.Add(state);
        }

        state.RoundsSinceProfileSwitch = roundsSinceProfileSwitch;
        state.LastProfileChangedAt = lastProfileChangedAt;
        state.UpdatedAt = now;

        var start = lastProfileChangedAt ?? now.AddHours(-2);
        for (var index = 0; index < rounds.Length; index++)
        {
            var seededRound = rounds[index];
            var createdAt = start.AddMinutes((index + 1) * 5);
            var durationSeconds = seededRound.RoundMode == RoundMode.Turbo ? 120 : 180;
            var betWindowSeconds = seededRound.RoundMode == RoundMode.Turbo ? 30 : 70;
            var endsAt = createdAt.AddSeconds(durationSeconds);

            db.Rounds.Add(new Round
            {
                RoundId = Guid.NewGuid(),
                CameraId = cameraId,
                RoundMode = seededRound.RoundMode,
                Status = RoundStatus.Settled,
                DisplayName = seededRound.RoundMode == RoundMode.Turbo ? "Rodada Turbo" : "Rodada Normal",
                CreatedAt = createdAt,
                BetCloseAt = createdAt.AddSeconds(betWindowSeconds),
                EndsAt = endsAt,
                SettledAt = endsAt.AddSeconds(2),
                CurrentCount = seededRound.FinalCount,
                FinalCount = seededRound.FinalCount,
            });
        }

        await db.SaveChangesAsync();
    }

    private static async Task SeedHistoricalRoundWithStatusAsync(
        IDbContextFactory<AppDbContext> dbFactory,
        string cameraId,
        RoundStatus status,
        int finalCount)
    {
        await using var db = await dbFactory.CreateDbContextAsync();
        var now = DateTime.UtcNow;
        var createdAt = now.AddMinutes(-3);
        var endsAt = createdAt.AddSeconds(180);

        db.Rounds.Add(new Round
        {
            RoundId = Guid.NewGuid(),
            CameraId = cameraId,
            RoundMode = RoundMode.Normal,
            Status = status,
            DisplayName = "Rodada Normal",
            CreatedAt = createdAt,
            BetCloseAt = createdAt.AddSeconds(70),
            EndsAt = endsAt,
            SettledAt = status == RoundStatus.Settled ? endsAt.AddSeconds(2) : null,
            CurrentCount = finalCount,
            FinalCount = finalCount,
        });

        await db.SaveChangesAsync();
    }

    private static async Task SetCameraSourceSnapshotAsync(
        IDbContextFactory<AppDbContext> dbFactory,
        string cameraId,
        string sourceUrl)
    {
        await using var db = await dbFactory.CreateDbContextAsync();
        var state = await db.CameraRoundStates.SingleAsync(item => item.CameraId == cameraId);
        var now = DateTime.UtcNow;

        state.LastSourceUrl = sourceUrl;
        state.LastSourceFingerprint = Convert.ToHexString(
            System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(sourceUrl)))
            .ToLowerInvariant();
        state.LastSourceChangedAt = now.AddMinutes(-1);
        state.UpdatedAt = now;

        await db.SaveChangesAsync();
    }

    private readonly record struct SeededHistoricalRound(RoundMode RoundMode, int FinalCount);
}
