using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class VehicleCrossingEventConfiguration : IEntityTypeConfiguration<VehicleCrossingEvent>
{
    public void Configure(EntityTypeBuilder<VehicleCrossingEvent> builder)
    {
        builder.HasKey(e => e.Id);
        builder.Property(e => e.CameraId).HasMaxLength(128).IsRequired();
        builder.Property(e => e.ObjectClass).HasMaxLength(32).IsRequired();
        builder.Property(e => e.Direction).HasMaxLength(32).IsRequired();
        builder.Property(e => e.LineId).HasMaxLength(64).IsRequired();
        builder.Property(e => e.SnapshotUrl).HasMaxLength(512);
        builder.Property(e => e.Source).HasMaxLength(64);
        builder.Property(e => e.StreamProfileId).HasMaxLength(128);
        builder.Property(e => e.PreviousEventHash).HasMaxLength(128);
        builder.Property(e => e.EventHash).HasMaxLength(128).IsRequired();

        builder.HasIndex(e => new { e.SessionId, e.TimestampUtc });
        builder.HasIndex(e => new { e.RoundId, e.TimestampUtc });
        builder.HasIndex(e => e.RoundId);
        builder.HasIndex(e => e.EventHash);

        builder.HasOne(e => e.Session)
            .WithMany(s => s.CrossingEvents)
            .HasForeignKey(e => e.SessionId)
            .OnDelete(DeleteBehavior.SetNull);
    }
}
