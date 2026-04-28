using System.Data;
using System.Data.Common;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace TrafficCounter.Api.Data;

internal static class SqliteSchemaRepair
{
    private const string MigrationRoundEvents = "20260408223627_AddRoundEventsAndOptionalSessionCrossingEvents";
    private const string MigrationCrossingAudit = "20260408224557_AddCrossingEventAuditFieldsAndTimelineSupport";
    private const string MigrationRoundOperationalFields = "20260409152004_AddRoundCountEventOperationalFields";
    private const string MigrationCameraActivationReadiness = "20260424030000_AddCameraRoundStateActivationReadiness";

    public static async Task TryRepairLegacySchemaAsync(AppDbContext db, ILogger logger, CancellationToken cancellationToken = default)
    {
        if (!db.Database.IsSqlite())
            return;

        var connection = (SqliteConnection)db.Database.GetDbConnection();
        var shouldClose = connection.State != ConnectionState.Open;
        if (shouldClose)
            await connection.OpenAsync(cancellationToken);

        try
        {
            var roundEventsNeedsRepair = await TableNeedsRepairAsync(
                connection,
                "RoundEvents",
                ["Id", "RoundId", "EventType", "RoundStatus", "TimestampUtc", "CountValue", "Reason", "Source"],
                cancellationToken);

            var crossingEventsNeedsRepair = await TableNeedsRepairAsync(
                connection,
                "VehicleCrossingEvents",
                ["Id", "RoundId", "SessionId", "CameraId", "TimestampUtc", "TrackId", "ObjectClass", "Direction", "LineId", "FrameNumber", "Confidence", "SnapshotUrl", "Source", "StreamProfileId", "CountBefore", "CountAfter", "PreviousEventHash", "EventHash"],
                cancellationToken);

            if (!roundEventsNeedsRepair && !crossingEventsNeedsRepair)
            {
                await EnsureOperationalFieldMigrationAsync(connection, logger, cancellationToken);
                await EnsureCameraRoundActivationFieldsAsync(connection, logger, cancellationToken);
                return;
            }

            logger.LogWarning("Legacy SQLite schema detected. Applying local repair for round/count tables before migrations.");

            await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

            if (crossingEventsNeedsRepair)
            {
                await ExecuteNonQueryAsync(connection, transaction, """
                    PRAGMA foreign_keys = OFF;
                    DROP INDEX IF EXISTS IX_VehicleCrossingEvents_SessionId_TimestampUtc;
                    DROP INDEX IF EXISTS IX_VehicleCrossingEvents_RoundId;
                    DROP INDEX IF EXISTS IX_VehicleCrossingEvents_EventHash;
                    DROP INDEX IF EXISTS IX_VehicleCrossingEvents_RoundId_TimestampUtc;
                    ALTER TABLE VehicleCrossingEvents RENAME TO VehicleCrossingEvents_legacy;
                    CREATE TABLE VehicleCrossingEvents (
                        Id TEXT NOT NULL CONSTRAINT PK_VehicleCrossingEvents PRIMARY KEY,
                        RoundId TEXT NULL,
                        SessionId TEXT NULL,
                        CameraId TEXT NOT NULL DEFAULT '',
                        TimestampUtc TEXT NOT NULL,
                        TrackId INTEGER NOT NULL,
                        ObjectClass TEXT NOT NULL,
                        Direction TEXT NOT NULL,
                        LineId TEXT NOT NULL,
                        FrameNumber INTEGER NOT NULL,
                        Confidence REAL NOT NULL,
                        SnapshotUrl TEXT NULL,
                        Source TEXT NULL,
                        StreamProfileId TEXT NULL,
                        CountBefore INTEGER NULL,
                        CountAfter INTEGER NULL,
                        PreviousEventHash TEXT NULL,
                        EventHash TEXT NOT NULL,
                        CONSTRAINT FK_VehicleCrossingEvents_Rounds_RoundId FOREIGN KEY (RoundId) REFERENCES Rounds (RoundId),
                        CONSTRAINT FK_VehicleCrossingEvents_StreamSessions_SessionId FOREIGN KEY (SessionId) REFERENCES StreamSessions (Id) ON DELETE CASCADE
                    );
                    INSERT INTO VehicleCrossingEvents (
                        Id, RoundId, SessionId, CameraId, TimestampUtc, TrackId, ObjectClass, Direction, LineId, FrameNumber, Confidence, SnapshotUrl, Source, StreamProfileId, CountBefore, CountAfter, PreviousEventHash, EventHash
                    )
                    SELECT
                        legacy.Id,
                        legacy.RoundId,
                        legacy.SessionId,
                        COALESCE(rounds.CameraId, 'default'),
                        legacy.TimestampUtc,
                        legacy.TrackId,
                        legacy.ObjectClass,
                        legacy.Direction,
                        legacy.LineId,
                        legacy.FrameNumber,
                        legacy.Confidence,
                        NULL,
                        'legacy_crossing_event',
                        NULL,
                        NULL,
                        NULL,
                        legacy.PreviousEventHash,
                        legacy.EventHash
                    FROM VehicleCrossingEvents_legacy AS legacy
                    LEFT JOIN Rounds AS rounds ON rounds.RoundId = legacy.RoundId;
                    DROP TABLE VehicleCrossingEvents_legacy;
                    CREATE INDEX IX_VehicleCrossingEvents_SessionId_TimestampUtc ON VehicleCrossingEvents (SessionId, TimestampUtc);
                    CREATE INDEX IX_VehicleCrossingEvents_RoundId ON VehicleCrossingEvents (RoundId);
                    CREATE INDEX IX_VehicleCrossingEvents_EventHash ON VehicleCrossingEvents (EventHash);
                    CREATE INDEX IX_VehicleCrossingEvents_RoundId_TimestampUtc ON VehicleCrossingEvents (RoundId, TimestampUtc);
                    PRAGMA foreign_keys = ON;
                    """, cancellationToken);
            }

            if (roundEventsNeedsRepair)
            {
                await ExecuteNonQueryAsync(connection, transaction, """
                    PRAGMA foreign_keys = OFF;
                    DROP INDEX IF EXISTS IX_RoundEvents_RoundId_EventType;
                    DROP INDEX IF EXISTS IX_RoundEvents_RoundId_TimestampUtc;
                    ALTER TABLE RoundEvents RENAME TO RoundEvents_legacy;
                    CREATE TABLE RoundEvents (
                        Id TEXT NOT NULL CONSTRAINT PK_RoundEvents PRIMARY KEY,
                        RoundId TEXT NOT NULL,
                        EventType TEXT NOT NULL,
                        RoundStatus TEXT NOT NULL,
                        TimestampUtc TEXT NOT NULL,
                        CountValue INTEGER NOT NULL DEFAULT 0,
                        Reason TEXT NULL,
                        Source TEXT NULL,
                        CONSTRAINT FK_RoundEvents_Rounds_RoundId FOREIGN KEY (RoundId) REFERENCES Rounds (RoundId) ON DELETE CASCADE
                    );
                    INSERT INTO RoundEvents (
                        Id, RoundId, EventType, RoundStatus, TimestampUtc, CountValue, Reason, Source
                    )
                    SELECT
                        legacy.Id,
                        legacy.RoundId,
                        legacy.EventType,
                        COALESCE(legacy.NewStatus, legacy.PreviousStatus, 'open'),
                        COALESCE(legacy.OccurredAt, CURRENT_TIMESTAMP),
                        0,
                        legacy.MetadataJson,
                        'legacy_round_event'
                    FROM RoundEvents_legacy AS legacy;
                    DROP TABLE RoundEvents_legacy;
                    CREATE INDEX IX_RoundEvents_RoundId_EventType ON RoundEvents (RoundId, EventType);
                    CREATE INDEX IX_RoundEvents_RoundId_TimestampUtc ON RoundEvents (RoundId, TimestampUtc);
                    PRAGMA foreign_keys = ON;
                    """, cancellationToken);
            }

            await EnsureMigrationHistoryAsync(connection, transaction, cancellationToken);
            await transaction.CommitAsync(cancellationToken);

            await EnsureOperationalFieldMigrationAsync(connection, logger, cancellationToken);
            await EnsureCameraRoundActivationFieldsAsync(connection, logger, cancellationToken);
        }
        finally
        {
            if (shouldClose)
                await connection.CloseAsync();
        }
    }

    private static async Task<bool> TableNeedsRepairAsync(
        SqliteConnection connection,
        string tableName,
        IReadOnlyCollection<string> expectedColumns,
        CancellationToken cancellationToken)
    {
        if (!await TableExistsAsync(connection, tableName, cancellationToken))
            return false;

        var existingColumns = await GetColumnNamesAsync(connection, tableName, cancellationToken);
        return expectedColumns.Any(column => !existingColumns.Contains(column));
    }

    private static async Task<bool> TableExistsAsync(SqliteConnection connection, string tableName, CancellationToken cancellationToken)
    {
        await using var command = connection.CreateCommand();
        command.CommandText = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = $name LIMIT 1;";
        command.Parameters.AddWithValue("$name", tableName);
        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result is not null;
    }

    private static async Task<HashSet<string>> GetColumnNamesAsync(SqliteConnection connection, string tableName, CancellationToken cancellationToken)
    {
        var columns = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        await using var command = connection.CreateCommand();
        command.CommandText = $"PRAGMA table_info('{tableName}');";

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
            columns.Add(reader.GetString(reader.GetOrdinal("name")));

        return columns;
    }

    private static async Task ExecuteNonQueryAsync(
        SqliteConnection connection,
        DbTransaction transaction,
        string sql,
        CancellationToken cancellationToken)
    {
        await using var command = connection.CreateCommand();
        command.Transaction = (SqliteTransaction)transaction;
        command.CommandText = sql;
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task EnsureMigrationHistoryAsync(
        SqliteConnection connection,
        DbTransaction transaction,
        CancellationToken cancellationToken)
    {
        await using var createCommand = connection.CreateCommand();
        createCommand.Transaction = (SqliteTransaction)transaction;
        createCommand.CommandText = """
            CREATE TABLE IF NOT EXISTS "__EFMigrationsHistory" (
                "MigrationId" TEXT NOT NULL CONSTRAINT "PK___EFMigrationsHistory" PRIMARY KEY,
                "ProductVersion" TEXT NOT NULL
            );
            """;
        await createCommand.ExecuteNonQueryAsync(cancellationToken);

        var productVersion = await GetLatestProductVersionAsync(connection, transaction, cancellationToken) ?? "8.0.0";
        await EnsureMigrationRowAsync(connection, transaction, MigrationRoundEvents, productVersion, cancellationToken);
        await EnsureMigrationRowAsync(connection, transaction, MigrationCrossingAudit, productVersion, cancellationToken);
    }

    private static async Task EnsureOperationalFieldMigrationAsync(
        SqliteConnection connection,
        ILogger logger,
        CancellationToken cancellationToken)
    {
        var existingColumns = await GetColumnNamesAsync(connection, "VehicleCrossingEvents", cancellationToken);
        var requiredColumns = new[] { "CountAfter", "CountBefore", "StreamProfileId" };

        if (!requiredColumns.Any(existingColumns.Contains))
            return;

        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        foreach (var column in requiredColumns.Where(column => !existingColumns.Contains(column)))
        {
            var columnSql = column switch
            {
                "CountAfter" => """ALTER TABLE VehicleCrossingEvents ADD COLUMN CountAfter INTEGER NULL;""",
                "CountBefore" => """ALTER TABLE VehicleCrossingEvents ADD COLUMN CountBefore INTEGER NULL;""",
                "StreamProfileId" => """ALTER TABLE VehicleCrossingEvents ADD COLUMN StreamProfileId TEXT NULL;""",
                _ => null,
            };

            if (columnSql is null)
                continue;

            logger.LogWarning("SQLite schema estava parcialmente atualizado. Adicionando coluna ausente {Column}.", column);
            await ExecuteNonQueryAsync(connection, transaction, columnSql, cancellationToken);
        }

        var productVersion = await GetLatestProductVersionAsync(connection, transaction, cancellationToken) ?? "8.0.0";
        await EnsureMigrationRowAsync(connection, transaction, MigrationRoundOperationalFields, productVersion, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    private static async Task EnsureCameraRoundActivationFieldsAsync(
        SqliteConnection connection,
        ILogger logger,
        CancellationToken cancellationToken)
    {
        if (!await TableExistsAsync(connection, "CameraRoundStates", cancellationToken))
            return;

        var existingColumns = await GetColumnNamesAsync(connection, "CameraRoundStates", cancellationToken);
        var requiredColumns = new[]
        {
            "ActivationPhase",
            "ReadyForRounds",
            "ExpectedFrontendAckNonce",
            "ActivationSessionId",
            "LastReadyActivationSessionId",
            "FrontendAckReceived",
            "FrontendAckedAt",
            "LastFrontendAckSessionId",
            "ActivationRequestedAt",
        };

        if (requiredColumns.All(existingColumns.Contains))
            return;

        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        foreach (var column in requiredColumns.Where(column => !existingColumns.Contains(column)))
        {
            var columnSql = column switch
            {
                "ActivationPhase" => """ALTER TABLE CameraRoundStates ADD COLUMN ActivationPhase TEXT NOT NULL DEFAULT 'ready';""",
                "ReadyForRounds" => """ALTER TABLE CameraRoundStates ADD COLUMN ReadyForRounds INTEGER NOT NULL DEFAULT 1;""",
                "ExpectedFrontendAckNonce" => """ALTER TABLE CameraRoundStates ADD COLUMN ExpectedFrontendAckNonce TEXT NULL;""",
                "ActivationSessionId" => """ALTER TABLE CameraRoundStates ADD COLUMN ActivationSessionId TEXT NULL;""",
                "LastReadyActivationSessionId" => """ALTER TABLE CameraRoundStates ADD COLUMN LastReadyActivationSessionId TEXT NULL;""",
                "FrontendAckReceived" => """ALTER TABLE CameraRoundStates ADD COLUMN FrontendAckReceived INTEGER NOT NULL DEFAULT 0;""",
                "FrontendAckedAt" => """ALTER TABLE CameraRoundStates ADD COLUMN FrontendAckedAt TEXT NULL;""",
                "LastFrontendAckSessionId" => """ALTER TABLE CameraRoundStates ADD COLUMN LastFrontendAckSessionId TEXT NULL;""",
                "ActivationRequestedAt" => """ALTER TABLE CameraRoundStates ADD COLUMN ActivationRequestedAt TEXT NULL;""",
                _ => null,
            };

            if (columnSql is null)
                continue;

            logger.LogWarning("SQLite schema estava parcialmente atualizado. Adicionando coluna ausente {Column} em CameraRoundStates.", column);
            await ExecuteNonQueryAsync(connection, transaction, columnSql, cancellationToken);
        }

        var productVersion = await GetLatestProductVersionAsync(connection, transaction, cancellationToken) ?? "8.0.0";
        await EnsureMigrationRowAsync(connection, transaction, MigrationCameraActivationReadiness, productVersion, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    private static async Task<string?> GetLatestProductVersionAsync(
        SqliteConnection connection,
        DbTransaction transaction,
        CancellationToken cancellationToken)
    {
        await using var command = connection.CreateCommand();
        command.Transaction = (SqliteTransaction)transaction;
        command.CommandText = """
            SELECT ProductVersion
            FROM "__EFMigrationsHistory"
            ORDER BY MigrationId DESC
            LIMIT 1;
            """;
        var result = await command.ExecuteScalarAsync(cancellationToken);
        return result?.ToString();
    }

    private static async Task EnsureMigrationRowAsync(
        SqliteConnection connection,
        DbTransaction transaction,
        string migrationId,
        string productVersion,
        CancellationToken cancellationToken)
    {
        await using var command = connection.CreateCommand();
        command.Transaction = (SqliteTransaction)transaction;
        command.CommandText = """
            INSERT OR IGNORE INTO "__EFMigrationsHistory" ("MigrationId", "ProductVersion")
            VALUES ($migrationId, $productVersion);
            """;
        command.Parameters.AddWithValue("$migrationId", migrationId);
        command.Parameters.AddWithValue("$productVersion", productVersion);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }
}
