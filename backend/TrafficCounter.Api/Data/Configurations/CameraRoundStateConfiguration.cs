using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class CameraRoundStateConfiguration : IEntityTypeConfiguration<CameraRoundState>
{
    public void Configure(EntityTypeBuilder<CameraRoundState> builder)
    {
        builder.HasKey(x => x.CameraId);

        builder.Property(x => x.CameraId).HasMaxLength(128).IsRequired();
        builder.Property(x => x.ActiveStreamProfileId).HasMaxLength(128);
        builder.Property(x => x.LastSourceFingerprint).HasMaxLength(128);
        builder.Property(x => x.LastSourceUrl).HasMaxLength(1024);

        builder.HasIndex(x => x.ActiveStreamProfileId);
    }
}
