using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Identity;
using System.Security.Claims;
using System.Threading.RateLimiting;
using TrafficCounter.Api.Security;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Options;
using TrafficCounter.Api.Services;
using TrafficCounter.Api.Workers;

if (args.Contains("--create-user")) { AccountCommand.Run(args); return; }

if (args.Contains("--hash-password"))
{
    Console.Error.Write("Senha (entrada oculta): ");
    var password = "";
    if (Console.IsInputRedirected) password = Console.ReadLine() ?? "";
    else
    {
        ConsoleKeyInfo key;
        while ((key = Console.ReadKey(true)).Key != ConsoleKey.Enter)
            if (key.Key == ConsoleKey.Backspace) password = password.Length > 0 ? password[..^1] : password;
            else if (!char.IsControl(key.KeyChar)) password += key.KeyChar;
        Console.Error.WriteLine();
    }
    if (password.Length < 12) throw new InvalidOperationException("Use pelo menos 12 caracteres.");
    Console.WriteLine(new PasswordHasher<LocalAccount>().HashPassword(new LocalAccount(), password));
    return;
}
var builder = WebApplication.CreateBuilder(args);
builder.Configuration.AddJsonFile("appsettings.Local.json", optional: true, reloadOnChange: true);
builder.Configuration.AddEnvironmentVariables();
if (!builder.Environment.IsEnvironment("Testing") && !args.Contains("--migrate-only"))
{
    var workerKey = builder.Configuration["Security:BackendApiKey"];
    var connectionString = builder.Configuration.GetConnectionString("DefaultConnection");
    var dataProtectionPath = builder.Configuration["DataProtection:KeyPath"];
    var hasAdmin = builder.Configuration.GetSection("Auth:Users").GetChildren().Any(user =>
        string.Equals(user["Role"], "admin", StringComparison.Ordinal) && !string.IsNullOrWhiteSpace(user["PasswordHash"]));
    var connectionHasPlaceholder = string.IsNullOrWhiteSpace(connectionString) ||
        connectionString.Contains("CHANGE_ME", StringComparison.OrdinalIgnoreCase) ||
        connectionString.Contains("YOUR_PROJECT", StringComparison.OrdinalIgnoreCase);
    if (string.IsNullOrWhiteSpace(workerKey) || workerKey == "CHANGE_ME" || !hasAdmin ||
        string.IsNullOrWhiteSpace(dataProtectionPath) || connectionHasPlaceholder)
        throw new InvalidOperationException("Configuracao obrigatoria ausente: execute scripts/configure-local.ps1 e defina banco, chave interna, Data Protection e uma conta admin.");
}
builder.Services.AddSingleton<AccountStore>();
var keyPath = builder.Configuration["DataProtection:KeyPath"];
if (!string.IsNullOrWhiteSpace(keyPath))
    builder.Services.AddDataProtection().SetApplicationName("VideoBetTransit").PersistKeysToFileSystem(new DirectoryInfo(keyPath));
builder.Services.AddAntiforgery(o => o.HeaderName = "X-CSRF-Token");
builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie(o =>
{
    o.Cookie.Name = "videobet.session";
    o.Cookie.HttpOnly = true;
    o.Cookie.SameSite = SameSiteMode.Lax;
    o.Cookie.SecurePolicy = builder.Environment.IsDevelopment() || builder.Environment.IsEnvironment("Testing")
        ? CookieSecurePolicy.SameAsRequest : CookieSecurePolicy.Always;
    o.ExpireTimeSpan = TimeSpan.FromHours(8);
    o.Events.OnRedirectToLogin = c => { c.Response.StatusCode = 401; return Task.CompletedTask; };
    o.Events.OnRedirectToAccessDenied = c => { c.Response.StatusCode = 403; return Task.CompletedTask; };
    o.Events.OnValidatePrincipal = async c =>
    {
        var account = c.HttpContext.RequestServices.GetRequiredService<AccountStore>().Find(c.Principal?.Identity?.Name ?? "");
        if (account is null || account.Role != c.Principal?.FindFirstValue(ClaimTypes.Role)
            || account.OperatorRef != c.Principal?.FindFirstValue("operator")
            || account.CredentialVersion != c.Principal?.FindFirstValue("credential_version"))
        { c.RejectPrincipal(); await c.HttpContext.SignOutAsync(); }
    };
});
builder.Services.AddAuthorization();
builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = 429;
    o.AddPolicy("login", c => RateLimitPartition.GetFixedWindowLimiter(
        c.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = builder.Configuration.GetValue("Auth:LoginPermitLimit", 10), Window = TimeSpan.FromMinutes(1), QueueLimit = 0 }));
});

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
builder.Services.AddScoped<DynamicMarketLineService>();
builder.Services.AddScoped<RoundService>();
builder.Services.AddScoped<BetService>();
builder.Services.AddScoped<RoundEvidenceService>();
builder.Services.AddScoped<CameraManagementService>();

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
if (args.Contains("--migrate-only")) { Console.WriteLine("Migracoes concluidas."); return; }

app.UseMiddleware<ApiErrorsMiddleware>();
app.UseCors();
app.UseAuthentication();
app.UseMiddleware<AdministrativeAuditMiddleware>();
app.UseAuthorization();
app.UseRateLimiter();
app.UseMiddleware<BrowserCsrfMiddleware>();
// Startup must not depend on round creation: the pipeline can intentionally be
// paused for camera management, in which case /rounds/current returns a domain
// error even though the API is healthy.
app.MapGet("/health", () => Results.Ok(new { status = "ok" })).AllowAnonymous();
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

            if (ctx.Database.IsSqlite())
                await SqliteSchemaRepair.TryRepairLegacySchemaAsync(ctx, app.Logger);
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
