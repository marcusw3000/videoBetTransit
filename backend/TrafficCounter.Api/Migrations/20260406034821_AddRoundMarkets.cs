using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddRoundMarkets : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "VoidReason",
                table: "Rounds",
                type: "character varying(512)",
                maxLength: 512,
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "VoidedAt",
                table: "Rounds",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.CreateTable(
                name: "RoundMarkets",
                columns: table => new
                {
                    MarketId = table.Column<Guid>(type: "uuid", nullable: false),
                    RoundId = table.Column<Guid>(type: "uuid", nullable: false),
                    MarketType = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    Label = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    Odds = table.Column<decimal>(type: "numeric(10,4)", nullable: false),
                    Threshold = table.Column<int>(type: "integer", nullable: true),
                    Min = table.Column<int>(type: "integer", nullable: true),
                    Max = table.Column<int>(type: "integer", nullable: true),
                    TargetValue = table.Column<int>(type: "integer", nullable: true),
                    IsWinner = table.Column<bool>(type: "boolean", nullable: true),
                    SortOrder = table.Column<int>(type: "integer", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RoundMarkets", x => x.MarketId);
                    table.ForeignKey(
                        name: "FK_RoundMarkets_Rounds_RoundId",
                        column: x => x.RoundId,
                        principalTable: "Rounds",
                        principalColumn: "RoundId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_RoundMarkets_RoundId",
                table: "RoundMarkets",
                column: "RoundId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "RoundMarkets");

            migrationBuilder.DropColumn(
                name: "VoidReason",
                table: "Rounds");

            migrationBuilder.DropColumn(
                name: "VoidedAt",
                table: "Rounds");
        }
    }
}
