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
            return new DynamicMarketLineResult([], 0, 0, 0, null, "fallback", 0, null, 0, 0);

        var fallbackCenter = ClampCenter(ResolveFallbackCenter(templates));
        var fallbackHalfRange = ResolveStaticHalfRange();
        if (!_options.Enabled)
        {
            return new DynamicMarketLineResult(
                ApplyCenterToTemplates(templates, fallbackCenter, fallbackHalfRange),
                fallbackCenter,
                0,
                0,
                null,
                "fallback",
                fallbackHalfRange,
                null,
                0,
                0);
        }

        var historyLimit = Math.Min(Math.Max(0, _options.HistoryWindow), Math.Max(0, roundsSinceProfileSwitch));
        if (historyLimit <= 0)
        {
            return new DynamicMarketLineResult(
                ApplyCenterToTemplates(templates, fallbackCenter, fallbackHalfRange),
                fallbackCenter,
                0,
                0,
                null,
                "fallback",
                fallbackHalfRange,
                null,
                0,
                0);
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
                ApplyCenterToTemplates(templates, fallbackCenter, fallbackHalfRange),
                fallbackCenter,
                0,
                0,
                null,
                "fallback",
                fallbackHalfRange,
                null,
                0,
                0);
        }

        var samples = rounds
            .OrderBy(r => r.CreatedAt)
            .Select(r => new HistoricalRoundSample(
                r.FinalCount!.Value,
                ResolveDurationSeconds(r),
                r.FinalCount.Value / ResolveDurationSeconds(r)))
            .ToList();

        var adjustedRates = AdjustOutlierRates(samples.Select(s => s.RatePerSecond).ToList());
        var lastRate = adjustedRates.Rates[^1];
        var emaRate = CalculateExponentialMovingAverage(adjustedRates.Rates, ToDouble(_options.EmaAlpha));
        var medianRate = CalculateMedian(adjustedRates.Rates);
        var hybridRate = CombineRates(lastRate, emaRate, medianRate);
        var targetDuration = Math.Max(1, targetDurationSeconds);
        var historyProjectedCenter = hybridRate * targetDuration;
        var volatilityCount = CalculateMedianAbsoluteDeviation(adjustedRates.Rates) * targetDuration;
        var confidence = CalculateConfidence(samples.Count, historyProjectedCenter, volatilityCount);
        var projectedCenter = confidence * hybridRate * Math.Max(1, targetDurationSeconds)
            + (1 - confidence) * fallbackCenter;
        var forecastCenter = ClampCenter((int)Math.Round(projectedCenter, MidpointRounding.AwayFromZero));
        var halfRange = ResolveDynamicHalfRange(volatilityCount);

        return new DynamicMarketLineResult(
            ApplyCenterToTemplates(templates, forecastCenter, halfRange),
            forecastCenter,
            samples.Count,
            confidence,
            samples[^1].FinalCount,
            "history",
            halfRange,
            hybridRate,
            volatilityCount,
            adjustedRates.OutlierAdjustedSamples);
    }

    private List<MarketTemplate> ApplyCenterToTemplates(IReadOnlyList<MarketTemplate> baseTemplates, int center, int halfRange)
    {
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

    private double CalculateConfidence(int sampleSize, double projectedCenter, double volatilityCount)
    {
        if (sampleSize <= 0)
            return 0;

        var minSamples = Math.Max(1, _options.MinSamplesForFullConfidence);
        var sampleConfidence = Math.Min(1d, sampleSize / (double)minSamples);
        var volatilityDenominator = Math.Max(6d, Math.Abs(projectedCenter));
        var volatilityConfidence = 1d / (1d + (Math.Max(0d, volatilityCount) / volatilityDenominator * 0.5d));

        return Math.Clamp(sampleConfidence * volatilityConfidence, 0d, 1d);
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

    private AdjustedHistoricalRates AdjustOutlierRates(IReadOnlyList<double> rates)
    {
        var adjustedRates = rates.ToList();
        if (rates.Count < Math.Max(1, _options.MinSamplesForOutlierAdjustment))
            return new AdjustedHistoricalRates(adjustedRates, 0);

        var median = CalculateMedian(rates);
        var mad = CalculateMedianAbsoluteDeviation(rates);
        if (mad <= 0)
            return new AdjustedHistoricalRates(adjustedRates, 0);

        var multiplier = Math.Max(0d, ToDouble(_options.OutlierMadMultiplier));
        if (multiplier <= 0)
            return new AdjustedHistoricalRates(adjustedRates, 0);

        var lowerBound = median - (mad * multiplier);
        var upperBound = median + (mad * multiplier);
        var adjustedCount = 0;

        for (var index = 0; index < adjustedRates.Count; index++)
        {
            var original = adjustedRates[index];
            var adjusted = Math.Clamp(original, lowerBound, upperBound);
            if (Math.Abs(adjusted - original) > double.Epsilon)
            {
                adjustedRates[index] = adjusted;
                adjustedCount++;
            }
        }

        return new AdjustedHistoricalRates(adjustedRates, adjustedCount);
    }

    private static double CalculateMedianAbsoluteDeviation(IReadOnlyList<double> values)
    {
        if (values.Count == 0)
            return 0;

        var median = CalculateMedian(values);
        return CalculateMedian(values.Select(value => Math.Abs(value - median)).ToList());
    }

    private int ResolveStaticHalfRange()
    {
        return Math.Max(0, _options.HalfRange);
    }

    private int ResolveDynamicHalfRange(double volatilityCount)
    {
        var baseHalfRange = ResolveStaticHalfRange();
        var minHalfRange = Math.Max(0, _options.MinHalfRange);
        var maxHalfRange = Math.Max(minHalfRange, _options.MaxHalfRange);
        var volatilityHalfRange = (int)Math.Ceiling(Math.Max(0d, volatilityCount) * ToDouble(_options.VolatilityRangeMultiplier));
        var preferredHalfRange = Math.Max(Math.Max(baseHalfRange, minHalfRange), volatilityHalfRange);

        return Math.Clamp(preferredHalfRange, minHalfRange, maxHalfRange);
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
    string ForecastSource,
    int HalfRange,
    double? ForecastRatePerSecond,
    double VolatilityCount,
    int OutlierAdjustedSamples)
{
    public string ToAuditReason()
    {
        var confidenceValue = Confidence.ToString("0.####", CultureInfo.InvariantCulture);
        var lastFinalCountValue = LastFinalCount?.ToString(CultureInfo.InvariantCulture) ?? "none";
        var forecastRateValue = ForecastRatePerSecond?.ToString("0.####", CultureInfo.InvariantCulture) ?? "none";
        var volatilityValue = VolatilityCount.ToString("0.####", CultureInfo.InvariantCulture);
        return $"center={Center};halfRange={HalfRange};sampleSize={SampleSize};confidence={confidenceValue};lastFinalCount={lastFinalCountValue};forecastSource={ForecastSource};forecastRatePerSecond={forecastRateValue};volatilityCount={volatilityValue};outlierAdjustedSamples={OutlierAdjustedSamples}";
    }
}

internal sealed record HistoricalRoundSample(
    int FinalCount,
    double DurationSeconds,
    double RatePerSecond);

internal sealed record AdjustedHistoricalRates(
    List<double> Rates,
    int OutlierAdjustedSamples);
