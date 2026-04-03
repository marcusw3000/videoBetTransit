using Microsoft.AspNetCore.SignalR;

namespace TrafficCounter.Api.Hubs;

public class MetricsHub : Hub
{
    public async Task JoinSession(string sessionId)
        => await Groups.AddToGroupAsync(Context.ConnectionId, $"session:{sessionId}");

    public async Task LeaveSession(string sessionId)
        => await Groups.RemoveFromGroupAsync(Context.ConnectionId, $"session:{sessionId}");

    public override Task OnConnectedAsync() => base.OnConnectedAsync();
    public override Task OnDisconnectedAsync(Exception? exception) => base.OnDisconnectedAsync(exception);
}
