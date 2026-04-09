using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddCrossingEventAuditFieldsAndTimelineSupport : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "CameraId",
                table: "VehicleCrossingEvents",
                type: "TEXT",
                maxLength: 128,
                nullable: false,
                defaultValue: "");

            migrationBuilder.AddColumn<string>(
                name: "SnapshotUrl",
                table: "VehicleCrossingEvents",
                type: "TEXT",
                maxLength: 512,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Source",
                table: "VehicleCrossingEvents",
                type: "TEXT",
                maxLength: 64,
                nullable: true);

            migrationBuilder.CreateIndex(
                name: "IX_VehicleCrossingEvents_RoundId_TimestampUtc",
                table: "VehicleCrossingEvents",
                columns: new[] { "RoundId", "TimestampUtc" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_VehicleCrossingEvents_RoundId_TimestampUtc",
                table: "VehicleCrossingEvents");

            migrationBuilder.DropColumn(
                name: "CameraId",
                table: "VehicleCrossingEvents");

            migrationBuilder.DropColumn(
                name: "SnapshotUrl",
                table: "VehicleCrossingEvents");

            migrationBuilder.DropColumn(
                name: "Source",
                table: "VehicleCrossingEvents");
        }
    }
}
