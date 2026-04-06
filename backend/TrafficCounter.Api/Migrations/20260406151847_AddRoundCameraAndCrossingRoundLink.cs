using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddRoundCameraAndCrossingRoundLink : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<Guid>(
                name: "RoundId",
                table: "VehicleCrossingEvents",
                type: "uuid",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "CameraId",
                table: "Rounds",
                type: "character varying(128)",
                maxLength: 128,
                nullable: false,
                defaultValue: "");

            migrationBuilder.CreateIndex(
                name: "IX_VehicleCrossingEvents_RoundId",
                table: "VehicleCrossingEvents",
                column: "RoundId");

            migrationBuilder.CreateIndex(
                name: "IX_Rounds_CameraId_Status",
                table: "Rounds",
                columns: new[] { "CameraId", "Status" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_VehicleCrossingEvents_RoundId",
                table: "VehicleCrossingEvents");

            migrationBuilder.DropIndex(
                name: "IX_Rounds_CameraId_Status",
                table: "Rounds");

            migrationBuilder.DropColumn(
                name: "RoundId",
                table: "VehicleCrossingEvents");

            migrationBuilder.DropColumn(
                name: "CameraId",
                table: "Rounds");
        }
    }
}
