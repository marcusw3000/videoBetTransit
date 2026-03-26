using Microsoft.AspNetCore.SignalR;

namespace TrafficCounter.Api.Hubs;

public class OverlayHub : Hub
{
    public override async Task OnConnectedAsync()
    {
        Console.WriteLine($"[OverlayHub] Cliente conectado: {Context.ConnectionId}");
        await base.OnConnectedAsync();
    }

    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        Console.WriteLine($"[OverlayHub] Cliente desconectado: {Context.ConnectionId}");
        await base.OnDisconnectedAsync(exception);
    }
}
