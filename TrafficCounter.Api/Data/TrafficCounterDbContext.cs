using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Models;

namespace TrafficCounter.Api.Data;

public class TrafficCounterDbContext : DbContext
{
    public TrafficCounterDbContext(DbContextOptions<TrafficCounterDbContext> options)
        : base(options)
    {
    }

    public DbSet<Round> Rounds => Set<Round>();
    public DbSet<RoundRange> RoundRanges => Set<RoundRange>();
    public DbSet<CountEvent> CountEvents => Set<CountEvent>();
    public DbSet<CameraConfig> CameraConfigs => Set<CameraConfig>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Round>(entity =>
        {
            entity.HasKey(x => x.Id);
            entity.Property(x => x.DisplayName).HasMaxLength(64);
            entity.Property(x => x.Status).HasMaxLength(32);
            entity.Property(x => x.VoidReason).HasMaxLength(256);
            entity.HasMany(x => x.Ranges)
                .WithOne()
                .HasForeignKey(x => x.RoundId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<RoundRange>(entity =>
        {
            entity.HasKey(x => x.Id);
            entity.Property(x => x.MarketType).HasMaxLength(24);
            entity.Property(x => x.Label).HasMaxLength(64);
        });

        modelBuilder.Entity<CountEvent>(entity =>
        {
            entity.HasKey(x => x.Id);
            entity.Property(x => x.CameraId).HasMaxLength(128);
            entity.Property(x => x.RoundId).HasMaxLength(128);
            entity.Property(x => x.TrackId).HasMaxLength(128);
            entity.Property(x => x.VehicleType).HasMaxLength(64);
            entity.Property(x => x.CrossedAt).HasMaxLength(64);
            entity.Property(x => x.SnapshotUrl).HasMaxLength(512);
            entity.HasIndex(x => new { x.RoundId, x.TrackId });
        });

        modelBuilder.Entity<CameraConfig>(entity =>
        {
            entity.HasKey(x => x.CameraId);
            entity.Property(x => x.CameraId).HasMaxLength(128);
            entity.Property(x => x.CountDirection).HasMaxLength(16);
        });
    }
}
