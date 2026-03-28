using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Services;

var builder = WebApplication.CreateBuilder(args);

var connectionString = builder.Configuration.GetConnectionString("DefaultConnection")
    ?? "Data Source=trafficcounter.db";
var allowedOrigins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>()
    ?? Array.Empty<string>();

builder.Services.AddDbContextFactory<TrafficCounterDbContext>(options =>
    options.UseSqlite(connectionString));

builder.Services.AddControllers();
builder.Services.AddSignalR();
builder.Services.AddSingleton<RoundService>();
builder.Services.AddSingleton<CameraConfigService>();
builder.Services.AddHostedService<RoundWorker>();

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        if (allowedOrigins.Length > 0)
        {
            policy
                .WithOrigins(allowedOrigins)
                .AllowAnyHeader()
                .AllowAnyMethod()
                .AllowCredentials();
            return;
        }

        if (builder.Environment.IsDevelopment())
        {
            policy
                .WithOrigins(
                    "http://localhost:5173",
                    "http://localhost:3000",
                    "http://127.0.0.1:5173"
                )
                .AllowAnyHeader()
                .AllowAnyMethod()
                .AllowCredentials();
            return;
        }

        throw new InvalidOperationException(
            "Cors:AllowedOrigins must be configured outside development."
        );
    });
});

var app = builder.Build();

using (var scope = app.Services.CreateScope())
{
    var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<TrafficCounterDbContext>>();
    using var db = dbFactory.CreateDbContext();
    db.Database.Migrate();
}

app.UseCors();
app.MapControllers();
app.MapHub<RoundHub>("/hubs/round");
app.MapHub<OverlayHub>("/hubs/overlay");

Console.WriteLine("TrafficCounter.Api rodando em http://localhost:5000");

app.Run();

public partial class Program;
