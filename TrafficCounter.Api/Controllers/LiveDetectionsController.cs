using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.SignalR;
using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Models;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("api/live-detections")]
public class LiveDetectionsController : ControllerBase
{
    private readonly IHubContext<OverlayHub> _overlayHub;

    public LiveDetectionsController(IHubContext<OverlayHub> overlayHub)
    {
        _overlayHub = overlayHub;
    }

    [HttpPost]
    public async Task<IActionResult> ReceiveFrame([FromBody] LiveDetectionFrameDto frame)
    {
        await _overlayHub.Clients.All.SendAsync("live_detections_updated", frame);
        return Ok(new { received = true });
    }
}
