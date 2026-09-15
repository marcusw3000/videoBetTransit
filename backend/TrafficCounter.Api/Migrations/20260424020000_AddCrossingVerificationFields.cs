using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using TrafficCounter.Api.Data;

namespace TrafficCounter.Api.Migrations;

[DbContext(typeof(AppDbContext))]
[Migration("20260424020000_AddCrossingVerificationFields")]
public sealed class AddCrossingVerificationFields : Migration
{
    protected override void Up(MigrationBuilder builder)
    {
        builder.AddColumn<string>("CountMethod", "VehicleCrossingEvents", maxLength: 32, nullable: true);
        builder.AddColumn<int>("FallbackBandPx", "VehicleCrossingEvents", nullable: true);
    }
    protected override void Down(MigrationBuilder builder)
    {
        builder.DropColumn("CountMethod", "VehicleCrossingEvents");
        builder.DropColumn("FallbackBandPx", "VehicleCrossingEvents");
    }
}
