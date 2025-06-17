USE [AuditReport];
GO

CREATE PROCEDURE usp_BackupAndPurge_AuditReport
AS
BEGIN
    SET NOCOUNT ON;

    -- Variables for dynamic backup file path
    DECLARE @BackupPath NVARCHAR(255) = 'C:\Backups\AuditReport_backup_' + 
        CONVERT(NVARCHAR(50), GETDATE(), 112) + '_' + 
        REPLACE(CONVERT(NVARCHAR(50), GETDATE(), 108), ':', '') + '.bak';

    -- Step 1: Backup Database
    BACKUP DATABASE [AuditReport]
    TO DISK = @BackupPath
    WITH INIT, COMPRESSION, STATS = 10;

    -- Step 2: Delete old data from AuditReport table
    DELETE FROM [dbo].[AuditReport]
    WHERE TimeStmp < DATEADD(MONTH, -3, GETDATE());

END;
GO