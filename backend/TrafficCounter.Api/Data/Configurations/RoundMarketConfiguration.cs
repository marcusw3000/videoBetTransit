using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class RoundMarketConfiguration : IEntityTypeConfiguration<RoundMarket>
{
    public void Configure(EntityTypeBuilder<RoundMarket> builder)
    {
        builder.HasKey(m => m.MarketId);

        builder.Property(m => m.MarketType).HasMaxLength(16).IsRequired();
        builder.Property(m => m.Label).HasMaxLength(128).IsRequired();
        builder.Property(m => m.Odds).HasColumnType("numeric(10,4)").IsRequired();

        builder.HasIndex(m => m.RoundId);

        builder.HasOne(m => m.Round)
            .WithMany(r => r.Markets)
            .HasForeignKey(m => m.RoundId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
