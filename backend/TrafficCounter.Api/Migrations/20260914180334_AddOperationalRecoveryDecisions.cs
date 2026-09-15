using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddOperationalRecoveryDecisions : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "OperationalRecoveryDecisions",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    TimestampUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    EventId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    Decision = table.Column<string>(type: "TEXT", maxLength: 32, nullable: false),
                    Actor = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    ReasonCode = table.Column<string>(type: "TEXT", maxLength: 64, nullable: false),
                    Reason = table.Column<string>(type: "TEXT", maxLength: 512, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_OperationalRecoveryDecisions", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_OperationalRecoveryDecisions_EventId_TimestampUtc",
                table: "OperationalRecoveryDecisions",
                columns: new[] { "EventId", "TimestampUtc" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "OperationalRecoveryDecisions");
        }
    }
}
