using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class CameraSourceConfiguration : IEntityTypeConfiguration<CameraSource>
{
    public void Configure(EntityTypeBuilder<CameraSource> builder)
    {
        builder.HasKey(e => e.Id);
        builder.Property(e => e.Name).HasMaxLength(128).IsRequired();
        builder.Property(e => e.SourceUrl).HasMaxLength(512).IsRequired();
        builder.Property(e => e.Protocol).HasConversion<string>().HasMaxLength(16).IsRequired();
        builder.Property(e => e.CreatedAt).IsRequired();
    }
}
