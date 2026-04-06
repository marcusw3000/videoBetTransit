using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<CameraSource> CameraSources => Set<CameraSource>();
    public DbSet<StreamSession> StreamSessions => Set<StreamSession>();
    public DbSet<VehicleCrossingEvent> VehicleCrossingEvents => Set<VehicleCrossingEvent>();
    public DbSet<StreamHealthLog> StreamHealthLogs => Set<StreamHealthLog>();
    public DbSet<RecordingSegment> RecordingSegments => Set<RecordingSegment>();
    public DbSet<Round> Rounds => Set<Round>();
    public DbSet<RoundMarket> RoundMarkets => Set<RoundMarket>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(AppDbContext).Assembly);
    }
}
