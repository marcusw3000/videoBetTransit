using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Options;
using TrafficCounter.Api.Security;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("internal")]
[RequireApiKey]
public class InternalController : ControllerBase
{
    private readonly CrossingEventService _crossingEventService;
    private readonly StreamSessionService _sessionService;
    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly HealthMonitorOptions _healthOptions;
    private readonly RoundService _roundService;
    private readonly BetService _betService;
    private readonly CameraManagementService _management;

    public InternalController(
        CrossingEventService crossingEventService,
        StreamSessionService sessionService,
        IDbContextFactory<AppDbContext> dbFactory,
        IOptions<HealthMonitorOptions> healthOptions,
        RoundService roundService,
        BetService betService, CameraManagementService management)
    {
        _crossingEventService = crossingEventService;
        _sessionService = sessionService;
        _dbFactory = dbFactory;
        _healthOptions = healthOptions.Value;
        _roundService = roundService;
        _betService = betService;
        _management = management;
    }

    [HttpPost("crossing-events")]
    public async Task<IActionResult> ReceiveCrossingEvent([FromBody] CrossingEventInboundDto dto)
    {
        var accepted = await _crossingEventService.IngestAsync(dto);
        if (!accepted)
            return Conflict(new { error = "Session not found or not in a running state." });

        return Ok(new { received = true });
    }

    /// <summary>
    /// Endpoint chamado pelo vision worker Python a cada veículo detectado.
    /// Não requer sessão — incrementa diretamente o round ativo.
    /// </summary>
    [HttpPost("round-count-event")]
    public async Task<IActionResult> ReceiveRoundCountEvent([FromBody] RoundCountEventDto dto)
    {
        await _roundService.RecordCountEventAsync(dto);
        return Ok(new { received = true });
    }

    [HttpPost("rounds/{roundId:guid}/void")]
    public async Task<IActionResult> VoidRound(Guid roundId, [FromBody] VoidRoundRequest request)
    {
        var ok = await _roundService.VoidRoundAsync(roundId, request.Reason, request.ReasonCode);
        if (!ok)
            return Conflict(new { error = "Round não encontrado ou já encerrado/anulado." });

        return Ok(new { voided = true });
    }

    [HttpPost("rounds/profile-activated")]
    public async Task<IActionResult> NotifyStreamProfileActivated([FromBody] StreamProfileActivatedDto dto)
    {
        HttpContext.Items["AuditTarget"] = dto.CameraId;
        if (string.IsNullOrWhiteSpace(dto.CameraId))
            return BadRequest(new { error = "cameraId is required." });

        try
        {
            await _roundService.NotifyStreamProfileActivatedAsync(
                dto.CameraId,
                dto.StreamProfileId,
                dto.AllowSettling,
                dto.AutoSwitchRound,
                dto.Phase,
                dto.ActivationNonce,
                dto.ActivationSessionId);
            return Ok(new { received = true });
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(new { error = ex.Message });
        }
    }

    [HttpGet("cameras/{cameraId}/round-lock")]
    public async Task<IActionResult> GetRoundLock(string cameraId)
    {
        if (string.IsNullOrWhiteSpace(cameraId))
            return BadRequest(new { error = "cameraId is required." });

        var isLocked = await _roundService.IsCameraLockedForRoundAsync(cameraId);
        return Ok(new RoundLockResponse
        {
            CameraId = cameraId.Trim(),
            IsLocked = isLocked,
            Reason = isLocked ? RoundService.CameraLockedMessage : null,
        });
    }

    [HttpGet("camera-management")]
    public async Task<IActionResult> CameraManagement() => Ok(await _management.GetAsync());

    // The local worker panel uses the device API key, so it never receives an
    // admin browser cookie. The backend remains the authority and audit source.
    [HttpPost("camera-management/activate")]
    public async Task<IActionResult> ActivateCameraManagement([FromBody] ActivateCameraManagementRequest request)
    {
        if (!ModelState.IsValid) return BadRequest(new { error = "Informe camera, perfil e justificativa." });
        return Ok(await _management.ActivateAsync(request, "worker"));
    }

    [HttpPut("camera-management/draft")]
    public async Task<IActionResult> UpdateCameraManagementDraft([FromBody] UpdateCameraManagementDraftRequest request)
    {
        try
        {
            var state = await _management.UpdateDraftAsync(request, "worker");
            return state is null ? Conflict(await _management.GetAsync()) : Ok(state);
        }
        catch (ArgumentException ex) { return BadRequest(new { error = ex.Message }); }
        catch (InvalidOperationException ex) { return Conflict(new { error = ex.Message }); }
    }

    [HttpPost("camera-management/select-camera")]
    public async Task<IActionResult> SelectManagedCamera([FromBody] SelectManagedCameraRequest request)
    {
        if (!ModelState.IsValid) return BadRequest(new { error = "Informe camera e perfil." });
        try { return Ok(await _management.SelectCameraAsync(request, "worker")); }
        catch (InvalidOperationException ex) { return Conflict(new { error = ex.Message }); }
    }

    [HttpPost("camera-management/apply")]
    public async Task<IActionResult> ApplyCameraManagement()
    {
        try { return Ok(await _management.ApplyAsync("worker")); }
        catch (InvalidOperationException ex) { return Conflict(new { error = ex.Message }); }
    }

    [HttpPost("camera-management/deactivate")]
    public async Task<IActionResult> DeactivateCameraManagement()
    {
        try { return Ok(await _management.DeactivateAsync("worker")); }
        catch (InvalidOperationException ex) { return Conflict(new { error = ex.Message }); }
    }

    [HttpPost("camera-config")]
    public async Task<IActionResult> RegisterConfiguration(OperationalConfigurationDto dto)
    {
        HttpContext.Items["AuditTarget"] = dto.CameraId;
        try { var version = await _roundService.RegisterOperationalConfigurationAsync(dto); return Ok(new { saved = true, configurationVersion = version }); }
        catch (ArgumentException ex) { return BadRequest(new { error = ex.Message }); }
        catch (InvalidOperationException ex) { return Conflict(new { error = ex.Message }); }
    }

    [HttpPost("camera-config/validate-change")]
    public async Task<IActionResult> ValidateCameraConfigChange([FromBody] CameraConfigChangeDto dto)
    {
        HttpContext.Items["AuditTarget"] = dto.CameraId;
        if (string.IsNullOrWhiteSpace(dto.CameraId))
            return BadRequest(new { error = "cameraId is required." });

        try
        {
            if (dto.AllowSettling)
                await _roundService.EnsureCameraUnlockedForBoundaryChangeAsync(dto.CameraId);
            else
                await _roundService.EnsureCameraUnlockedAsync(dto.CameraId);
            return Ok(new { allowed = true });
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(new { error = ex.Message });
        }
    }

    [HttpPost("health-report")]
    public async Task<IActionResult> ReceiveHealthReport([FromBody] HealthReportDto dto)
    {
        if (!Guid.TryParse(dto.SessionId, out var sessionId))
            return BadRequest(new { error = "Invalid sessionId." });

        await using var db = await _dbFactory.CreateDbContextAsync();

        var session = await db.StreamSessions.FindAsync(sessionId);
        if (session is null) return NotFound();

        var log = new StreamHealthLog
        {
            Id = Guid.NewGuid(),
            SessionId = sessionId,
            TimestampUtc = DateTime.UtcNow,
            FpsIn = dto.FpsIn,
            FpsOut = dto.FpsOut,
            LatencyMs = dto.LatencyMs,
            GpuUsagePercent = dto.GpuUsagePercent,
            ReconnectCount = dto.ReconnectCount,
            Notes = dto.Notes,
        };

        db.StreamHealthLogs.Add(log);
        await db.SaveChangesAsync();

        // Transition to Degraded if FPS is below threshold
        if (dto.FpsIn < _healthOptions.DegradedFpsThreshold && session.Status == SessionStatus.Running)
        {
            await _sessionService.TransitionStatusAsync(sessionId, SessionStatus.Degraded);
        }
        else if (dto.FpsIn >= _healthOptions.DegradedFpsThreshold && session.Status == SessionStatus.Degraded)
        {
            await _sessionService.TransitionStatusAsync(sessionId, SessionStatus.Running);
        }

        return Ok(new { received = true });
    }
}
