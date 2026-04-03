using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Contracts.Requests;
using TrafficCounter.Api.Contracts.Responses;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Hubs;

namespace TrafficCounter.Api.Services;

public class StreamSessionService
{
    private static readonly Dictionary<SessionStatus, SessionStatus[]> AllowedTransitions = new()
    {
        [SessionStatus.Created]          = [SessionStatus.ValidatingSource],
        [SessionStatus.ValidatingSource] = [SessionStatus.Ready, SessionStatus.Failed],
        [SessionStatus.Ready]            = [SessionStatus.Starting],
        [SessionStatus.Starting]         = [SessionStatus.Running, SessionStatus.Failed],
        [SessionStatus.Running]          = [SessionStatus.Degraded, SessionStatus.Stopped, SessionStatus.Failed],
        [SessionStatus.Degraded]         = [SessionStatus.Running, SessionStatus.Stopped, SessionStatus.Failed],
        [SessionStatus.Stopped]          = [],
        [SessionStatus.Failed]           = [],
    };

    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly IHubContext<MetricsHub> _hub;

    public StreamSessionService(IDbContextFactory<AppDbContext> dbFactory, IHubContext<MetricsHub> hub)
    {
        _dbFactory = dbFactory;
        _hub = hub;
    }

    public async Task<StreamSessionResponse> CreateAsync(CreateStreamRequest request)
    {
        if (!Enum.TryParse<SourceProtocol>(request.SourceProtocol, ignoreCase: true, out var protocol))
            throw new ArgumentException($"Invalid protocol '{request.SourceProtocol}'.");

        await using var db = await _dbFactory.CreateDbContextAsync();

        var source = new CameraSource
        {
            Id = Guid.NewGuid(),
            Name = request.Name,
            SourceUrl = request.SourceUrl,
            Protocol = protocol,
            CreatedAt = DateTime.UtcNow,
        };

        var session = new StreamSession
        {
            Id = Guid.NewGuid(),
            CameraSource = source,
            Status = SessionStatus.Created,
            CountLineX1 = request.CountLine.X1,
            CountLineY1 = request.CountLine.Y1,
            CountLineX2 = request.CountLine.X2,
            CountLineY2 = request.CountLine.Y2,
            CountDirection = request.Direction,
            TotalCount = 0,
            CreatedAt = DateTime.UtcNow,
        };

        db.CameraSources.Add(source);
        db.StreamSessions.Add(session);
        await db.SaveChangesAsync();

        return ToResponse(session);
    }

    public async Task<StreamSessionResponse?> GetAsync(Guid sessionId)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var session = await db.StreamSessions
            .Include(s => s.CameraSource)
            .FirstOrDefaultAsync(s => s.Id == sessionId);

        return session is null ? null : ToResponse(session);
    }

    public async Task<SessionMetricsResponse?> GetMetricsAsync(Guid sessionId)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var session = await db.StreamSessions.FindAsync(sessionId);
        if (session is null) return null;

        var oneMinuteAgo = DateTime.UtcNow.AddMinutes(-1);
        var lastMinuteCount = await db.VehicleCrossingEvents
            .CountAsync(e => e.SessionId == sessionId && e.TimestampUtc >= oneMinuteAgo);

        return new SessionMetricsResponse
        {
            SessionId = session.Id,
            TotalCount = session.TotalCount,
            LastMinuteCount = lastMinuteCount,
            Status = session.Status.ToString(),
        };
    }

    public async Task<IList<StreamSessionResponse>> ListActiveAsync()
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var sessions = await db.StreamSessions
            .Include(s => s.CameraSource)
            .Where(s => s.Status == SessionStatus.Running || s.Status == SessionStatus.Degraded
                     || s.Status == SessionStatus.Starting || s.Status == SessionStatus.ValidatingSource)
            .ToListAsync();

        return sessions.Select(ToResponse).ToList();
    }

    public async Task<StreamSessionResponse> TransitionStatusAsync(
        Guid sessionId, SessionStatus next, string? failureReason = null)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var session = await db.StreamSessions
            .Include(s => s.CameraSource)
            .FirstOrDefaultAsync(s => s.Id == sessionId)
            ?? throw new KeyNotFoundException($"Session {sessionId} not found.");

        var allowed = AllowedTransitions[session.Status];
        if (!allowed.Contains(next))
            throw new InvalidOperationException(
                $"Cannot transition from {session.Status} to {next}.");

        session.Status = next;

        if (next == SessionStatus.Running && session.StartedAt is null)
            session.StartedAt = DateTime.UtcNow;
        if (next is SessionStatus.Stopped or SessionStatus.Failed)
            session.StoppedAt = DateTime.UtcNow;
        if (next == SessionStatus.Failed && failureReason is not null)
            session.FailureReason = failureReason;

        await db.SaveChangesAsync();

        var response = ToResponse(session);
        await _hub.Clients.Group($"session:{sessionId}")
            .SendAsync("session_status_changed", response);

        return response;
    }

    public async Task<IList<CrossingEventResponse>> GetCrossingEventsAsync(Guid sessionId, int page, int pageSize)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var events = await db.VehicleCrossingEvents
            .Where(e => e.SessionId == sessionId)
            .OrderByDescending(e => e.TimestampUtc)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(e => new CrossingEventResponse
            {
                Id = e.Id,
                SessionId = e.SessionId,
                TimestampUtc = e.TimestampUtc,
                TrackId = e.TrackId,
                ObjectClass = e.ObjectClass,
                Direction = e.Direction,
                LineId = e.LineId,
                FrameNumber = e.FrameNumber,
                Confidence = e.Confidence,
                EventHash = e.EventHash,
            })
            .ToListAsync();

        return events;
    }

    public async Task UpdatePathsAsync(Guid sessionId, string rawPath, string processedPath)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();
        var session = await db.StreamSessions.FindAsync(sessionId)
            ?? throw new KeyNotFoundException($"Session {sessionId} not found.");

        session.RawStreamPath = rawPath;
        session.ProcessedStreamPath = processedPath;
        await db.SaveChangesAsync();
    }

    private static StreamSessionResponse ToResponse(StreamSession s) => new()
    {
        Id = s.Id,
        Status = s.Status.ToString(),
        CameraName = s.CameraSource.Name,
        SourceUrl = s.CameraSource.SourceUrl,
        SourceProtocol = s.CameraSource.Protocol.ToString(),
        TotalCount = s.TotalCount,
        RawStreamPath = s.RawStreamPath,
        ProcessedStreamPath = s.ProcessedStreamPath,
        CountLine = new CountLineResponse
        {
            X1 = s.CountLineX1, Y1 = s.CountLineY1,
            X2 = s.CountLineX2, Y2 = s.CountLineY2
        },
        CountDirection = s.CountDirection,
        CreatedAt = s.CreatedAt,
        StartedAt = s.StartedAt,
        StoppedAt = s.StoppedAt,
        FailureReason = s.FailureReason,
    };
}
