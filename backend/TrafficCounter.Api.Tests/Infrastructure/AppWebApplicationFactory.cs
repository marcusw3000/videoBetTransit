using System.Net;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Tests.Infrastructure;

public class AppWebApplicationFactory : WebApplicationFactory<Program>
{
    public FakeMediaMtxClient MediaMtxClient { get; } = new();
    public FakeHttpClientFactory HttpClientFactory { get; } = new();

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

            foreach (var mediaMtxDescriptor in services
                .Where(d => d.ServiceType == typeof(IMediaMtxClient))
                .ToList())
            {
                services.Remove(mediaMtxDescriptor);
            }

            services.AddSingleton<IMediaMtxClient>(MediaMtxClient);

            foreach (var httpFactoryDescriptor in services
                .Where(d => d.ServiceType == typeof(IHttpClientFactory))
                .ToList())
            {
                services.Remove(httpFactoryDescriptor);
            }

            services.AddSingleton<IHttpClientFactory>(HttpClientFactory);

        });

        builder.UseEnvironment("Testing");
    }
}

public sealed class FakeMediaMtxClient : IMediaMtxClient
{
    private readonly object _lock = new();

    public List<(string PathName, string SourceUrl)> AddedPaths { get; } = [];
    public List<string> RemovedPaths { get; } = [];
    public List<string> ExistingPathChecks { get; } = [];

    public Task<bool> AddPathAsync(string pathName, string sourceUrl, CancellationToken ct = default)
    {
        lock (_lock)
        {
            AddedPaths.Add((pathName, sourceUrl));
        }

        return Task.FromResult(true);
    }

    public Task<bool> RemovePathAsync(string pathName, CancellationToken ct = default)
    {
        lock (_lock)
        {
            RemovedPaths.Add(pathName);
        }

        return Task.FromResult(true);
    }

    public Task<bool> PathExistsAsync(string pathName, CancellationToken ct = default)
    {
        lock (_lock)
        {
            ExistingPathChecks.Add(pathName);
        }

        return Task.FromResult(true);
    }

    public void Reset()
    {
        lock (_lock)
        {
            AddedPaths.Clear();
            RemovedPaths.Clear();
            ExistingPathChecks.Clear();
        }
    }
}

public sealed class FakeHttpClientFactory : IHttpClientFactory
{
    public HttpClient CreateClient(string name)
        => new(new AlwaysSuccessHandler())
        {
            BaseAddress = new Uri("http://127.0.0.1")
        };
}

internal sealed class AlwaysSuccessHandler : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
}
