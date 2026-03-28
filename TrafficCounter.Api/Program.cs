using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Services;

var builder = WebApplication.CreateBuilder(args);

var connectionString = builder.Configuration.GetConnectionString("DefaultConnection")
    ?? "Data Source=trafficcounter.db";

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
        policy
            .WithOrigins(
                "http://localhost:5173",
                "http://localhost:3000",
                "http://127.0.0.1:5173"
            )
            .AllowAnyHeader()
            .AllowAnyMethod()
            .AllowCredentials();
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
