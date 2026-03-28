using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class InitialSqlitePersistence : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "CameraConfigs",
                columns: table => new
                {
                    CameraId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    RoiX = table.Column<int>(type: "INTEGER", nullable: false),
                    RoiY = table.Column<int>(type: "INTEGER", nullable: false),
                    RoiW = table.Column<int>(type: "INTEGER", nullable: false),
                    RoiH = table.Column<int>(type: "INTEGER", nullable: false),
                    CountLineX1 = table.Column<int>(type: "INTEGER", nullable: false),
                    CountLineY1 = table.Column<int>(type: "INTEGER", nullable: false),
                    CountLineX2 = table.Column<int>(type: "INTEGER", nullable: false),
                    CountLineY2 = table.Column<int>(type: "INTEGER", nullable: false),
                    CountDirection = table.Column<string>(type: "TEXT", maxLength: 16, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CameraConfigs", x => x.CameraId);
                });

            migrationBuilder.CreateTable(
                name: "CountEvents",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "TEXT", nullable: false),
                    CameraId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    RoundId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    TrackId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    VehicleType = table.Column<string>(type: "TEXT", maxLength: 64, nullable: false),
                    CrossedAt = table.Column<string>(type: "TEXT", maxLength: 64, nullable: false),
                    SnapshotUrl = table.Column<string>(type: "TEXT", maxLength: 512, nullable: false),
                    TotalCount = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CountEvents", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Rounds",
                columns: table => new
                {
                    Id = table.Column<string>(type: "TEXT", nullable: false),
                    Status = table.Column<string>(type: "TEXT", maxLength: 32, nullable: false),
                    CurrentCount = table.Column<int>(type: "INTEGER", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "TEXT", nullable: false),
                    EndsAt = table.Column<DateTime>(type: "TEXT", nullable: false),
                    FinalCount = table.Column<int>(type: "INTEGER", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Rounds", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "RoundRanges",
                columns: table => new
                {
                    Id = table.Column<string>(type: "TEXT", nullable: false),
                    RoundId = table.Column<string>(type: "TEXT", nullable: false),
                    Label = table.Column<string>(type: "TEXT", maxLength: 64, nullable: false),
                    Min = table.Column<int>(type: "INTEGER", nullable: false),
                    Max = table.Column<int>(type: "INTEGER", nullable: false),
                    Odds = table.Column<double>(type: "REAL", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RoundRanges", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RoundRanges_Rounds_RoundId",
                        column: x => x.RoundId,
                        principalTable: "Rounds",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CountEvents_RoundId_TrackId",
                table: "CountEvents",
                columns: new[] { "RoundId", "TrackId" });

            migrationBuilder.CreateIndex(
                name: "IX_RoundRanges_RoundId",
                table: "RoundRanges",
                column: "RoundId");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "CameraConfigs");

            migrationBuilder.DropTable(
                name: "CountEvents");

            migrationBuilder.DropTable(
                name: "RoundRanges");

            migrationBuilder.DropTable(
                name: "Rounds");
        }
    }
}
