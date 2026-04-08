using System.Net;
using System.Net.Http.Json;
using TrafficCounter.Api.Contracts.Requests;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Tests.Infrastructure;
using Xunit;

namespace TrafficCounter.Api.Tests.Api;

public class StreamsApiTests : IClassFixture<AppWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly AppWebApplicationFactory _factory;

    public StreamsApiTests(AppWebApplicationFactory factory)
    {
        _factory = factory;
        _client = factory.CreateClient();
        _client.DefaultRequestHeaders.Add("X-API-Key", "CHANGE_ME");
    }

    [Fact]
    public async Task CreateStream_returns_201_with_location_header()
    {
        var request = new CreateStreamRequest
        {
            Name = "Test Cam",
            CameraId = "cam_001",
            SourceUrl = "rtsp://192.168.1.1:554/stream",
            SourceProtocol = "rtsp",
            CountLine = new CountLineRequest { X1 = 0, Y1 = 400, X2 = 1280, Y2 = 400 },
            Direction = "down_to_up",
        };

        var response = await _client.PostAsJsonAsync("/streams", request);

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        Assert.NotNull(response.Headers.Location);
    }

    [Fact]
    public async Task CreateStream_rejects_web_page_url()
    {
        var request = new CreateStreamRequest
        {
            Name = "Bad Cam",
            CameraId = "cam_bad",
            SourceUrl = "https://www.youtube.com/watch?v=abc",
            SourceProtocol = "hls",
            CountLine = new CountLineRequest { X1 = 0, Y1 = 400, X2 = 1280, Y2 = 400 },
            Direction = "down_to_up",
        };

        var response = await _client.PostAsJsonAsync("/streams", request);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task GetSession_returns_404_for_unknown_id()
    {
        var response = await _client.GetAsync($"/streams/{Guid.NewGuid()}");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task GetSession_returns_200_for_created_session()
    {
        var session = await CreateSessionAsync();
        var response = await _client.GetAsync($"/streams/{session.Id}");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<StreamSessionResponse>();
        Assert.Equal(session.Id, body!.Id);
        Assert.Equal("Created", body.Status);
        Assert.Equal("cam_001", body.CameraId);
        Assert.Equal("raw/cam_001", body.RawStreamPath);
        Assert.Equal("processed/cam_001", body.ProcessedStreamPath);
    }

    [Fact]
    public async Task GetMetrics_returns_zero_count_for_new_session()
    {
        var session = await CreateSessionAsync();
        var response = await _client.GetAsync($"/streams/{session.Id}/metrics");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<SessionMetricsResponse>();
        Assert.Equal(0, body!.TotalCount);
        Assert.Equal(0, body.LastMinuteCount);
    }

    [Fact]
    public async Task CreateStream_without_api_key_returns_401()
    {
        var clientNoKey = _factory.CreateClient(); // uses test transport, no API key
        var request = new CreateStreamRequest
        {
            Name = "Cam",
            CameraId = "cam_unauthorized",
            SourceUrl = "rtsp://192.168.1.1/stream",
            SourceProtocol = "rtsp",
            CountLine = new CountLineRequest(),
            Direction = "down_to_up",
        };

        var response = await clientNoKey.PostAsJsonAsync("/streams", request);
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    private async Task<StreamSessionResponse> CreateSessionAsync()
    {
        var request = new CreateStreamRequest
        {
            Name = "Integration Cam",
            CameraId = "cam_001",
            SourceUrl = "rtsp://10.0.0.1:554/live",
            SourceProtocol = "rtsp",
            CountLine = new CountLineRequest { X1 = 0, Y1 = 400, X2 = 1280, Y2 = 400 },
            Direction = "down_to_up",
        };

        var response = await _client.PostAsJsonAsync("/streams", request);
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<StreamSessionResponse>())!;
    }
}
