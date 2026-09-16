using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Domain.Enums;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<CameraSource> CameraSources => Set<CameraSource>();
    public DbSet<StreamSession> StreamSessions => Set<StreamSession>();
    public DbSet<VehicleCrossingEvent> VehicleCrossingEvents => Set<VehicleCrossingEvent>();
    public DbSet<StreamHealthLog> StreamHealthLogs => Set<StreamHealthLog>();
    public DbSet<RecordingSegment> RecordingSegments => Set<RecordingSegment>();
    public DbSet<Round> Rounds => Set<Round>();
    public DbSet<RoundMarket> RoundMarkets => Set<RoundMarket>();
    public DbSet<RoundEvent> RoundEvents => Set<RoundEvent>();
    public DbSet<CameraRoundState> CameraRoundStates => Set<CameraRoundState>();
    public DbSet<Bet> Bets => Set<Bet>();
    public DbSet<EventReceipt> EventReceipts => Set<EventReceipt>();

    public DbSet<AdministrativeAudit> AdministrativeAudits => Set<AdministrativeAudit>();
    public DbSet<OperationalRecoveryDecision> OperationalRecoveryDecisions => Set<OperationalRecoveryDecision>();
    public DbSet<PipelineManagementState> PipelineManagementStates => Set<PipelineManagementState>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(AppDbContext).Assembly);
        modelBuilder.Entity<AdministrativeAudit>().HasKey(e => e.Id);
        modelBuilder.Entity<AdministrativeAudit>().HasIndex(e => new { e.Target, e.TimestampUtc });
        modelBuilder.Entity<OperationalRecoveryDecision>().HasKey(e => e.Id);
        modelBuilder.Entity<OperationalRecoveryDecision>().Property(e => e.EventId).HasMaxLength(128).IsRequired();
        modelBuilder.Entity<OperationalRecoveryDecision>().Property(e => e.Decision).HasMaxLength(32).IsRequired();
        modelBuilder.Entity<OperationalRecoveryDecision>().Property(e => e.Actor).HasMaxLength(128).IsRequired();
        modelBuilder.Entity<OperationalRecoveryDecision>().Property(e => e.ReasonCode).HasMaxLength(64).IsRequired();
        modelBuilder.Entity<OperationalRecoveryDecision>().Property(e => e.Reason).HasMaxLength(512);
        modelBuilder.Entity<OperationalRecoveryDecision>().HasIndex(e => new { e.EventId, e.TimestampUtc });
        modelBuilder.Entity<CameraRoundState>().Property(e => e.Revision).IsConcurrencyToken();
        modelBuilder.Entity<PipelineManagementState>().HasData(new PipelineManagementState { Id = 1, IsActive = false, Revision = 1, DraftApplied = true, UpdatedAt = DateTime.UnixEpoch });
        modelBuilder.Entity<EventReceipt>().HasKey(e => e.Id);
        modelBuilder.Entity<EventReceipt>().Property(e => e.Id).HasMaxLength(128);
    }

    public override async Task<int> SaveChangesAsync(CancellationToken cancellationToken = default)
    {
        ChangeTracker.DetectChanges();
        foreach (var entry in ChangeTracker.Entries<AdministrativeAudit>())
            if (entry.State is EntityState.Modified or EntityState.Deleted)
                throw new InvalidOperationException("A auditoria e somente de acrescimo.");
        foreach (var entry in ChangeTracker.Entries<OperationalRecoveryDecision>())
            if (entry.State is EntityState.Modified or EntityState.Deleted)
                throw new InvalidOperationException("As decisoes operacionais sao somente de acrescimo.");
        foreach (var entry in ChangeTracker.Entries<CameraRoundState>())
            if (entry.State is EntityState.Added or EntityState.Modified) entry.Entity.Revision = Guid.NewGuid();
        foreach (var entry in ChangeTracker.Entries<Round>())
            if (entry.State == EntityState.Modified &&
                entry.Properties.Any(p => p.IsModified && new[] { nameof(Round.OperationalSnapshotJson), nameof(Round.RulesSnapshotJson),
                    nameof(Round.CameraId), nameof(Round.RoundMode) }.Contains(p.Metadata.Name)))
                throw new InvalidOperationException("Snapshots da rodada sao imutaveis.");
        foreach (var entry in ChangeTracker.Entries<RoundMarket>())
            if (entry.State == EntityState.Deleted || (entry.State == EntityState.Modified &&
                entry.Properties.Any(p => p.IsModified && p.Metadata.Name != nameof(RoundMarket.IsWinner))))
                throw new InvalidOperationException("Parametros do mercado sao imutaveis.");
        var changedRounds = ChangeTracker.Entries<Round>()
            .Where(e => e.State is EntityState.Added or EntityState.Modified).ToList();
        foreach (var entry in changedRounds)
        {
            var round = entry.Entity;
            round.Revision = Guid.NewGuid();
            if (round.Status is not RoundStatus.Settled and not RoundStatus.Void) continue;
            var bets = await Bets.Where(b => b.RoundId == round.RoundId && b.Status == BetStatus.Accepted)
                .ToListAsync(cancellationToken);
            foreach (var bet in bets) ApplyResult(bet, round);
        }
        // EF commits the round, its events and all affected bets in one transaction.
        return await base.SaveChangesAsync(cancellationToken);
    }

    public static void ApplyResult(Bet bet, Round round)
    {
        if (round.Status == RoundStatus.Void)
        { bet.Status = BetStatus.Void; bet.VoidedAt = round.VoidedAt; }
        else if (round.Status == RoundStatus.Settled && round.FinalCount.HasValue)
        {
            bet.Status = BetService.EvaluateBet(bet, round.FinalCount.Value)
                ? BetStatus.SettledWin : BetStatus.SettledLoss;
            bet.SettledAt = round.SettledAt;
        }
    }
}
