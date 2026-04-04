using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class StreamSessionConfiguration : IEntityTypeConfiguration<StreamSession>
{
    public void Configure(EntityTypeBuilder<StreamSession> builder)
    {
        builder.HasKey(e => e.Id);
        builder.Property(e => e.Status).HasConversion<string>().HasMaxLength(32).IsRequired();
        builder.Property(e => e.CountDirection).HasMaxLength(32).IsRequired();
        builder.Property(e => e.RawStreamPath).HasMaxLength(256);
        builder.Property(e => e.ProcessedStreamPath).HasMaxLength(256);
        builder.Property(e => e.FailureReason).HasMaxLength(512);

        builder.HasIndex(e => e.Status);

        builder.HasOne(e => e.CameraSource)
            .WithMany(c => c.Sessions)
            .HasForeignKey(e => e.CameraSourceId)
            .OnDelete(DeleteBehavior.Restrict);
    }
}
