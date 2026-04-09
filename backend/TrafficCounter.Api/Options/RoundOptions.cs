namespace TrafficCounter.Api.Options;

public class RoundOptions
{
    public int DurationSeconds { get; set; } = 180;
    public int BetWindowSeconds { get; set; } = 70;
    public int SettleDelaySeconds { get; set; } = 2;
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
