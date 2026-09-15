using System.Net.Http.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using TrafficCounter.Api.Security;
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
    protected virtual bool Relational => false;
    protected virtual bool RequireOperationalSnapshot => false;
    private readonly string _databasePath = Path.Combine(Path.GetTempPath(), $"videobet-test-{Guid.NewGuid():N}.db");
    public string EvidenceSnapshotRoot { get; } = Path.Combine(Path.GetTempPath(), $"videobet-snapshots-{Guid.NewGuid():N}");
    public const string WorkerKey = "test-worker-key-only-for-tests-12345";
    public const string Password = "test-password-only-12345";

    public HttpClient AuthenticatedClient(string username = "admin")
    {
        var client = CreateClient();
        var csrf = client.GetFromJsonAsync<CsrfToken>("/auth/csrf").GetAwaiter().GetResult()!;
        client.DefaultRequestHeaders.Add("X-CSRF-Token", csrf.Token);
        client.PostAsJsonAsync("/auth/login", new { username, password = Password }).GetAwaiter().GetResult().EnsureSuccessStatusCode();
        client.DefaultRequestHeaders.Remove("X-CSRF-Token");
        csrf = client.GetFromJsonAsync<CsrfToken>("/auth/csrf").GetAwaiter().GetResult()!;
        client.DefaultRequestHeaders.Add("X-CSRF-Token", csrf.Token);
        return client;
    }
    private sealed record CsrfToken(string Token);

    public FakeMediaMtxClient MediaMtxClient { get; } = new();
    public FakeHttpClientFactory HttpClientFactory { get; } = new();

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureAppConfiguration((_, config) => config.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Security:BackendApiKey"] = WorkerKey,
            ["Rounds:RequireOperationalSnapshot"] = RequireOperationalSnapshot.ToString(), // Legacy fixture cameras omit worker activation.
            ["Evidence:SnapshotRoot"] = EvidenceSnapshotRoot,
            ["Auth:LoginPermitLimit"] = "1000",
            ["Auth:Users:0:Username"] = "admin",
            ["Auth:Users:0:Role"] = "admin",
            ["Auth:Users:0:PasswordHash"] = new PasswordHasher<LocalAccount>().HashPassword(new(), Password),
            ["Auth:Users:1:Username"] = "player",
            ["Auth:Users:1:Role"] = "player",
            ["Auth:Users:1:PasswordHash"] = new PasswordHasher<LocalAccount>().HashPassword(new(), Password),
            ["Auth:Users:2:Username"] = "other",
            ["Auth:Users:2:Role"] = "player",
            ["Auth:Users:2:PasswordHash"] = new PasswordHasher<LocalAccount>().HashPassword(new(), Password),
        }));
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

            var databaseName = $"TestDb_{Guid.NewGuid()}";
            services.AddDbContextFactory<AppDbContext>(options =>
            {
                if (Relational) options.UseSqlite($"Data Source={_databasePath}");
                else options.UseInMemoryDatabase(databaseName);
            });
            foreach (var hosted in services.Where(d => d.ServiceType == typeof(IHostedService)).ToList())
                services.Remove(hosted);

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
