using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Tests.Infrastructure;

public class AppWebApplicationFactory : WebApplicationFactory<Program>
{
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureServices(services =>
        {
            // Replace PostgreSQL with InMemory
            var descriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(DbContextOptions<AppDbContext>));
            if (descriptor is not null)
                services.Remove(descriptor);

            var factoryDescriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(IDbContextFactory<AppDbContext>));
            if (factoryDescriptor is not null)
                services.Remove(factoryDescriptor);

            services.AddDbContextFactory<AppDbContext>(options =>
                options.UseInMemoryDatabase($"TestDb_{Guid.NewGuid()}"));

            // Replace real MediaMTX client with a fake that always succeeds
            var mediaMtxDescriptor = services.SingleOrDefault(
                d => d.ServiceType == typeof(IMediaMtxClient));
            if (mediaMtxDescriptor is not null)
                services.Remove(mediaMtxDescriptor);

            services.AddScoped<IMediaMtxClient, FakeMediaMtxClient>();

        });

        builder.UseEnvironment("Testing");
    }
}

/// <summary>Always-successful stub for integration tests.</summary>
public class FakeMediaMtxClient : IMediaMtxClient
{
    public Task<bool> AddPathAsync(string pathName, string sourceUrl, CancellationToken ct = default)
        => Task.FromResult(true);

    public Task<bool> RemovePathAsync(string pathName, CancellationToken ct = default)
        => Task.FromResult(true);

    public Task<bool> PathExistsAsync(string pathName, CancellationToken ct = default)
        => Task.FromResult(true);
}
