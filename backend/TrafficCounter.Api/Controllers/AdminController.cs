using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Controllers;

[ApiController, Route("admin"), Authorize(Roles = "admin")]
public class AdminController(RoundService rounds, IDbContextFactory<AppDbContext> factory, RoundEvidenceService evidence, CameraManagementService management) : ControllerBase
{
    [HttpGet("camera-management")]
    public async Task<IActionResult> CameraManagement() => Ok(await management.GetAsync());

    [HttpPost("camera-management/activate")]
    public async Task<IActionResult> ActivateCameraManagement(ActivateCameraManagementRequest request)
    {
        if (!ModelState.IsValid) return BadRequest(new { error = "Informe camera, perfil e justificativa." });
        return Ok(await management.ActivateAsync(request, User.FindFirstValue(ClaimTypes.NameIdentifier)!));
    }

    [HttpPut("camera-management/draft")]
    public async Task<IActionResult> UpdateCameraManagementDraft(UpdateCameraManagementDraftRequest request)
    {
        try { var state = await management.UpdateDraftAsync(request, User.FindFirstValue(ClaimTypes.NameIdentifier)!); return state is null ? Conflict(await management.GetAsync()) : Ok(state); }
        catch (ArgumentException ex) { return BadRequest(new { error = ex.Message }); }
        catch (InvalidOperationException ex) { return Conflict(new { error = ex.Message }); }
    }

    [HttpPost("camera-management/apply")]
    public async Task<IActionResult> ApplyCameraManagement() { try { return Ok(await management.ApplyAsync(User.FindFirstValue(ClaimTypes.NameIdentifier)!)); } catch (InvalidOperationException ex) { return Conflict(new { error = ex.Message }); } }

    [HttpPost("camera-management/deactivate")]
    public async Task<IActionResult> DeactivateCameraManagement() { try { return Ok(await management.DeactivateAsync(User.FindFirstValue(ClaimTypes.NameIdentifier)!)); } catch (InvalidOperationException ex) { return Conflict(new { error = ex.Message }); } }
    [HttpPost("rounds/{id:guid}/void")]
    public async Task<IActionResult> Void(Guid id, VoidRoundRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.Reason) || request.Reason.Length > 512)
            return BadRequest(new { error = "Informe um motivo de ate 512 caracteres." });
        return await rounds.VoidRoundAsync(id, request.Reason, request.ReasonCode, User.FindFirstValue(ClaimTypes.NameIdentifier)!)
            ? Ok(new { voided = true }) : Conflict(new { error = "Rodada indisponivel para anulacao." });
    }

    [HttpGet("rounds/{id:guid}/configuration")]
    public async Task<IActionResult> Configuration(Guid id)
    {
        await using var db = await factory.CreateDbContextAsync();
        var round = await db.Rounds.AsNoTracking().SingleOrDefaultAsync(r => r.RoundId == id);
        if (round is null) return NotFound();
        return Ok(new {
            available = round.OperationalSnapshotJson is not null,
            configurationVersion = round.OperationalSnapshotJson is null ? null : RoundService.ConfigurationVersion(round.OperationalSnapshotJson),
            operational = round.OperationalSnapshotJson is null ? (JsonElement?)null : JsonSerializer.Deserialize<JsonElement>(round.OperationalSnapshotJson),
            rules = round.RulesSnapshotJson is null ? (JsonElement?)null : JsonSerializer.Deserialize<JsonElement>(round.RulesSnapshotJson)
        });
    }

    [HttpGet("audit")]
    public async Task<IActionResult> Audit([FromQuery] string? target, [FromQuery] int page = 1)
    {
        await using var db = await factory.CreateDbContextAsync();
        var query = db.AdministrativeAudits.AsNoTracking();
        if (!string.IsNullOrWhiteSpace(target)) query = query.Where(a => a.Target == target || a.Target.Contains(target));
        return Ok(await query.OrderByDescending(a => a.TimestampUtc).ThenBy(a => a.Id)
            .Skip((Math.Clamp(page, 1, 10000) - 1) * 50).Take(50).ToListAsync());
    }

    [HttpGet("recovery-decisions")]
    public async Task<IActionResult> RecoveryDecisions([FromQuery] string? eventId, [FromQuery] int page = 1)
    {
        await using var db = await factory.CreateDbContextAsync();
        var query = db.OperationalRecoveryDecisions.AsNoTracking();
        if (!string.IsNullOrWhiteSpace(eventId)) query = query.Where(d => d.EventId == eventId);
        return Ok(await query.OrderByDescending(d => d.TimestampUtc).ThenBy(d => d.Id)
            .Skip((Math.Clamp(page, 1, 10000) - 1) * 50).Take(50).ToListAsync());
    }

    [HttpPost("recovery-events/{eventId}/decision")]
    public async Task<IActionResult> RecordRecoveryDecision(string eventId, OperationalRecoveryDecisionRequest request)
    {
        var allowedDecisions = new[] { "acknowledged", "investigating", "closed" };
        if (string.IsNullOrWhiteSpace(eventId) || eventId.Length > 128 ||
            !allowedDecisions.Contains(request.Decision, StringComparer.Ordinal) ||
            string.IsNullOrWhiteSpace(request.ReasonCode) || request.ReasonCode.Length > 64 ||
            (request.Reason?.Length ?? 0) > 512)
            return BadRequest(new { error = "Decisao operacional invalida." });

        var decision = new OperationalRecoveryDecision {
            EventId = eventId,
            Decision = request.Decision,
            ReasonCode = request.ReasonCode,
            Reason = string.IsNullOrWhiteSpace(request.Reason) ? null : request.Reason.Trim(),
            Actor = User.FindFirstValue(ClaimTypes.NameIdentifier)!
        };
        await using var db = await factory.CreateDbContextAsync();
        db.OperationalRecoveryDecisions.Add(decision);
        db.AdministrativeAudits.Add(new AdministrativeAudit {
            Actor = decision.Actor, Action = "recovery.decision", Target = "recovery:" + eventId,
            Outcome = decision.Decision, ReasonCode = decision.ReasonCode, Reason = decision.Reason
        });
        await db.SaveChangesAsync();
        HttpContext.Items["AuditTarget"] = "recovery:" + eventId;
        return Ok(decision);
    }

    [HttpGet("rounds/{id:guid}/evidence")]
    public async Task<IActionResult> Evidence(Guid id, CancellationToken cancellationToken)
    {
        var package = await evidence.BuildAsync(id, cancellationToken);
        return package is null ? NotFound(new { error = "Evidencias disponiveis somente para rodada encerrada." }) : Ok(package);
    }

    [HttpGet("rounds/{id:guid}/evidence.csv")]
    public async Task<IActionResult> EvidenceCsv(Guid id, CancellationToken cancellationToken)
    {
        var package = await evidence.BuildAsync(id, cancellationToken);
        if (package is null) return NotFound(new { error = "Evidencias disponiveis somente para rodada encerrada." });
        var csv = new StringBuilder("kind,timestampUtc,eventType,status,countValue,cameraId,trackId,objectClass,direction,lineId,frameNumber,confidence,imageStatus,snapshotReference,sourceCategory,streamProfileId,countMethod,countBefore,countAfter,eventHash,reason\r\n");
        foreach (var item in package.Timeline)
            csv.AppendLine(string.Join(',', Csv("round_event"), Csv(item.TimestampUtc.ToString("O")), Csv(item.EventType),
                Csv(item.RoundStatus), Csv(item.CountValue), "", "", "", "", "", "", "", "", "", Csv(item.SourceCategory), "", "", "", "", "", ""));
        foreach (var item in package.Crossings)
            csv.AppendLine(string.Join(',', Csv("crossing_event"), Csv(item.TimestampUtc.ToString("O")), Csv("counted_vehicle"),
                Csv(package.Round.Status), Csv(item.CountAfter), Csv(item.CameraId), Csv(item.TrackId), Csv(item.ObjectClass),
                Csv(item.Direction), Csv(item.LineId), Csv(item.FrameNumber), Csv(item.Confidence), Csv(item.ImageStatus),
                Csv(item.SnapshotReference), Csv(item.SourceCategory), Csv(item.StreamProfileId), Csv(item.CountMethod), Csv(item.CountBefore),
                Csv(item.CountAfter), Csv(item.EventHash), ""));
        return File(Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(csv.ToString())).ToArray(),
            "text/csv; charset=utf-8", $"evidence-{id:N}.csv");
    }

    private static string Csv(object? value)
    {
        var text = Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture) ?? "";
        if (text.Length > 0 && text[0] is '=' or '+' or '-' or '@') text = "'" + text;
        return '"' + text.Replace("\"", "\"\"") + '"';
    }
}
