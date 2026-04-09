using System.Net;
using System.Net.Http.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Requests;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
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
    public async Task GetCurrentRound_creates_round_for_requested_camera()
    {
        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_001");

        Assert.NotNull(round);
        Assert.Equal("cam_001", round!.CameraId);
        Assert.Equal("open", round.Status);
        Assert.NotEmpty(round.RoundId);
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
}
