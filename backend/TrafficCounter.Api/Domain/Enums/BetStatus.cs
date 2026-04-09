namespace TrafficCounter.Api.Domain.Enums;

public enum BetStatus
{
    Accepted = 0,
    SettledWin = 1,
    SettledLoss = 2,
    Void = 3,
    Rollback = 4,
}
