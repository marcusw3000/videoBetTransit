using Microsoft.AspNetCore.Mvc;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("bets")]
public class BetsController : ControllerBase
{
    private readonly BetService _betService;

    public BetsController(BetService betService)
    {
        _betService = betService;
    }

    [HttpGet("{betId:guid}")]
    public async Task<IActionResult> GetById(Guid betId)
    {
        var bet = await _betService.GetByIdAsync(betId);
        if (bet is null)
            return NotFound(new { error = $"Bet '{betId}' nao encontrada." });

        return Ok(bet);
    }
}
