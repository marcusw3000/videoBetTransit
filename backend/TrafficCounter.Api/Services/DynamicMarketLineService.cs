using System.Globalization;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Options;

namespace TrafficCounter.Api.Services;

public class DynamicMarketLineService
{
    private readonly DynamicMarketOptions _options;

    public DynamicMarketLineService(IOptions<RoundOptions> options)
    {
        _options = options.Value.DynamicMarkets;
    }

    public async Task<DynamicMarketLineResult> BuildTemplatesAsync(
        AppDbContext db,
        string cameraId,
        int targetDurationSeconds,
        int roundsSinceProfileSwitch,
        DateTime? lastProfileChangedAt,
        IReadOnlyList<MarketTemplate> baseTemplates)
    {
        var templates = CloneTemplates(baseTemplates);
        if (templates.Count == 0)
            return new DynamicMarketLineResult([], 0, 0, 0, null, "fallback");

        var fallbackCenter = ClampCenter(ResolveFallbackCenter(templates));
        if (!_options.Enabled)
        {
            return new DynamicMarketLineResult(
                ApplyCenterToTemplates(templates, fallbackCenter),
                fallbackCenter,
                0,
                0,
                null,
                "fallback");
        }

        var historyLimit = Math.Min(Math.Max(0, _options.HistoryWindow), Math.Max(0, roundsSinceProfileSwitch));
        if (historyLimit <= 0)
        {
            return new DynamicMarketLineResult(
                ApplyCenterToTemplates(templates, fallbackCenter),
                fallbackCenter,
                0,
                0,
                null,
                "fallback");
        }

        var historyQuery = db.Rounds
            .AsNoTracking()
            .Where(r => r.CameraId == cameraId)
            .Where(r => r.Status == RoundStatus.Settled)
            .Where(r => r.FinalCount.HasValue);

        if (lastProfileChangedAt.HasValue)
        {
            var since = lastProfileChangedAt.Value;
            historyQuery = historyQuery.Where(r => r.CreatedAt >= since);
        }

        var rounds = await historyQuery
            .OrderByDescending(r => r.CreatedAt)
            .Take(historyLimit)
            .ToListAsync();

        if (rounds.Count == 0)
        {
            return new DynamicMarketLineResult(
                ApplyCenterToTemplates(templates, fallbackCenter),
                fallbackCenter,
                0,
                0,
                null,
                "fallback");
        }

        var samples = rounds
            .OrderBy(r => r.CreatedAt)
            .Select(r => new HistoricalRoundSample(
                r.FinalCount!.Value,
                ResolveDurationSeconds(r),
                r.FinalCount.Value / ResolveDurationSeconds(r)))
            .ToList();

        var lastRate = samples[^1].RatePerSecond;
        var emaRate = CalculateExponentialMovingAverage(samples.Select(s => s.RatePerSecond).ToList(), ToDouble(_options.EmaAlpha));
        var medianRate = CalculateMedian(samples.Select(s => s.RatePerSecond).ToList());
        var hybridRate = CombineRates(lastRate, emaRate, medianRate);
        var confidence = CalculateConfidence(samples.Count);
        var projectedCenter = confidence * hybridRate * Math.Max(1, targetDurationSeconds)
            + (1 - confidence) * fallbackCenter;
        var forecastCenter = ClampCenter((int)Math.Round(projectedCenter, MidpointRounding.AwayFromZero));

        return new DynamicMarketLineResult(
            ApplyCenterToTemplates(templates, forecastCenter),
            forecastCenter,
            samples.Count,
            confidence,
            samples[^1].FinalCount,
            "history");
    }

    private List<MarketTemplate> ApplyCenterToTemplates(IReadOnlyList<MarketTemplate> baseTemplates, int center)
    {
        var halfRange = Math.Max(0, _options.HalfRange);
        var underThreshold = Math.Max(1, center - halfRange);
        var rangeMin = underThreshold;
        var rangeMax = center + halfRange;
        var overThreshold = rangeMax + 1;

        return baseTemplates.Select(template =>
        {
            var clone = CloneTemplate(template);
            switch (clone.Type.Trim().ToLowerInvariant())
            {
                case "under":
                    clone.Label = $"Menos de {underThreshold}";
                    clone.Threshold = underThreshold;
                    clone.Min = null;
                    clone.Max = null;
                    clone.TargetValue = null;
                    break;
                case "range":
                    clone.Label = $"{rangeMin} a {rangeMax}";
                    clone.Threshold = null;
                    clone.Min = rangeMin;
                    clone.Max = rangeMax;
                    clone.TargetValue = null;
                    break;
                case "exact":
                    clone.Label = $"Exato {center}";
                    clone.Threshold = null;
                    clone.Min = null;
                    clone.Max = null;
                    clone.TargetValue = center;
                    break;
                case "over":
                    clone.Label = $"{overThreshold} ou mais";
                    clone.Threshold = overThreshold;
                    clone.Min = null;
                    clone.Max = null;
                    clone.TargetValue = null;
                    break;
            }

            return clone;
        }).ToList();
    }

    private double CombineRates(double lastRate, double emaRate, double medianRate)
    {
        var lastWeight = Math.Max(0d, ToDouble(_options.LastRoundWeight));
        var emaWeight = Math.Max(0d, ToDouble(_options.EmaWeight));
        var medianWeight = Math.Max(0d, ToDouble(_options.MedianWeight));
        var totalWeight = lastWeight + emaWeight + medianWeight;

        if (totalWeight <= 0)
            return lastRate;

        return ((lastWeight * lastRate) + (emaWeight * emaRate) + (medianWeight * medianRate)) / totalWeight;
    }

    private double CalculateConfidence(int sampleSize)
    {
        if (sampleSize <= 0)
            return 0;

        var minSamples = Math.Max(1, _options.MinSamplesForFullConfidence);
        return Math.Min(1d, sampleSize / (double)minSamples);
    }

    private static double CalculateExponentialMovingAverage(IReadOnlyList<double> values, double alpha)
    {
        if (values.Count == 0)
            return 0;

        var clampedAlpha = Math.Clamp(alpha, 0d, 1d);
        var ema = values[0];
        for (var index = 1; index < values.Count; index++)
            ema = (clampedAlpha * values[index]) + ((1d - clampedAlpha) * ema);

        return ema;
    }

    private static double CalculateMedian(IReadOnlyList<double> values)
    {
        if (values.Count == 0)
            return 0;

        var ordered = values.OrderBy(v => v).ToList();
        var middle = ordered.Count / 2;
        return ordered.Count % 2 == 0
            ? (ordered[middle - 1] + ordered[middle]) / 2d
            : ordered[middle];
    }

    private int ResolveFallbackCenter(IReadOnlyList<MarketTemplate> templates)
    {
        var exactTemplate = templates.FirstOrDefault(t => string.Equals(t.Type, "exact", StringComparison.OrdinalIgnoreCase));
        if (exactTemplate?.TargetValue is int exactTarget)
            return exactTarget;

        var rangeTemplate = templates.FirstOrDefault(t => string.Equals(t.Type, "range", StringComparison.OrdinalIgnoreCase));
        if (rangeTemplate?.Min is int min && rangeTemplate.Max is int max)
            return (int)Math.Round((min + max) / 2d, MidpointRounding.AwayFromZero);

        var underTemplate = templates.FirstOrDefault(t => string.Equals(t.Type, "under", StringComparison.OrdinalIgnoreCase));
        if (underTemplate?.Threshold is int underThreshold)
            return underThreshold + Math.Max(0, _options.HalfRange);

        var overTemplate = templates.FirstOrDefault(t => string.Equals(t.Type, "over", StringComparison.OrdinalIgnoreCase));
        if (overTemplate?.Threshold is int overThreshold)
            return Math.Max(1, overThreshold - Math.Max(0, _options.HalfRange) - 1);

        return Math.Max(1, _options.MinCenter);
    }

    private int ClampCenter(int center)
    {
        var minCenter = Math.Max(1, _options.MinCenter);
        var maxCenter = Math.Max(minCenter, _options.MaxCenter);
        return Math.Clamp(center, minCenter, maxCenter);
    }

    private static double ResolveDurationSeconds(Round round)
    {
        var duration = (round.EndsAt - round.CreatedAt).TotalSeconds;
        return duration > 0 ? duration : 1d;
    }

    private static List<MarketTemplate> CloneTemplates(IReadOnlyList<MarketTemplate> templates)
    {
        return templates.Select(CloneTemplate).ToList();
    }

    private static MarketTemplate CloneTemplate(MarketTemplate template)
    {
        return new MarketTemplate
        {
            Type = template.Type,
            Label = template.Label,
            Odds = template.Odds,
            Threshold = template.Threshold,
            Min = template.Min,
            Max = template.Max,
            TargetValue = template.TargetValue,
        };
    }

    private static double ToDouble(decimal value)
    {
        return double.Parse(value.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
    }
}

public sealed record DynamicMarketLineResult(
    List<MarketTemplate> Templates,
    int Center,
    int SampleSize,
    double Confidence,
    int? LastFinalCount,
    string ForecastSource)
{
    public string ToAuditReason()
    {
        var confidenceValue = Confidence.ToString("0.####", CultureInfo.InvariantCulture);
        var lastFinalCountValue = LastFinalCount?.ToString(CultureInfo.InvariantCulture) ?? "none";
        return $"center={Center};sampleSize={SampleSize};confidence={confidenceValue};lastFinalCount={lastFinalCountValue};forecastSource={ForecastSource}";
    }
}

internal sealed record HistoricalRoundSample(
    int FinalCount,
    double DurationSeconds,
    double RatePerSecond);
