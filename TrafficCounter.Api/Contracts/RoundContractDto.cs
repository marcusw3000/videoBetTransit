using TrafficCounter.Api.Models;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Contracts;

public class RoundContractDto
{
    public string RoundId { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public string Status { get; set; } = RoundService.StatusOpen;
    public DateTime CreatedAt { get; set; }
    public DateTime BetCloseAt { get; set; }
    public DateTime EndsAt { get; set; }
    public DateTime? SettledAt { get; set; }
    public DateTime? VoidedAt { get; set; }
    public string? VoidReason { get; set; }
    public int CurrentCount { get; set; }
    public int? FinalCount { get; set; }
    public bool IsSuspended { get; set; }
    public List<RoundMarketDto> Markets { get; set; } = new();
}

public class RoundMarketDto
{
    public string MarketId { get; set; } = string.Empty;
    public string MarketType { get; set; } = string.Empty;
    public string Label { get; set; } = string.Empty;
    public int Min { get; set; }
    public int Max { get; set; }
    public int? TargetValue { get; set; }
    public double Odds { get; set; }
    public bool? IsWinner { get; set; }
}

public static class RoundContractMapper
{
    public static RoundContractDto ToContract(this Round round)
    {
        return new RoundContractDto
        {
            RoundId = round.Id,
            DisplayName = round.DisplayName,
            Status = round.Status,
            CreatedAt = round.CreatedAt,
            BetCloseAt = round.BetCloseAt,
            EndsAt = round.EndsAt,
            SettledAt = round.SettledAt,
            VoidedAt = round.VoidedAt,
            VoidReason = round.VoidReason,
            CurrentCount = round.CurrentCount,
            FinalCount = round.FinalCount,
            IsSuspended = !string.Equals(round.Status, RoundService.StatusOpen, StringComparison.OrdinalIgnoreCase),
            Markets = round.Ranges
                .Select(market => new RoundMarketDto
                {
                    MarketId = market.Id,
                    MarketType = market.MarketType,
                    Label = market.Label,
                    Min = market.Min,
                    Max = market.Max,
                    TargetValue = market.TargetValue,
                    Odds = market.Odds,
                    IsWinner = market.IsWinner,
                })
                .ToList(),
        };
    }
}
