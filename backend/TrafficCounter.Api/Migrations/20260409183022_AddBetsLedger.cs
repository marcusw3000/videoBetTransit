using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddBetsLedger : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Bets",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    ProviderBetId = table.Column<string>(type: "TEXT", maxLength: 64, nullable: false),
                    TransactionId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    GameSessionId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    RoundId = table.Column<Guid>(type: "TEXT", nullable: false),
                    CameraId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    RoundMode = table.Column<string>(type: "TEXT", maxLength: 32, nullable: false),
                    MarketId = table.Column<Guid>(type: "TEXT", nullable: false),
                    MarketType = table.Column<string>(type: "TEXT", maxLength: 16, nullable: false),
                    MarketLabel = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    Odds = table.Column<decimal>(type: "numeric(10,4)", nullable: false),
                    Threshold = table.Column<int>(type: "INTEGER", nullable: true),
                    Min = table.Column<int>(type: "INTEGER", nullable: true),
                    Max = table.Column<int>(type: "INTEGER", nullable: true),
                    TargetValue = table.Column<int>(type: "INTEGER", nullable: true),
                    StakeAmount = table.Column<decimal>(type: "numeric(18,2)", nullable: false),
                    PotentialPayout = table.Column<decimal>(type: "numeric(18,2)", nullable: false),
                    Currency = table.Column<string>(type: "TEXT", maxLength: 16, nullable: false),
                    Status = table.Column<string>(type: "TEXT", maxLength: 32, nullable: false),
                    PlacedAt = table.Column<DateTime>(type: "TEXT", nullable: false),
                    AcceptedAt = table.Column<DateTime>(type: "TEXT", nullable: false),
                    SettledAt = table.Column<DateTime>(type: "TEXT", nullable: true),
                    VoidedAt = table.Column<DateTime>(type: "TEXT", nullable: true),
                    RollbackOfTransactionId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: true),
                    PlayerRef = table.Column<string>(type: "TEXT", maxLength: 128, nullable: true),
                    OperatorRef = table.Column<string>(type: "TEXT", maxLength: 128, nullable: true),
                    MetadataJson = table.Column<string>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Bets", x => x.Id);
                    table.ForeignKey(
                        name: "FK_Bets_Rounds_RoundId",
                        column: x => x.RoundId,
                        principalTable: "Rounds",
                        principalColumn: "RoundId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Bets_GameSessionId",
                table: "Bets",
                column: "GameSessionId");

            migrationBuilder.CreateIndex(
                name: "IX_Bets_ProviderBetId",
                table: "Bets",
                column: "ProviderBetId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Bets_RoundId",
                table: "Bets",
                column: "RoundId");

            migrationBuilder.CreateIndex(
                name: "IX_Bets_RoundId_Status",
                table: "Bets",
                columns: new[] { "RoundId", "Status" });

            migrationBuilder.CreateIndex(
                name: "IX_Bets_TransactionId",
                table: "Bets",
                column: "TransactionId",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "Bets");
        }
    }
}
