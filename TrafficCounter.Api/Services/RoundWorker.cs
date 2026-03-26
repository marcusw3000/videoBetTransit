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
            var current = _roundService.GetCurrent();

            // Verifica se o round está rodando e o tempo já acabou
            if (current != null && current.Status == "running" && DateTime.UtcNow >= current.EndsAt)
            {
                var newRound = _roundService.Settle(current.Id);
                
                // Transmite para todos os clientes conectados que o round fechou e um novo começou
                if (newRound != null)
                {
                    await _hubContext.Clients.All.SendAsync("round_settled", newRound, cancellationToken: stoppingToken);
                }
            }

            // Checa a cada segundo
            await Task.Delay(1000, stoppingToken);
        }
    }
}
