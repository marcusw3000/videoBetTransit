using System;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using TrafficCounter.Api.Data;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    [DbContext(typeof(TrafficCounterDbContext))]
    [Migration("20260328190000_AddRoundAuditFields")]
    public partial class AddRoundAuditFields : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "DisplayName",
                table: "Rounds",
                type: "TEXT",
                maxLength: 64,
                nullable: false,
                defaultValue: "Rodada Turbo");

            migrationBuilder.AddColumn<DateTime>(
                name: "SettledAt",
                table: "Rounds",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "VoidedAt",
                table: "Rounds",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "VoidReason",
                table: "Rounds",
                type: "TEXT",
                maxLength: 256,
                nullable: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "DisplayName",
                table: "Rounds");

            migrationBuilder.DropColumn(
                name: "SettledAt",
                table: "Rounds");

            migrationBuilder.DropColumn(
                name: "VoidedAt",
                table: "Rounds");

            migrationBuilder.DropColumn(
                name: "VoidReason",
                table: "Rounds");
        }
    }
}
