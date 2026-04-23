namespace TrafficCounter.Api.Options;

public class RoundOptions
{
    public int DurationSeconds { get; set; } = 60;
    public int BetWindowSeconds { get; set; } = 15;
    public int SettleDelaySeconds { get; set; } = 2;
    public RoundTimingOptions Timing { get; set; } = new();
    public TurboRoundOptions Turbo { get; set; } = new();
    public DynamicMarketOptions DynamicMarkets { get; set; } = new();
    public RoundMarketSets MarketSets { get; set; } = new();
    public List<MarketTemplate> Markets { get; set; } = [];
}

public class MarketTemplate
{
    /// <summary>"under" | "over" | "range" | "exact"</summary>
    public string Type { get; set; } = string.Empty;
    public string Label { get; set; } = string.Empty;
    public decimal Odds { get; set; }

    // under / over
    public int? Threshold { get; set; }

    // range
    public int? Min { get; set; }
    public int? Max { get; set; }

    // exact
    public int? TargetValue { get; set; }
}

public class TurboRoundOptions
{
    public bool Enabled { get; set; } = false;
    public double Probability { get; set; } = 0.25;
    public int WarmupRoundsAfterProfileSwitch { get; set; } = 5;
}

public class RoundTimingOptions
{
    public RoundModeTimingOptions Normal { get; set; } = new()
    {
        DurationSeconds = 60,
        BetWindowSeconds = 15,
    };

    public RoundModeTimingOptions Turbo { get; set; } = new()
    {
        DurationSeconds = 60,
        BetWindowSeconds = 15,
    };
}

public class RoundModeTimingOptions
{
    public int DurationSeconds { get; set; } = 60;
    public int BetWindowSeconds { get; set; } = 15;
}

public class RoundMarketSets
{
    public List<MarketTemplate> Normal { get; set; } = [];
    public List<MarketTemplate> Turbo { get; set; } = [];
}

public class DynamicMarketOptions
{
    public bool Enabled { get; set; } = true;
    public int HistoryWindow { get; set; } = 12;
    public int MinSamplesForFullConfidence { get; set; } = 3;
    public decimal LastRoundWeight { get; set; } = 0.35m;
    public decimal EmaWeight { get; set; } = 0.45m;
    public decimal MedianWeight { get; set; } = 0.20m;
    public decimal EmaAlpha { get; set; } = 0.45m;
    public int HalfRange { get; set; } = 2;
    public int MinHalfRange { get; set; } = 2;
    public int MaxHalfRange { get; set; } = 6;
    public decimal VolatilityRangeMultiplier { get; set; } = 1.25m;
    public decimal OutlierMadMultiplier { get; set; } = 2.50m;
    public int MinSamplesForOutlierAdjustment { get; set; } = 5;
    public int MinCenter { get; set; } = 1;
    public int MaxCenter { get; set; } = 60;
}
