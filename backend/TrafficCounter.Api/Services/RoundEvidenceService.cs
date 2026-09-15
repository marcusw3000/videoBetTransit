using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Services;

// Read-only evidence projection. Do not add bets, account identifiers, source
// URLs, worker keys or original event payloads to this package.
public sealed class RoundEvidenceService(IDbContextFactory<AppDbContext> factory, IConfiguration configuration,
    IWebHostEnvironment environment)
{
    private static readonly string[] OperationalFields = ["schemaVersion", "cameraId", "streamProfileId", "sourceFingerprint",
        "roi", "line", "countDirection", "secondaryVerificationEnabled", "secondaryVerificationBandPx"];
    private static readonly string[] RulesFields = ["version", "betWindowSeconds", "countAfterBetCloseSeconds",
        "settleDelaySeconds", "nextRoundDelaySeconds", "markets"];

    public async Task<RoundEvidencePackage?> BuildAsync(Guid roundId, CancellationToken cancellationToken = default)
    {
        await using var db = await factory.CreateDbContextAsync(cancellationToken);
        var round = await db.Rounds.AsNoTracking().Include(r => r.Markets)
            .SingleOrDefaultAsync(r => r.RoundId == roundId, cancellationToken);
        if (round is null || round.Status is not (RoundStatus.Settled or RoundStatus.Void)) return null;

        var crossingEntities = await db.VehicleCrossingEvents.AsNoTracking().Where(e => e.RoundId == roundId)
            .OrderBy(e => e.TimestampUtc).ToListAsync(cancellationToken);
        var crossings = crossingEntities.Select(e => {
            var image = ImageReference(e.Id, e.SnapshotUrl);
            return new EvidenceCrossing(e.Id, e.TimestampUtc, e.CameraId, e.TrackId, e.ObjectClass, e.Direction, e.LineId,
                e.FrameNumber, e.Confidence, image.Reference, image.Status, SourceCategory(e.Source), e.StreamProfileId,
                e.CountMethod, e.FallbackBandPx, e.CountBefore, e.CountAfter, e.EventHash);
        }).ToList();
        var timelineEntities = await db.RoundEvents.AsNoTracking().Where(e => e.RoundId == roundId)
            .OrderBy(e => e.TimestampUtc).ToListAsync(cancellationToken);
        var timeline = timelineEntities.Select(e => new EvidenceTimeline(
            e.TimestampUtc, e.EventType, e.RoundStatus, e.CountValue, SourceCategory(e.Source))).ToList();

        return new RoundEvidencePackage(
            "videobettransit-round-evidence-v1", DateTime.UtcNow,
            new EvidenceRound(round.RoundId, round.CameraId, round.RoundMode.ToString().ToLowerInvariant(),
                round.Status.ToString().ToLowerInvariant(), round.CreatedAt, round.BetCloseAt, round.EndsAt,
                round.SettledAt, round.VoidedAt, round.CurrentCount, round.FinalCount, round.VoidReasonCode),
            round.Markets.OrderBy(m => m.SortOrder).Select(m => new EvidenceMarket(m.MarketId, m.MarketType, m.Label,
                m.Odds, m.Threshold, m.Min, m.Max, m.TargetValue, m.IsWinner)).ToList(),
            timeline, crossings,
            EvidenceSnapshot.FromJson(round.OperationalSnapshotJson, OperationalFields),
            EvidenceSnapshot.FromJson(round.RulesSnapshotJson, RulesFields));
    }

    private (string? Reference, string Status) ImageReference(Guid crossingId, string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return (null, "not_recorded");
        if (Uri.TryCreate(value, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https")
            return ($"crossing-event:{crossingId:N}", "external_unverified");
        var fileName = Path.GetFileName(value.Replace('/', Path.DirectorySeparatorChar));
        if (string.IsNullOrWhiteSpace(fileName)) return (null, "invalid_reference");
        var configuredRoot = configuration["Evidence:SnapshotRoot"];
        if (string.IsNullOrWhiteSpace(configuredRoot)) return ($"crossing-event:{crossingId:N}", "reference_recorded");
        var snapshotRoot = Path.GetFullPath(configuredRoot, environment.ContentRootPath);
        return ($"crossing-event:{crossingId:N}", File.Exists(Path.Combine(snapshotRoot, fileName)) ? "available" : "missing");
    }

    private static string SourceCategory(string? source) => source switch {
        "system" or "round_manager" or "pipeline_orchestrator" or "stream_profile_activation" => source,
        not null when source.StartsWith("vision_worker", StringComparison.Ordinal) => "vision_worker",
        null or "" => "unknown",
        _ => "administrative_action"
    };
}

public sealed record RoundEvidencePackage(string SchemaVersion, DateTime GeneratedAtUtc, EvidenceRound Round,
    List<EvidenceMarket> Markets, List<EvidenceTimeline> Timeline, List<EvidenceCrossing> Crossings,
    EvidenceSnapshot OperationalSnapshot, EvidenceSnapshot RulesSnapshot);
public sealed record EvidenceRound(Guid RoundId, string CameraId, string Mode, string Status, DateTime CreatedAtUtc,
    DateTime BetCloseAtUtc, DateTime EndsAtUtc, DateTime? SettledAtUtc, DateTime? VoidedAtUtc, int CurrentCount,
    int? FinalCount, string? VoidReasonCode);
public sealed record EvidenceMarket(Guid MarketId, string MarketType, string Label, decimal Odds, int? Threshold,
    int? Min, int? Max, int? TargetValue, bool? IsWinner);
public sealed record EvidenceTimeline(DateTime TimestampUtc, string EventType, string RoundStatus, int? CountValue,
    string SourceCategory);
public sealed record EvidenceCrossing(Guid Id, DateTime TimestampUtc, string CameraId, long TrackId, string ObjectClass,
    string Direction, string LineId, long FrameNumber, double Confidence, string? SnapshotReference, string ImageStatus,
    string SourceCategory, string? StreamProfileId, string? CountMethod, int? FallbackBandPx, int? CountBefore,
    int? CountAfter, string EventHash);
public sealed record EvidenceSnapshot(string Status, JsonElement? Value)
{
    public static EvidenceSnapshot FromJson(string? json, IReadOnlyCollection<string> allowedProperties)
    {
        if (string.IsNullOrWhiteSpace(json)) return new("not_recorded", null);
        try
        {
            using var document = JsonDocument.Parse(json);
            if (document.RootElement.ValueKind != JsonValueKind.Object) return new("unreadable", null);
            var safe = document.RootElement.EnumerateObject().Where(p => allowedProperties.Contains(p.Name))
                .ToDictionary(p => p.Name, p => p.Value.Clone(), StringComparer.Ordinal);
            return new("recorded", JsonSerializer.SerializeToElement(safe));
        }
        catch (JsonException) { return new("unreadable", null); }
    }
}
