using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Options;
using TrafficCounter.Api.Services;
using TrafficCounter.Api.Workers;

var builder = WebApplication.CreateBuilder(args);

var defaultUrls = Environment.GetEnvironmentVariable("ASPNETCORE_URLS");
if (string.IsNullOrWhiteSpace(defaultUrls))
{
    builder.WebHost.UseUrls("http://0.0.0.0:8080");
}

builder.Logging.ClearProviders();
builder.Logging.AddConsole();
builder.Logging.AddDebug();

// ── Database ──────────────────────────────────────────────────────────────────
var connString = builder.Configuration.GetConnectionString("DefaultConnection")!;
var useSqlite = connString.StartsWith("Data Source", StringComparison.OrdinalIgnoreCase);

builder.Services.AddDbContextFactory<AppDbContext>(options =>
{
    if (useSqlite)
        options.UseSqlite(connString);
    else
        options.UseNpgsql(connString);
});

// ── Options ───────────────────────────────────────────────────────────────────
builder.Services.Configure<MediaMtxOptions>(builder.Configuration.GetSection("MediaMtx"));
builder.Services.Configure<VisionWorkerOptions>(builder.Configuration.GetSection("VisionWorker"));
builder.Services.Configure<SecurityOptions>(builder.Configuration.GetSection("Security"));
builder.Services.Configure<HealthMonitorOptions>(builder.Configuration.GetSection("HealthMonitor"));
builder.Services.Configure<RoundOptions>(builder.Configuration.GetSection("Rounds"));

// ── HTTP Clients ───────────────────────────────────────────────────────────────
builder.Services.AddHttpClient();
builder.Services.AddHttpClient<MediaMtxClient>();

// ── Domain services ───────────────────────────────────────────────────────────
builder.Services.AddScoped<StreamSessionService>();
builder.Services.AddScoped<CrossingEventService>();
builder.Services.AddScoped<UrlValidationService>();
builder.Services.AddScoped<RoundService>();
builder.Services.AddScoped<BetService>();
builder.Services.AddSingleton<IRandomSource, SystemRandomSource>();

// ── MediaMTX client — Singleton para poder ser injetado em Singletons/Workers ─
builder.Services.AddSingleton<IMediaMtxClient>(sp =>
{
    var factory = sp.GetRequiredService<IHttpClientFactory>();
    var http = factory.CreateClient(nameof(MediaMtxClient));
    var opts = sp.GetRequiredService<IOptions<MediaMtxOptions>>();
    var logger = sp.GetRequiredService<ILogger<MediaMtxClient>>();
    return new MediaMtxClient(http, opts, logger);
});

// ── Orchestrator (Singleton — holds per-session SemaphoreSlim map) ────────────
builder.Services.AddSingleton<PipelineOrchestratorService>();

// ── Background workers ────────────────────────────────────────────────────────
builder.Services.AddHostedService<SessionStateWorker>();
builder.Services.AddHostedService<HealthMonitorWorker>();
builder.Services.AddHostedService<RoundManagerWorker>();

// ── SignalR ───────────────────────────────────────────────────────────────────
builder.Services.AddSignalR();

// ── Controllers + CORS ────────────────────────────────────────────────────────
builder.Services.AddControllers();

var allowedOrigins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>()
    ?? ["http://localhost:5173", "http://localhost:3000"];

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
        policy.WithOrigins(allowedOrigins)
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials());
});

// ─────────────────────────────────────────────────────────────────────────────
var app = builder.Build();

// ── Migrate on startup (with retry for Docker startup race) ──────────────────
await MigrateWithRetryAsync(app);

app.UseCors();
app.MapControllers();
app.MapHub<MetricsHub>("/hubs/metrics");
app.MapHub<RoundHub>("/hubs/round");

Console.WriteLine("TrafficCounter backend running on http://0.0.0.0:8080");
app.Run();

// ── Helpers ───────────────────────────────────────────────────────────────────
static async Task MigrateWithRetryAsync(WebApplication app)
{
    const int maxRetries = 10;
    const int delayMs = 2000;

    for (int i = 1; i <= maxRetries; i++)
    {
        try
        {
            using var scope = app.Services.CreateScope();
            var factory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
            await using var ctx = await factory.CreateDbContextAsync();

            var providerName = ctx.Database.ProviderName ?? "";
            if (providerName.Contains("Sqlite", StringComparison.OrdinalIgnoreCase))
                await SqliteSchemaRepair.TryRepairLegacySchemaAsync(ctx, app.Logger);

            if (ctx.Database.IsRelational())
                await ctx.Database.MigrateAsync();
            else
                await ctx.Database.EnsureCreatedAsync();

            return;
        }
        catch (Exception ex)
        {
            if (i == maxRetries) throw;
            app.Logger.LogWarning(ex, "Database not ready (attempt {Attempt}/{Max}), retrying in {Delay}ms…",
                i, maxRetries, delayMs);
            await Task.Delay(delayMs);
        }
    }
}

public partial class Program;
