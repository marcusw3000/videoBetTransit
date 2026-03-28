using System.Net;
using System.Net.Http.Json;
using TrafficCounter.Api.Models;
using Xunit;

namespace TrafficCounter.Api.Tests;

public class CameraConfigApiTests
{
    [Fact]
    public async Task SaveAndGetConfig_PersistsCameraConfiguration()
    {
        using var factory = new CustomWebApplicationFactory();
        using var client = factory.CreateClient();

        var payload = new CameraConfigDto
        {
            CameraId = "cam-sp125",
            Roi = new RoiDto { X = 10, Y = 20, W = 300, H = 120 },
            CountLine = new CountLineDto { X1 = 15, Y1 = 90, X2 = 280, Y2 = 90 },
            CountDirection = "down",
        };

        var saveResponse = await client.PostAsJsonAsync("/api/camera-config/cam-sp125", payload);
        saveResponse.EnsureSuccessStatusCode();

        var saved = await saveResponse.Content.ReadFromJsonAsync<CameraConfigDto>();
        var fetched = await client.GetFromJsonAsync<CameraConfigDto>("/api/camera-config/cam-sp125");
        var all = await client.GetFromJsonAsync<List<CameraConfigDto>>("/api/camera-config");

        Assert.NotNull(saved);
        Assert.NotNull(fetched);
        Assert.NotNull(all);
        Assert.Equal("cam-sp125", fetched.CameraId);
        Assert.Equal(300, fetched.Roi.W);
        Assert.Equal(90, fetched.CountLine.Y1);
        Assert.Equal("down", fetched.CountDirection);
        Assert.Single(all);
    }

    [Fact]
    public async Task GetConfig_ReturnsNotFound_WhenCameraDoesNotExist()
    {
        using var factory = new CustomWebApplicationFactory();
        using var client = factory.CreateClient();

        var response = await client.GetAsync("/api/camera-config/cam-missing");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }
}
