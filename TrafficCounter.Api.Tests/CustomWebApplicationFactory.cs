using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TrafficCounter.Api.Data;

namespace TrafficCounter.Api.Tests;

public class CustomWebApplicationFactory : WebApplicationFactory<Program>, IDisposable
{
    private readonly string _databasePath = Path.Combine(
        Path.GetTempPath(),
        $"traffic-counter-tests-{Guid.NewGuid():N}.db"
    );

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");

        builder.ConfigureAppConfiguration((_, config) =>
        {
            config.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ConnectionStrings:DefaultConnection"] = $"Data Source={_databasePath}",
            });
        });

        builder.ConfigureServices(services =>
        {
            services.RemoveAll<IDbContextFactory<TrafficCounterDbContext>>();
            services.RemoveAll<DbContextOptions<TrafficCounterDbContext>>();
            services.AddDbContextFactory<TrafficCounterDbContext>(options =>
                options.UseSqlite($"Data Source={_databasePath}"));
        });
    }

    void IDisposable.Dispose()
    {
        base.Dispose();
    }
}
