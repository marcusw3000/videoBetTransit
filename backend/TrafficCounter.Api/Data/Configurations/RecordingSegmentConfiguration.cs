using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class RecordingSegmentConfiguration : IEntityTypeConfiguration<RecordingSegment>
{
    public void Configure(EntityTypeBuilder<RecordingSegment> builder)
    {
        builder.HasKey(e => e.Id);
        builder.Property(e => e.SegmentType).HasMaxLength(16).IsRequired();
        builder.Property(e => e.FilePath).HasMaxLength(512).IsRequired();

        builder.HasOne(e => e.Session)
            .WithMany(s => s.RecordingSegments)
            .HasForeignKey(e => e.SessionId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
