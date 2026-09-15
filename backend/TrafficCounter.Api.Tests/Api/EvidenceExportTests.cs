using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Tests.Infrastructure;
using Xunit;

namespace TrafficCounter.Api.Tests.Api;

public sealed class EvidenceExportTests(SqliteAppFactory factory) : IClassFixture<SqliteAppFactory>
{
    [Fact]
    public async Task Closed_round_exports_safe_json_and_csv_with_explicit_missing_snapshot()
    {
        var cameraId = "evidence_" + Guid.NewGuid().ToString("N");
        using var visitor = factory.CreateClient();
        var round = (await visitor.GetFromJsonAsync<RoundResponse>($"/rounds/current?cameraId={cameraId}"))!;
        var id = Guid.Parse(round.RoundId);
        Directory.CreateDirectory(factory.EvidenceSnapshotRoot);
        await File.WriteAllTextAsync(Path.Combine(factory.EvidenceSnapshotRoot, "round-1.jpg"), "image");
        using (var scope = factory.Services.CreateScope())
        {
            var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var db = await dbFactory.CreateDbContextAsync();
            var entity = await db.Rounds.SingleAsync(r => r.RoundId == id);
            entity.Status = RoundStatus.Settled;
            entity.FinalCount = 1;
            entity.SettledAt = DateTime.UtcNow;
            db.RoundEvents.Add(new RoundEvent { Id = Guid.NewGuid(), RoundId = id, EventType = "settled",
                RoundStatus = "settled", TimestampUtc = DateTime.UtcNow, CountValue = 1,
                Source = "admin@example.com", Reason = "Nome privado nao deve sair" });
            db.VehicleCrossingEvents.Add(new VehicleCrossingEvent { Id = Guid.NewGuid(), RoundId = id, CameraId = cameraId,
                TimestampUtc = DateTime.UtcNow, TrackId = 42, ObjectClass = "car", Direction = "down", LineId = "line-1",
                FrameNumber = 9, Confidence = .93, SnapshotUrl = "snapshots/round-1.jpg", EventHash = "event-1",
                Source = "worker-secret-identity", CountMethod = "line", CountBefore = 0, CountAfter = 1 });
            db.VehicleCrossingEvents.Add(new VehicleCrossingEvent { Id = Guid.NewGuid(), RoundId = id, CameraId = cameraId,
                TimestampUtc = DateTime.UtcNow.AddMilliseconds(1), TrackId = 43, ObjectClass = "car", Direction = "down",
                LineId = "line-1", SnapshotUrl = "https://user:password@example.com/image.jpg?token=never-export",
                EventHash = "event-2", Source = "vision_worker_round_count" });
            await db.SaveChangesAsync();
        }

        using var player = factory.AuthenticatedClient("player");
        Assert.Equal(HttpStatusCode.Forbidden, (await player.GetAsync($"/admin/rounds/{id}/evidence")).StatusCode);
        using var admin = factory.AuthenticatedClient();
        var jsonResponse = await admin.GetAsync($"/admin/rounds/{id}/evidence");
        jsonResponse.EnsureSuccessStatusCode();
        var json = JsonDocument.Parse(await jsonResponse.Content.ReadAsStringAsync()).RootElement;
        Assert.Equal("videobettransit-round-evidence-v1", json.GetProperty("schemaVersion").GetString());
        Assert.Equal("not_recorded", json.GetProperty("operationalSnapshot").GetProperty("status").GetString());
        Assert.Equal("available", json.GetProperty("crossings")[0].GetProperty("imageStatus").GetString());
        Assert.StartsWith("crossing-event:", json.GetProperty("crossings")[0].GetProperty("snapshotReference").GetString());
        Assert.Equal("external_unverified", json.GetProperty("crossings")[1].GetProperty("imageStatus").GetString());
        Assert.StartsWith("crossing-event:", json.GetProperty("crossings")[1].GetProperty("snapshotReference").GetString());
        Assert.False(json.TryGetProperty("bets", out _));
        var rawJson = json.GetRawText();
        Assert.DoesNotContain("admin@example.com", rawJson);
        Assert.DoesNotContain("Nome privado", rawJson);
        Assert.DoesNotContain("password", rawJson);
        Assert.DoesNotContain("never-export", rawJson);

        var csvResponse = await admin.GetAsync($"/admin/rounds/{id}/evidence.csv");
        csvResponse.EnsureSuccessStatusCode();
        var csv = await csvResponse.Content.ReadAsStringAsync();
        Assert.Contains("crossing_event", csv);
        Assert.Contains("event-1", csv);
        Assert.Contains("available", csv);
        Assert.DoesNotContain("admin@example.com", csv);
        Assert.DoesNotContain("never-export", csv);
    }

    [Fact]
    public async Task Active_round_does_not_export_evidence()
    {
        using var admin = factory.AuthenticatedClient();
        var round = (await admin.GetFromJsonAsync<RoundResponse>($"/rounds/current?cameraId=active_evidence_{Guid.NewGuid():N}"))!;
        Assert.Equal(HttpStatusCode.NotFound, (await admin.GetAsync($"/admin/rounds/{round.RoundId}/evidence")).StatusCode);
    }
}
