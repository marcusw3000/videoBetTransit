using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddReliableEventsAndBetOwnership : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_Bets_TransactionId",
                table: "Bets");

            migrationBuilder.AddColumn<Guid>(
                name: "Revision",
                table: "Rounds",
                nullable: false,
                defaultValue: new Guid("00000000-0000-0000-0000-000000000000"));

            migrationBuilder.CreateTable(
                name: "EventReceipts",
                columns: table => new
                {
                    Id = table.Column<string>(maxLength: 128, nullable: false),
                    RoundId = table.Column<Guid>(nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_EventReceipts", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Bets_PlayerRef_OperatorRef_TransactionId",
                table: "Bets",
                columns: new[] { "PlayerRef", "OperatorRef", "TransactionId" },
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "EventReceipts");

            migrationBuilder.DropIndex(
                name: "IX_Bets_PlayerRef_OperatorRef_TransactionId",
                table: "Bets");

            migrationBuilder.DropColumn(
                name: "Revision",
                table: "Rounds");

            migrationBuilder.CreateIndex(
                name: "IX_Bets_TransactionId",
                table: "Bets",
                column: "TransactionId",
                unique: true);
        }
    }
}
