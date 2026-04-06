using System.Net;
using System.Net.Http.Json;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Requests;
using TrafficCounter.Api.Contracts.Responses;
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
            CameraId = "cam_001",
            TrackId = "track-1",
            VehicleType = "car",
            CrossedAt = DateTime.UtcNow,
            TotalCount = 1,
        };

        var countResponse = await _client.PostAsJsonAsync("/internal/round-count-event", dto);
        countResponse.EnsureSuccessStatusCode();

        var round = await _client.GetFromJsonAsync<RoundResponse>("/rounds/current?cameraId=cam_001");

        Assert.NotNull(round);
        Assert.Equal("cam_001", round!.CameraId);
        Assert.Contains("cam_001", round.CameraIds);
        Assert.Equal(1, round.CurrentCount);
        Assert.Equal("open", round.Status);
    }
}
