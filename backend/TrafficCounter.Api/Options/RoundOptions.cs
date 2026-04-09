namespace TrafficCounter.Api.Options;

public class RoundOptions
{
    public int DurationSeconds { get; set; } = 180;
    public int BetWindowSeconds { get; set; } = 70;
    public int SettleDelaySeconds { get; set; } = 2;
    public RoundTimingOptions Timing { get; set; } = new();
    public TurboRoundOptions Turbo { get; set; } = new();
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
    public bool Enabled { get; set; } = true;
    public double Probability { get; set; } = 0.25;
    public int WarmupRoundsAfterProfileSwitch { get; set; } = 5;
}

public class RoundTimingOptions
{
    public RoundModeTimingOptions Normal { get; set; } = new()
    {
        DurationSeconds = 180,
        BetWindowSeconds = 70,
    };

    public RoundModeTimingOptions Turbo { get; set; } = new()
    {
        DurationSeconds = 120,
        BetWindowSeconds = 30,
    };
}

public class RoundModeTimingOptions
{
    public int DurationSeconds { get; set; } = 180;
    public int BetWindowSeconds { get; set; } = 70;
}

public class RoundMarketSets
{
    public List<MarketTemplate> Normal { get; set; } = [];
    public List<MarketTemplate> Turbo { get; set; } = [];
}
