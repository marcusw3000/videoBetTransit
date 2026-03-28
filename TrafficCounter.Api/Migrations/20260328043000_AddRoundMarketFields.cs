using Microsoft.EntityFrameworkCore.Migrations;
#nullable disable

namespace TrafficCounter.Api.Migrations
{
    public partial class AddRoundMarketFields : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "MarketType",
                table: "RoundRanges",
                type: "TEXT",
                maxLength: 24,
                nullable: false,
                defaultValue: "range");

            migrationBuilder.AddColumn<int>(
                name: "TargetValue",
                table: "RoundRanges",
                type: "INTEGER",
                nullable: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "MarketType",
                table: "RoundRanges");

            migrationBuilder.DropColumn(
                name: "TargetValue",
                table: "RoundRanges");
        }
    }
}
