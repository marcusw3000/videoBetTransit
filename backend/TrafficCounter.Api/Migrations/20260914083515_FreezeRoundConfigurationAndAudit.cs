using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class FreezeRoundConfigurationAndAudit : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "OperationalSnapshotJson",
                table: "Rounds",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "RulesSnapshotJson",
                table: "Rounds",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "VoidReasonCode",
                table: "Rounds",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "OperationalConfigurationJson",
                table: "CameraRoundStates",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<Guid>(
                name: "Revision",
                table: "CameraRoundStates",
                type: "TEXT",
                nullable: false,
                defaultValue: new Guid("00000000-0000-0000-0000-000000000000"));

            migrationBuilder.CreateTable(
                name: "AdministrativeAudits",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    TimestampUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    Actor = table.Column<string>(type: "TEXT", nullable: false),
                    Action = table.Column<string>(type: "TEXT", nullable: false),
                    Target = table.Column<string>(type: "TEXT", nullable: false),
                    Outcome = table.Column<string>(type: "TEXT", nullable: false),
                    ReasonCode = table.Column<string>(type: "TEXT", nullable: true),
                    Reason = table.Column<string>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_AdministrativeAudits", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_AdministrativeAudits_Target_TimestampUtc",
                table: "AdministrativeAudits",
                columns: new[] { "Target", "TimestampUtc" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "AdministrativeAudits");

            migrationBuilder.DropColumn(
                name: "OperationalSnapshotJson",
                table: "Rounds");

            migrationBuilder.DropColumn(
                name: "RulesSnapshotJson",
                table: "Rounds");

            migrationBuilder.DropColumn(
                name: "VoidReasonCode",
                table: "Rounds");

            migrationBuilder.DropColumn(
                name: "OperationalConfigurationJson",
                table: "CameraRoundStates");

            migrationBuilder.DropColumn(
                name: "Revision",
                table: "CameraRoundStates");
        }
    }
}
