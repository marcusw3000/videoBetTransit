using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;
public sealed class PipelineManagementStateConfiguration : IEntityTypeConfiguration<PipelineManagementState>
{
    public void Configure(EntityTypeBuilder<PipelineManagementState> builder)
    {
        builder.HasKey(x => x.Id);
        builder.Property(x => x.CameraId).HasMaxLength(128);
        builder.Property(x => x.StreamProfileId).HasMaxLength(128);
        builder.Property(x => x.Reason).HasMaxLength(512);
        builder.Property(x => x.ActivatedBy).HasMaxLength(128);
        builder.Property(x => x.DraftConfigurationJson).HasMaxLength(8192);
        builder.Property(x => x.Revision).IsConcurrencyToken();
    }
}
