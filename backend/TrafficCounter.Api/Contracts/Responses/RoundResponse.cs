namespace TrafficCounter.Api.Contracts.Responses;

public class RoundMarketResponse
{
    public string MarketId { get; set; } = string.Empty;
    public string MarketType { get; set; } = string.Empty;
    public string Label { get; set; } = string.Empty;
    public decimal Odds { get; set; }
    public int? Min { get; set; }
    public int? Max { get; set; }
    public int? TargetValue { get; set; }
    public bool? IsWinner { get; set; }
}

public class RoundResponse
{
    public string RoundId { get; set; } = string.Empty;
    public string CameraId { get; set; } = string.Empty;
    public List<string> CameraIds { get; set; } = [];
    public string RoundMode { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public string Status { get; set; } = string.Empty;
    public bool IsSuspended { get; set; }

    public DateTime CreatedAt { get; set; }
    public DateTime BetCloseAt { get; set; }
    public DateTime EndsAt { get; set; }
    public DateTime? SettledAt { get; set; }
    public DateTime? VoidedAt { get; set; }
    public string? VoidReason { get; set; }

    public int CurrentCount { get; set; }
    public int? FinalCount { get; set; }

    public List<RoundMarketResponse> Markets { get; set; } = [];
}
