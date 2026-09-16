using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Contracts.Inbound;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;

namespace TrafficCounter.Api.Services;

public sealed class CameraManagementService(IDbContextFactory<AppDbContext> factory, RoundService rounds)
{
    public async Task<PipelineManagementState> GetAsync()
    {
        await using var db = await factory.CreateDbContextAsync();
        return await GetStateAsync(db);
    }

    public async Task<PipelineManagementState> ActivateAsync(ActivateCameraManagementRequest request, string actor)
    {
        await using var db = await factory.CreateDbContextAsync();
        var state = await GetStateAsync(db);
        if (state.IsActive) return state;
        state.IsActive = true;
        state.CameraId = request.CameraId.Trim(); state.StreamProfileId = request.StreamProfileId.Trim();
        state.Reason = request.Reason.Trim(); state.ActivatedBy = actor; state.ActivatedAt = DateTime.UtcNow;
        state.DraftApplied = true; state.UpdatedAt = DateTime.UtcNow; state.Revision++;
        db.AdministrativeAudits.Add(new AdministrativeAudit { Actor = actor, Action = "camera_management.activate", Target = "pipeline", Outcome = "completed", ReasonCode = "camera_management", Reason = state.Reason });
        await db.SaveChangesAsync();
        var activeIds = await db.Rounds.AsNoTracking().Where(r => r.Status == RoundStatus.Open || r.Status == RoundStatus.Closing || r.Status == RoundStatus.Settling).Select(r => r.RoundId).ToListAsync();
        foreach (var id in activeIds) await rounds.VoidRoundAsync(id, "Camera management mode activated: " + state.Reason, "camera_management", actor);
        return await GetAsync();
    }

    public async Task<PipelineManagementState?> UpdateDraftAsync(UpdateCameraManagementDraftRequest request, string actor)
    {
        if (!GeometryValid(request.Roi, ["x", "y", "w", "h"]) || !GeometryValid(request.Line, ["x1", "y1", "x2", "y2"]) || request.Roi["w"] <= 0 || request.Roi["h"] <= 0)
            throw new ArgumentException("ROI ou linha de contagem invalidas.");
        await using var db = await factory.CreateDbContextAsync();
        var state = await GetStateAsync(db);
        if (!state.IsActive) throw new InvalidOperationException("O modo de gerenciamento nao esta ativo.");
        if (state.Revision != request.ExpectedRevision) return null;
        state.DraftConfigurationJson = JsonSerializer.Serialize(new { roi = request.Roi, line = request.Line });
        state.DraftApplied = false; state.Revision++; state.UpdatedAt = DateTime.UtcNow;
        db.AdministrativeAudits.Add(new AdministrativeAudit { Actor = actor, Action = "camera_management.draft", Target = "pipeline", Outcome = "completed", ReasonCode = "camera_management", Reason = "revision=" + state.Revision });
        await db.SaveChangesAsync(); return state;
    }

    public async Task<PipelineManagementState> SelectCameraAsync(SelectManagedCameraRequest request, string actor)
    {
        await using var db = await factory.CreateDbContextAsync();
        var state = await GetStateAsync(db);
        if (!state.IsActive) throw new InvalidOperationException("O modo de gerenciamento nao esta ativo.");
        state.CameraId = request.CameraId.Trim();
        state.StreamProfileId = request.StreamProfileId.Trim();
        state.DraftConfigurationJson = null;
        state.DraftApplied = true;
        state.Revision++; state.UpdatedAt = DateTime.UtcNow;
        db.AdministrativeAudits.Add(new AdministrativeAudit { Actor = actor, Action = "camera_management.select_camera", Target = state.CameraId, Outcome = "completed", ReasonCode = "camera_management", Reason = "profile=" + state.StreamProfileId });
        await db.SaveChangesAsync();
        return state;
    }

    public async Task<PipelineManagementState> ApplyAsync(string actor)
    {
        await using var db = await factory.CreateDbContextAsync(); var state = await GetStateAsync(db);
        if (!state.IsActive) throw new InvalidOperationException("O modo de gerenciamento nao esta ativo.");
        if (string.IsNullOrWhiteSpace(state.DraftConfigurationJson)) throw new InvalidOperationException("Nenhuma calibracao para aplicar.");
        state.DraftApplied = true; state.Revision++; state.UpdatedAt = DateTime.UtcNow;
        db.AdministrativeAudits.Add(new AdministrativeAudit { Actor = actor, Action = "camera_management.apply", Target = "pipeline", Outcome = "completed", ReasonCode = "camera_management", Reason = "revision=" + state.Revision });
        await db.SaveChangesAsync(); return state;
    }

    public async Task<PipelineManagementState> DeactivateAsync(string actor)
    {
        await using var db = await factory.CreateDbContextAsync(); var state = await GetStateAsync(db);
        if (!state.IsActive) return state;
        if (!state.DraftApplied) throw new InvalidOperationException("Aplique ou descarte a calibracao antes de retomar a operacao.");
        state.IsActive = false; state.UpdatedAt = DateTime.UtcNow; state.Revision++;
        db.AdministrativeAudits.Add(new AdministrativeAudit { Actor = actor, Action = "camera_management.deactivate", Target = "pipeline", Outcome = "completed", ReasonCode = "camera_management", Reason = state.Reason });
        await db.SaveChangesAsync(); return state;
    }

    private static bool GeometryValid(Dictionary<string,double> value, string[] keys) => value.Count == keys.Length && keys.All(k => value.TryGetValue(k, out var n) && double.IsFinite(n));
    private static async Task<PipelineManagementState> GetStateAsync(AppDbContext db) => await db.PipelineManagementStates.SingleOrDefaultAsync(x => x.Id == 1) ?? new PipelineManagementState();
}
