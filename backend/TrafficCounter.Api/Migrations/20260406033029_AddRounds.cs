using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace TrafficCounter.Api.Migrations
{
    /// <inheritdoc />
    public partial class AddRounds : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "CameraSources",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    SourceUrl = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    Protocol = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CameraSources", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Rounds",
                columns: table => new
                {
                    RoundId = table.Column<Guid>(type: "uuid", nullable: false),
                    Status = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    DisplayName = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    BetCloseAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    EndsAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    SettledAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CurrentCount = table.Column<int>(type: "integer", nullable: false),
                    FinalCount = table.Column<int>(type: "integer", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Rounds", x => x.RoundId);
                });

            migrationBuilder.CreateTable(
                name: "StreamSessions",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    CameraSourceId = table.Column<Guid>(type: "uuid", nullable: false),
                    Status = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    CountLineX1 = table.Column<int>(type: "integer", nullable: false),
                    CountLineY1 = table.Column<int>(type: "integer", nullable: false),
                    CountLineX2 = table.Column<int>(type: "integer", nullable: false),
                    CountLineY2 = table.Column<int>(type: "integer", nullable: false),
                    CountDirection = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    RawStreamPath = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    ProcessedStreamPath = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true),
                    TotalCount = table.Column<int>(type: "integer", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    StartedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    StoppedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    FailureReason = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_StreamSessions", x => x.Id);
                    table.ForeignKey(
                        name: "FK_StreamSessions_CameraSources_CameraSourceId",
                        column: x => x.CameraSourceId,
                        principalTable: "CameraSources",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "RecordingSegments",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    SessionId = table.Column<Guid>(type: "uuid", nullable: false),
                    SegmentType = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    FilePath = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    StartedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    EndedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    FileSizeBytes = table.Column<long>(type: "bigint", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RecordingSegments", x => x.Id);
                    table.ForeignKey(
                        name: "FK_RecordingSegments_StreamSessions_SessionId",
                        column: x => x.SessionId,
                        principalTable: "StreamSessions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "StreamHealthLogs",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    SessionId = table.Column<Guid>(type: "uuid", nullable: false),
                    TimestampUtc = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    FpsIn = table.Column<double>(type: "double precision", nullable: false),
                    FpsOut = table.Column<double>(type: "double precision", nullable: false),
                    LatencyMs = table.Column<double>(type: "double precision", nullable: false),
                    GpuUsagePercent = table.Column<double>(type: "double precision", nullable: false),
                    ReconnectCount = table.Column<int>(type: "integer", nullable: false),
                    Notes = table.Column<string>(type: "character varying(256)", maxLength: 256, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_StreamHealthLogs", x => x.Id);
                    table.ForeignKey(
                        name: "FK_StreamHealthLogs_StreamSessions_SessionId",
                        column: x => x.SessionId,
                        principalTable: "StreamSessions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "VehicleCrossingEvents",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    SessionId = table.Column<Guid>(type: "uuid", nullable: false),
                    TimestampUtc = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    TrackId = table.Column<long>(type: "bigint", nullable: false),
                    ObjectClass = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    Direction = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    LineId = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    FrameNumber = table.Column<long>(type: "bigint", nullable: false),
                    Confidence = table.Column<double>(type: "double precision", nullable: false),
                    PreviousEventHash = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: true),
                    EventHash = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_VehicleCrossingEvents", x => x.Id);
                    table.ForeignKey(
                        name: "FK_VehicleCrossingEvents_StreamSessions_SessionId",
                        column: x => x.SessionId,
                        principalTable: "StreamSessions",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_RecordingSegments_SessionId",
                table: "RecordingSegments",
                column: "SessionId");

            migrationBuilder.CreateIndex(
                name: "IX_Rounds_CreatedAt",
                table: "Rounds",
                column: "CreatedAt");

            migrationBuilder.CreateIndex(
                name: "IX_Rounds_Status",
                table: "Rounds",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "IX_StreamHealthLogs_SessionId",
                table: "StreamHealthLogs",
                column: "SessionId");

            migrationBuilder.CreateIndex(
                name: "IX_StreamSessions_CameraSourceId",
                table: "StreamSessions",
                column: "CameraSourceId");

            migrationBuilder.CreateIndex(
                name: "IX_StreamSessions_Status",
                table: "StreamSessions",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "IX_VehicleCrossingEvents_EventHash",
                table: "VehicleCrossingEvents",
                column: "EventHash");

            migrationBuilder.CreateIndex(
                name: "IX_VehicleCrossingEvents_SessionId_TimestampUtc",
                table: "VehicleCrossingEvents",
                columns: new[] { "SessionId", "TimestampUtc" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "RecordingSegments");

            migrationBuilder.DropTable(
                name: "Rounds");

            migrationBuilder.DropTable(
                name: "StreamHealthLogs");

            migrationBuilder.DropTable(
                name: "VehicleCrossingEvents");

            migrationBuilder.DropTable(
                name: "StreamSessions");

            migrationBuilder.DropTable(
                name: "CameraSources");
        }
    }
}
