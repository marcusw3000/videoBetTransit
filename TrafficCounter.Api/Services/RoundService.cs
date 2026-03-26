using TrafficCounter.Api.Models;

namespace TrafficCounter.Api.Services;

public class RoundService
{
    private readonly List<Round> _history = new();
    private Round _current;

    public RoundService()
    {
        _current = CreateNewRound();
    }

    public Round GetCurrent() => _current;

    public List<Round> GetHistory() => _history
        .OrderByDescending(r => r.CreatedAt)
        .Take(20)
        .ToList();

    public Round? Settle(string currentId)
    {
        if (_current.Id != currentId || _current.Status == "settled") 
            return null;

        _current.Status = "settled";
        _current.FinalCount = _current.CurrentCount;
        _history.Add(_current);

        _current = CreateNewRound();
        return _current;
    }

    private readonly object _lock = new();

    public Round IncrementCount()
    {
        lock (_lock)
        {
            _current.CurrentCount++;
            return _current;
        }
    }

    private static Round CreateNewRound()
    {
        var id = $"rnd_{Guid.NewGuid().ToString()[..8]}";

        return new Round
        {
            Id = id,
            Status = "running",
            CurrentCount = 0,
            CreatedAt = DateTime.UtcNow,
            EndsAt = DateTime.UtcNow.AddMinutes(5),
            Ranges = new List<Models.Range>
            {
                new() { Id = $"{id}_r1", Label = "0–10",  Min = 0,  Max = 10, Odds = 3.5 },
                new() { Id = $"{id}_r2", Label = "11–20", Min = 11, Max = 20, Odds = 2.2 },
                new() { Id = $"{id}_r3", Label = "21–35", Min = 21, Max = 35, Odds = 1.8 },
                new() { Id = $"{id}_r4", Label = "36+",   Min = 36, Max = 999, Odds = 4.0 },
            }
        };
    }
}
