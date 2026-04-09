using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddRoundCountEventOperationalFields : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "CountAfter",
                table: "VehicleCrossingEvents",
                type: "INTEGER",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "CountBefore",
                table: "VehicleCrossingEvents",
                type: "INTEGER",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "StreamProfileId",
                table: "VehicleCrossingEvents",
                type: "TEXT",
                maxLength: 128,
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "CountAfter",
                table: "VehicleCrossingEvents");

            migrationBuilder.DropColumn(
                name: "CountBefore",
                table: "VehicleCrossingEvents");

            migrationBuilder.DropColumn(
                name: "StreamProfileId",
                table: "VehicleCrossingEvents");
        }
    }
}
