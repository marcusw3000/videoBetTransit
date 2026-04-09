using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class RoundEventConfiguration : IEntityTypeConfiguration<RoundEvent>
{
    public void Configure(EntityTypeBuilder<RoundEvent> builder)
    {
        builder.HasKey(e => e.Id);
        builder.Property(e => e.EventType).HasMaxLength(64).IsRequired();
        builder.Property(e => e.RoundStatus).HasMaxLength(32).IsRequired();
        builder.Property(e => e.Reason).HasMaxLength(512);
        builder.Property(e => e.Source).HasMaxLength(64);

        builder.HasIndex(e => new { e.RoundId, e.TimestampUtc });
        builder.HasIndex(e => new { e.RoundId, e.EventType });

        builder.HasOne(e => e.Round)
            .WithMany(r => r.Events)
            .HasForeignKey(e => e.RoundId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
