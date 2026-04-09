using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using TrafficCounter.Api.Domain.Entities;

namespace TrafficCounter.Api.Data.Configurations;

public class BetConfiguration : IEntityTypeConfiguration<Bet>
{
    public void Configure(EntityTypeBuilder<Bet> builder)
    {
        builder.HasKey(b => b.Id);

        builder.Property(b => b.ProviderBetId).HasMaxLength(64).IsRequired();
        builder.Property(b => b.TransactionId).HasMaxLength(128).IsRequired();
        builder.Property(b => b.GameSessionId).HasMaxLength(128).IsRequired();
        builder.Property(b => b.CameraId).HasMaxLength(128).IsRequired();
        builder.Property(b => b.RoundMode).HasConversion<string>().HasMaxLength(32).IsRequired();
        builder.Property(b => b.MarketType).HasMaxLength(16).IsRequired();
        builder.Property(b => b.MarketLabel).HasMaxLength(128).IsRequired();
        builder.Property(b => b.Odds).HasColumnType("numeric(10,4)").IsRequired();
        builder.Property(b => b.StakeAmount).HasColumnType("numeric(18,2)").IsRequired();
        builder.Property(b => b.PotentialPayout).HasColumnType("numeric(18,2)").IsRequired();
        builder.Property(b => b.Currency).HasMaxLength(16).IsRequired();
        builder.Property(b => b.Status).HasConversion<string>().HasMaxLength(32).IsRequired();
        builder.Property(b => b.RollbackOfTransactionId).HasMaxLength(128);
        builder.Property(b => b.PlayerRef).HasMaxLength(128);
        builder.Property(b => b.OperatorRef).HasMaxLength(128);

        builder.HasIndex(b => b.ProviderBetId).IsUnique();
        builder.HasIndex(b => b.TransactionId).IsUnique();
        builder.HasIndex(b => b.RoundId);
        builder.HasIndex(b => b.GameSessionId);
        builder.HasIndex(b => new { b.RoundId, b.Status });

        builder.HasOne(b => b.Round)
            .WithMany(r => r.Bets)
            .HasForeignKey(b => b.RoundId)
            .OnDelete(DeleteBehavior.Cascade);
    }
}
