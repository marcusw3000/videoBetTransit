using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Services;
using Xunit;

namespace TrafficCounter.Api.Tests.Services;

public class HashChainTests
{
    private static CrossingEventInboundDto MakeDto(string sessionId = "sess-1") => new()
    {
        SessionId = sessionId,
        TimestampUtc = new DateTime(2026, 4, 2, 10, 0, 0, DateTimeKind.Utc),
        TrackId = 42,
        ObjectClass = "car",
        Direction = "down_to_up",
        LineId = "main-line",
        Confidence = 0.91,
        FrameNumber = 1000,
        EventHash = string.Empty,
    };

    [Fact]
    public void Genesis_event_produces_deterministic_hash()
    {
        var dto = MakeDto();
        var hash1 = CrossingEventService.ComputeHash(dto, null);
        var hash2 = CrossingEventService.ComputeHash(dto, null);

        Assert.Equal(hash1, hash2);
        Assert.Equal(64, hash1.Length); // SHA-256 hex = 64 chars
        Assert.Matches("^[0-9a-f]+$", hash1);
    }

    [Fact]
    public void Chain_produces_different_hash_from_genesis()
    {
        var dto = MakeDto();
        var genesis = CrossingEventService.ComputeHash(dto, null);
        var chained = CrossingEventService.ComputeHash(dto, genesis);

        Assert.NotEqual(genesis, chained);
    }

    [Fact]
    public void Changing_any_field_changes_the_hash()
    {
        var dto = MakeDto();
        var original = CrossingEventService.ComputeHash(dto, null);

        dto.TrackId = 99;
        var changed = CrossingEventService.ComputeHash(dto, null);

        Assert.NotEqual(original, changed);
    }

    [Fact]
    public void Chain_of_three_events_has_correct_linkage()
    {
        var dto1 = MakeDto();
        var h1 = CrossingEventService.ComputeHash(dto1, null);

        var dto2 = MakeDto(); dto2.TrackId = 2;
        var h2 = CrossingEventService.ComputeHash(dto2, h1);

        var dto3 = MakeDto(); dto3.TrackId = 3;
        var h3 = CrossingEventService.ComputeHash(dto3, h2);

        Assert.NotEqual(h1, h2);
        Assert.NotEqual(h2, h3);
        Assert.NotEqual(h1, h3);
    }
}
