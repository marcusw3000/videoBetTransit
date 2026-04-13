using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddCameraRoundStateSourceSnapshot : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "LastSourceChangedAt",
                table: "CameraRoundStates",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "LastSourceFingerprint",
                table: "CameraRoundStates",
                type: "TEXT",
                maxLength: 128,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "LastSourceUrl",
                table: "CameraRoundStates",
                type: "TEXT",
                maxLength: 1024,
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "LastSourceChangedAt",
                table: "CameraRoundStates");

            migrationBuilder.DropColumn(
                name: "LastSourceFingerprint",
                table: "CameraRoundStates");

            migrationBuilder.DropColumn(
                name: "LastSourceUrl",
                table: "CameraRoundStates");
        }
    }
}
