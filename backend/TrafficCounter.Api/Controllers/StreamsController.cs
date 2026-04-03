using Microsoft.AspNetCore.Mvc;
using TrafficCounter.Api.Contracts.Requests;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Security;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("streams")]
public class StreamsController : ControllerBase
{
    private readonly StreamSessionService _sessionService;
    private readonly PipelineOrchestratorService _orchestrator;
    private readonly UrlValidationService _urlValidation;

    public StreamsController(
        StreamSessionService sessionService,
        PipelineOrchestratorService orchestrator,
        UrlValidationService urlValidation)
    {
        _sessionService = sessionService;
        _orchestrator = orchestrator;
        _urlValidation = urlValidation;
    }

    [HttpPost]
    [RequireApiKey]
    public async Task<IActionResult> CreateStream([FromBody] CreateStreamRequest request)
    {
        var validation = await _urlValidation.ValidateAsync(request.SourceUrl, request.SourceProtocol);
        if (!validation.IsValid)
            return BadRequest(new { error = validation.ErrorMessage });

        var session = await _sessionService.CreateAsync(request);
        return CreatedAtAction(nameof(GetSession), new { id = session.Id }, session);
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> GetSession(Guid id)
    {
        var session = await _sessionService.GetAsync(id);
        return session is null ? NotFound() : Ok(session);
    }

    [HttpGet("{id:guid}/metrics")]
    public async Task<IActionResult> GetMetrics(Guid id)
    {
        var metrics = await _sessionService.GetMetricsAsync(id);
        return metrics is null ? NotFound() : Ok(metrics);
    }

    [HttpPost("{id:guid}/start")]
    [RequireApiKey]
    public async Task<IActionResult> StartSession(Guid id)
    {
        var session = await _sessionService.GetAsync(id);
        if (session is null) return NotFound();

        // Must be in Ready state; if still Created, auto-transition through validation
        if (session.Status == SessionStatus.Created.ToString())
        {
            await _sessionService.TransitionStatusAsync(id, SessionStatus.ValidatingSource);
            await _sessionService.TransitionStatusAsync(id, SessionStatus.Ready);
        }
        else if (session.Status != SessionStatus.Ready.ToString())
        {
            return BadRequest(new { error = $"Session cannot be started from status '{session.Status}'." });
        }

        var result = await _orchestrator.StartPipelineAsync(id, HttpContext.RequestAborted);
        if (!result.Success)
            return UnprocessableEntity(new { error = result.ErrorMessage });

        var updated = await _sessionService.GetAsync(id);
        return Accepted(updated);
    }

    [HttpPost("{id:guid}/stop")]
    [RequireApiKey]
    public async Task<IActionResult> StopSession(Guid id)
    {
        var session = await _sessionService.GetAsync(id);
        if (session is null) return NotFound();

        await _orchestrator.StopPipelineAsync(id, HttpContext.RequestAborted);

        var updated = await _sessionService.GetAsync(id);
        return Ok(updated);
    }

    [HttpGet("{id:guid}/events")]
    public async Task<IActionResult> GetCrossingEvents(
        Guid id,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 50)
    {
        if (page < 1) page = 1;
        if (pageSize is < 1 or > 200) pageSize = 50;

        var session = await _sessionService.GetAsync(id);
        if (session is null) return NotFound();

        // Events are fetched here directly — keeping controller thin would require a repo,
        // but for MVP simplicity we inject the db factory via a service method.
        // Delegate to session service for paging.
        var events = await _sessionService.GetCrossingEventsAsync(id, page, pageSize);
        return Ok(events);
    }
}
