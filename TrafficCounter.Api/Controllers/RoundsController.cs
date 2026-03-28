using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.SignalR;
using TrafficCounter.Api.Hubs;
using TrafficCounter.Api.Models;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class RoundsController : ControllerBase
{
    private readonly RoundService _roundService;
    private readonly IHubContext<RoundHub> _hubContext;

    public RoundsController(RoundService roundService, IHubContext<RoundHub> hubContext)
    {
        _roundService = roundService;
        _hubContext = hubContext;
    }

    [HttpGet("current")]
    public IActionResult GetCurrent()
    {
        return Ok(_roundService.GetCurrent());
    }

    [HttpGet("history")]
    public IActionResult GetHistory()
    {
        return Ok(_roundService.GetHistory());
    }

    [HttpGet("{roundId}/count-events")]
    public IActionResult GetCountEvents(string roundId)
    {
        return Ok(_roundService.GetCountEvents(roundId));
    }

    [HttpPost("settle")]
    public async Task<IActionResult> Settle()
    {
        var currentId = _roundService.GetCurrent().Id;
        var newRound = _roundService.Settle(currentId);

        if (newRound != null)
        {
            await _hubContext.Clients.All.SendAsync("round_settled", newRound);
        }

        return Ok(_roundService.GetCurrent());
    }

    [HttpPost("count-events")]
    public async Task<IActionResult> ReceiveCountEvent([FromBody] CountEvent evt)
    {
        var round = _roundService.SyncCount(evt);

        await _hubContext.Clients.All.SendAsync("count_updated", round);

        return Ok(new { received = true, currentCount = round.CurrentCount });
    }
}
