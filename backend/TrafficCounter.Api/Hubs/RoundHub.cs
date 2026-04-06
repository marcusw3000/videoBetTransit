using Microsoft.AspNetCore.SignalR;

namespace TrafficCounter.Api.Hubs;

public class RoundHub : Hub
{
    public override Task OnConnectedAsync() => base.OnConnectedAsync();
    public override Task OnDisconnectedAsync(Exception? exception) => base.OnDisconnectedAsync(exception);
}
