using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class StreamHealthLogConfiguration : IEntityTypeConfiguration<StreamHealthLog>
{
    public void Configure(EntityTypeBuilder<StreamHealthLog> builder)
    {
        builder.HasKey(e => e.Id);
        builder.Property(e => e.Notes).HasMaxLength(256);

        builder.HasOne(e => e.Session)
            .WithMany(s => s.HealthLogs)
            .HasForeignKey(e => e.SessionId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
