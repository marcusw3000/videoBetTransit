using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddPipelineManagementMode : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "PipelineManagementStates",
                columns: table => new
                {
                    Id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    IsActive = table.Column<bool>(type: "INTEGER", nullable: false),
                    CameraId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: true),
                    StreamProfileId = table.Column<string>(type: "TEXT", maxLength: 128, nullable: true),
                    Reason = table.Column<string>(type: "TEXT", maxLength: 512, nullable: true),
                    ActivatedBy = table.Column<string>(type: "TEXT", maxLength: 128, nullable: true),
                    ActivatedAt = table.Column<DateTime>(type: "TEXT", nullable: true),
                    Revision = table.Column<int>(type: "INTEGER", nullable: false),
                    DraftConfigurationJson = table.Column<string>(type: "TEXT", maxLength: 8192, nullable: true),
                    DraftApplied = table.Column<bool>(type: "INTEGER", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PipelineManagementStates", x => x.Id);
                });

            migrationBuilder.InsertData(
                table: "PipelineManagementStates",
                columns: new[] { "Id", "ActivatedAt", "ActivatedBy", "CameraId", "DraftApplied", "DraftConfigurationJson", "IsActive", "Reason", "Revision", "StreamProfileId", "UpdatedAt" },
                values: new object[] { 1, null, null, null, true, null, false, null, 1, null, new DateTime(1970, 1, 1, 0, 0, 0, 0, DateTimeKind.Utc) });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "PipelineManagementStates");
        }
    }
}
