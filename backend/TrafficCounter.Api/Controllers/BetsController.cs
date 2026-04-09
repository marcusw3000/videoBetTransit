using Microsoft.AspNetCore.Mvc;
using TrafficCounter.Api.Services;
using TrafficCounter.Api.Contracts.Inbound;

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

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateBetDto dto)
    {
        try
        {
            var bet = await _betService.PlaceBetAsync(dto);
            return Ok(bet);
        }
        catch (InvalidOperationException ex)
        {
            var message = ex.Message ?? "Bet request rejected.";
            var isValidationError = message.Contains("required", StringComparison.OrdinalIgnoreCase)
                || message.Contains("valid guid", StringComparison.OrdinalIgnoreCase)
                || message.Contains("greater than zero", StringComparison.OrdinalIgnoreCase);

            return isValidationError
                ? BadRequest(new { error = message })
                : Conflict(new { error = message });
        }
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
