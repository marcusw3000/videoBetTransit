using System.Net.Http.Json;
using TrafficCounter.Api.Models;
using Xunit;

namespace TrafficCounter.Api.Tests;

public class RoundsApiTests
{

    [Fact]
    public async Task GetCurrent_ReturnsRunningRound()
    {
        using var factory = new CustomWebApplicationFactory();
        using var client = factory.CreateClient();

        var round = await client.GetFromJsonAsync<Round>("/api/rounds/current");

        Assert.NotNull(round);
        Assert.Equal("running", round.Status);
        Assert.False(string.IsNullOrWhiteSpace(round.Id));
        Assert.Equal(4, round.Ranges.Count);
    }

    [Fact]
    public async Task CountEvents_UpdatesCurrentCount_AndDoesNotDecrease()
    {
        using var factory = new CustomWebApplicationFactory();
        using var client = factory.CreateClient();
        var currentRound = await client.GetFromJsonAsync<Round>("/api/rounds/current");
        Assert.NotNull(currentRound);

        var firstResponse = await client.PostAsJsonAsync(
            "/api/rounds/count-events",
            new CountEvent
            {
                CameraId = "cam-1",
                RoundId = currentRound.Id,
                TrackId = "trk-1",
                VehicleType = "car",
                CrossedAt = DateTime.UtcNow.ToString("O"),
                SnapshotUrl = "",
                TotalCount = 7,
            }
        );
        firstResponse.EnsureSuccessStatusCode();

        var currentAfterIncrease = await client.GetFromJsonAsync<Round>("/api/rounds/current");

        var secondResponse = await client.PostAsJsonAsync(
            "/api/rounds/count-events",
            new CountEvent
            {
                CameraId = "cam-1",
                RoundId = currentRound.Id,
                TrackId = "trk-2",
                VehicleType = "car",
                CrossedAt = DateTime.UtcNow.ToString("O"),
                SnapshotUrl = "",
                TotalCount = 5,
            }
        );
        secondResponse.EnsureSuccessStatusCode();

        var currentAfterDecreaseAttempt = await client.GetFromJsonAsync<Round>("/api/rounds/current");

        Assert.NotNull(currentAfterIncrease);
        Assert.NotNull(currentAfterDecreaseAttempt);
        Assert.Equal(7, currentAfterIncrease.CurrentCount);
        Assert.Equal(7, currentAfterDecreaseAttempt.CurrentCount);

        var events = await client.GetFromJsonAsync<List<CountEvent>>($"/api/rounds/{currentRound.Id}/count-events");
        Assert.NotNull(events);
        Assert.Equal(2, events.Count);
        Assert.All(events, evt => Assert.Equal(currentRound.Id, evt.RoundId));
    }

    [Fact]
    public async Task Settle_CreatesNewCurrentRound_AndMovesPreviousToHistory()
    {
        using var factory = new CustomWebApplicationFactory();
        using var client = factory.CreateClient();

        var previousRound = await client.GetFromJsonAsync<Round>("/api/rounds/current");
        Assert.NotNull(previousRound);

        var countResponse = await client.PostAsJsonAsync(
            "/api/rounds/count-events",
            new CountEvent
            {
                CameraId = "cam-1",
                RoundId = previousRound.Id,
                TrackId = "trk-1",
                VehicleType = "car",
                CrossedAt = DateTime.UtcNow.ToString("O"),
                SnapshotUrl = "",
                TotalCount = 3,
            }
        );
        countResponse.EnsureSuccessStatusCode();

        var settleResponse = await client.PostAsync("/api/rounds/settle", content: null);
        settleResponse.EnsureSuccessStatusCode();

        var newCurrentRound = await settleResponse.Content.ReadFromJsonAsync<Round>();
        var history = await client.GetFromJsonAsync<List<Round>>("/api/rounds/history");

        Assert.NotNull(newCurrentRound);
        Assert.NotEqual(previousRound.Id, newCurrentRound.Id);
        Assert.Equal("running", newCurrentRound.Status);
        Assert.Equal(0, newCurrentRound.CurrentCount);

        Assert.NotNull(history);
        var settledRound = Assert.Single(history, r => r.Id == previousRound.Id);
        Assert.Equal("settled", settledRound.Status);
        Assert.Equal(3, settledRound.FinalCount);
    }
}
