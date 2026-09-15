using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using TrafficCounter.Api.Data;

namespace TrafficCounter.Api.Migrations;

[DbContext(typeof(AppDbContext))]
[Migration("20260424030000_AddCameraRoundStateActivationReadiness")]
public sealed class AddCameraRoundStateActivationReadiness : Migration
{
    protected override void Up(MigrationBuilder builder)
    {
        builder.AddColumn<string>("ActivationPhase", "CameraRoundStates", maxLength: 32, nullable: false, defaultValue: "ready");
        builder.AddColumn<bool>("ReadyForRounds", "CameraRoundStates", nullable: false, defaultValue: true);
        builder.AddColumn<bool>("FrontendAckReceived", "CameraRoundStates", nullable: false, defaultValue: false);
        foreach (var column in new[] { "ExpectedFrontendAckNonce", "ActivationSessionId", "LastReadyActivationSessionId", "LastFrontendAckSessionId" })
            builder.AddColumn<string>(column, "CameraRoundStates", maxLength: 128, nullable: true);
        builder.AddColumn<DateTime>("FrontendAckedAt", "CameraRoundStates", nullable: true);
        builder.AddColumn<DateTime>("ActivationRequestedAt", "CameraRoundStates", nullable: true);
    }
    protected override void Down(MigrationBuilder builder)
    {
        foreach (var column in new[] { "ActivationPhase", "ReadyForRounds", "FrontendAckReceived", "ExpectedFrontendAckNonce",
            "ActivationSessionId", "LastReadyActivationSessionId", "LastFrontendAckSessionId", "FrontendAckedAt", "ActivationRequestedAt" })
            builder.DropColumn(column, "CameraRoundStates");
    }
}
