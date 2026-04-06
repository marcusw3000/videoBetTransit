using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Workers;

/// <summary>
/// Ticks every second to advance round phases (Open→Closing→Settled) and
/// auto-create the next round when the current one ends.
/// </summary>
public class RoundManagerWorker : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<RoundManagerWorker> _logger;

    public RoundManagerWorker(IServiceScopeFactory scopeFactory, ILogger<RoundManagerWorker> logger)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("[RoundManager] Iniciando...");

        // Garante que existe um round ativo ao iniciar
        using (var scope = _scopeFactory.CreateScope())
        {
            var svc = scope.ServiceProvider.GetRequiredService<RoundService>();
            await svc.EnsureActiveRoundAsync();
        }

        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(1));

        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            try
            {
                using var scope = _scopeFactory.CreateScope();
                var svc = scope.ServiceProvider.GetRequiredService<RoundService>();
                await svc.TickAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[RoundManager] Erro no tick.");
            }
        }
    }
}
