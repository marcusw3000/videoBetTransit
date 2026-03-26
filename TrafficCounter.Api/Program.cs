using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Services;

var builder = WebApplication.CreateBuilder(args);

// Services
builder.Services.AddControllers();
builder.Services.AddSignalR();
builder.Services.AddSingleton<RoundService>();
builder.Services.AddSingleton<CameraConfigService>();
builder.Services.AddHostedService<RoundWorker>();

// CORS — permite React dev server e qualquer localhost
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

app.UseCors();
app.MapControllers();
app.MapHub<RoundHub>("/hubs/round");
app.MapHub<OverlayHub>("/hubs/overlay");

Console.WriteLine("🚀 TrafficCounter.Api rodando em http://localhost:5000");

app.Run();
