using System.Net.Http.Json;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Options;

namespace TrafficCounter.Api.Services;

public class OrchestratorResult
{
    public bool Success { get; set; }
    public string? ErrorMessage { get; set; }

    public static OrchestratorResult Ok() => new() { Success = true };
    public static OrchestratorResult Fail(string msg) => new() { Success = false, ErrorMessage = msg };
}

public class PipelineOrchestratorService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IMediaMtxClient _mediaMtx;
    private readonly IHttpClientFactory _httpFactory;
    private readonly VisionWorkerOptions _visionOptions;
    private readonly ILogger<PipelineOrchestratorService> _logger;

    // Per-session semaphore to prevent concurrent start/stop on same session
    private readonly Dictionary<Guid, SemaphoreSlim> _locks = new();
    private readonly object _lockMapLock = new();

    public PipelineOrchestratorService(
        IServiceScopeFactory scopeFactory,
        IMediaMtxClient mediaMtx,
        IHttpClientFactory httpFactory,
        IOptions<VisionWorkerOptions> visionOptions,
        ILogger<PipelineOrchestratorService> logger)
    {
        _scopeFactory = scopeFactory;
        _mediaMtx = mediaMtx;
        _httpFactory = httpFactory;
        _visionOptions = visionOptions.Value;
        _logger = logger;
    }

    public async Task<OrchestratorResult> StartPipelineAsync(Guid sessionId, CancellationToken ct = default)
    {
        var sem = GetSemaphore(sessionId);
        await sem.WaitAsync(ct);
        try
        {
            using var scope = _scopeFactory.CreateScope();
            var sessionService = scope.ServiceProvider.GetRequiredService<StreamSessionService>();

            var session = await sessionService.GetAsync(sessionId);
            if (session is null)
                return OrchestratorResult.Fail("Session not found.");

            if (session.Status != SessionStatus.Ready.ToString())
                return OrchestratorResult.Fail($"Session must be in Ready state to start (current: {session.Status}).");

            await sessionService.TransitionStatusAsync(sessionId, SessionStatus.Starting);

            var rawPath = $"raw/{sessionId:N}";
            var processedPath = $"processed/{sessionId:N}";

            // Tell MediaMTX to pull the raw stream
            var added = await _mediaMtx.AddPathAsync(rawPath, session.SourceUrl, ct);
            if (!added)
            {
                await sessionService.TransitionStatusAsync(sessionId, SessionStatus.Failed,
                    "Failed to register raw stream path in MediaMTX.");
                return OrchestratorResult.Fail("MediaMTX path creation failed.");
            }

            await sessionService.UpdatePathsAsync(sessionId, rawPath, processedPath);

            // Tell vision worker to start
            var workerOk = await StartVisionWorkerAsync(sessionId, session, rawPath, processedPath, ct);
            if (!workerOk)
            {
                await _mediaMtx.RemovePathAsync(rawPath, ct);
                await sessionService.TransitionStatusAsync(sessionId, SessionStatus.Failed,
                    "Vision worker failed to start.");
                return OrchestratorResult.Fail("Vision worker start failed.");
            }

            // Transition to Running immediately (worker will send health reports to confirm)
            await sessionService.TransitionStatusAsync(sessionId, SessionStatus.Running);
            return OrchestratorResult.Ok();
        }
        finally
        {
            sem.Release();
        }
    }

    public async Task StopPipelineAsync(Guid sessionId, CancellationToken ct = default)
    {
        var sem = GetSemaphore(sessionId);
        await sem.WaitAsync(ct);
        try
        {
            using var scope = _scopeFactory.CreateScope();
            var sessionService = scope.ServiceProvider.GetRequiredService<StreamSessionService>();

            var session = await sessionService.GetAsync(sessionId);
            if (session is null) return;

            await StopVisionWorkerAsync(sessionId, ct);

            if (session.RawStreamPath is not null)
                await _mediaMtx.RemovePathAsync(session.RawStreamPath, ct);
            if (session.ProcessedStreamPath is not null)
                await _mediaMtx.RemovePathAsync(session.ProcessedStreamPath, ct);

            var status = Enum.Parse<SessionStatus>(session.Status);
            if (status is not SessionStatus.Stopped and not SessionStatus.Failed)
                await sessionService.TransitionStatusAsync(sessionId, SessionStatus.Stopped);
        }
        finally
        {
            sem.Release();
        }
    }

    private async Task<bool> StartVisionWorkerAsync(
        Guid sessionId, StreamSessionResponse session,
        string rawPath, string processedPath,
        CancellationToken ct)
    {
        try
        {
            var http = _httpFactory.CreateClient();
            var url = _visionOptions.BaseUrl + _visionOptions.StartPipelinePath;
            var body = new
            {
                sessionId = sessionId.ToString(),
                rawStreamPath = rawPath,
                processedStreamPath = processedPath,
                countLine = new
                {
                    x1 = session.CountLine.X1,
                    y1 = session.CountLine.Y1,
                    x2 = session.CountLine.X2,
                    y2 = session.CountLine.Y2,
                },
                direction = session.CountDirection,
            };

            var response = await http.PostAsJsonAsync(url, body, ct);
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error starting vision worker for session {SessionId}", sessionId);
            return false;
        }
    }

    private async Task StopVisionWorkerAsync(Guid sessionId, CancellationToken ct)
    {
        try
        {
            var http = _httpFactory.CreateClient();
            var url = _visionOptions.BaseUrl + _visionOptions.StopPipelinePath;
            await http.PostAsJsonAsync(url, new { sessionId = sessionId.ToString() }, ct);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Error stopping vision worker for session {SessionId}", sessionId);
        }
    }

    private SemaphoreSlim GetSemaphore(Guid sessionId)
    {
        lock (_lockMapLock)
        {
            if (!_locks.TryGetValue(sessionId, out var sem))
            {
                sem = new SemaphoreSlim(1, 1);
                _locks[sessionId] = sem;
            }
            return sem;
        }
    }
}
