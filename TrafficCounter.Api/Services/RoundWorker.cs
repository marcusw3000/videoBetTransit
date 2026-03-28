using Microsoft.AspNetCore.SignalR;
using TrafficCounter.Api.Hubs;

namespace TrafficCounter.Api.Services;

public class RoundWorker : BackgroundService
{
    private readonly RoundService _roundService;
    private readonly IHubContext<RoundHub> _hubContext;

    public RoundWorker(RoundService roundService, IHubContext<RoundHub> hubContext)
    {
        _roundService = roundService;
        _hubContext = hubContext;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            var tick = _roundService.Tick();

            if (tick.UpdatedRound is not null)
            {
                await _hubContext.Clients.All.SendAsync("count_updated", tick.UpdatedRound, cancellationToken: stoppingToken);
            }

            if (tick.NewCurrentRound is not null)
            {
                await _hubContext.Clients.All.SendAsync("round_settled", tick.NewCurrentRound, cancellationToken: stoppingToken);
            }

            await Task.Delay(1000, stoppingToken);
        }
    }
}
