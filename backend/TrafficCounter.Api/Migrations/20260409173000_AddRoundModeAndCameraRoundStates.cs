using System;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using TrafficCounter.Api.Data;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    [DbContext(typeof(AppDbContext))]
    [Migration("20260409173000_AddRoundModeAndCameraRoundStates")]
    public partial class AddRoundModeAndCameraRoundStates : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "RoundMode",
                table: "Rounds",
                type: "TEXT",
                nullable: false,
                defaultValue: "Normal");

            migrationBuilder.CreateTable(
                name: "CameraRoundStates",
                columns: table => new
                {
                    CameraId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: false),
                    ActiveStreamProfileId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: true),
                    RoundsSinceProfileSwitch = table.Column<int>(type: "INTEGER", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "TEXT", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "TEXT", nullable: false),
                    LastProfileChangedAt = table.Column<DateTime>(type: "TEXT", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CameraRoundStates", x => x.CameraId);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CameraRoundStates_ActiveStreamProfileId",
                table: "CameraRoundStates",
                column: "ActiveStreamProfileId");
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "CameraRoundStates");

            migrationBuilder.DropColumn(
                name: "RoundMode",
                table: "Rounds");
        }
    }
}
