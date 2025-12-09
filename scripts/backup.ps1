# Ditto System Backup Script
# This script creates backups of data, configuration, and logs

param(
    [Parameter(Mandatory=$false)]
    [string]$BackupDir = "",

    [Parameter(Mandatory=$false)]
    [switch]$Compress,

    [Parameter(Mandatory=$false)]
    [switch]$IncludeLogs,

    [Parameter(Mandatory=$false)]
    [switch]$Incremental,

    [Parameter(Mandatory=$false)]
    [int]$RetentionDays = 30,

    [Parameter(Mandatory=$false)]
    [switch]$Quiet
)

# Script configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Color output functions
function Write-Status {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    if (-not $Quiet) {
        Write-Host $Message -ForegroundColor $Color
    }
}

function Write-Success {
    param([string]$Message)
    Write-Status "✓ $Message" "Green"
}

function Write-Warning {
    param([string]$Message)
    Write-Status "⚠ $Message" "Yellow"
}

function Write-Error {
    param([string]$Message)
    Write-Status "✗ $Message" "Red"
}

function Write-Info {
    param([string]$Message)
    Write-Status "ℹ $Message" "Cyan"
}

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir

# Setup backup directory
function Initialize-BackupDir {
    if ([string]::IsNullOrEmpty($BackupDir)) {
        $DefaultBackupDir = "$ProjectRoot\backups"
        $BackupDir = $DefaultBackupDir
    }

    # Create backup directory with date
    $Date = Get-Date -Format "yyyyMMdd_HHmmss"
    $BackupPath = Join-Path $BackupDir "ditto_backup_$Date"

    if (!(Test-Path $BackupPath)) {
        New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null
    }

    return $BackupPath
}

# Get last backup timestamp for incremental backup
function Get-LastBackupTimestamp {
    $BackupRoot = if ([string]::IsNullOrEmpty($BackupDir)) { "$ProjectRoot\backups" } else { $BackupDir }

    $LastBackup = Get-ChildItem $BackupRoot -Filter "ditto_backup_*" -Directory |
        Sort-Object CreationTime -Descending |
        Select-Object -First 1

    if ($LastBackup) {
        return $LastBackup.CreationTime
    }
    return $null
}

# Create manifest file for backup
function New-BackupManifest {
    param(
        [string]$BackupPath,
        [hashtable]$Stats
    )

    $Manifest = @{
        backup_time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        backup_type = if ($Incremental) { "incremental" } else { "full" }
        backup_path = $BackupPath
        compressed = $Compress
        stats = $Stats
        ditto_version = "1.0.0"  # TODO: Get from version file
    }

    $ManifestPath = Join-Path $BackupPath "backup_manifest.json"
    $Manifest | ConvertTo-Json -Depth 3 | Out-File -FilePath $ManifestPath -Encoding UTF8
}

# Backup databases
function Backup-Databases {
    param(
        [string]$BackupPath,
        [datetime]$SinceTime
    )

    Write-Info "Backing up databases..."

    $Stats = @{
        duckdb_size = 0
        sqlite_size = 0
        total_files = 0
    }

    # DuckDB database
    $DuckDBPath = "$ProjectRoot\data\duckdb\ditto.duckdb"
    if (Test-Path $DuckDBPath) {
        $DuckDBBackup = Join-Path $BackupPath "data\duckdb"
        New-Item -ItemType Directory -Path $DuckDBBackup -Force | Out-Null

        if ($Incremental -and $SinceTime) {
            # For incremental, only backup if modified since last backup
            if ((Get-Item $DuckDBPath).LastWriteTime -gt $SinceTime) {
                Copy-Item $DuckDBPath $DuckDBBackup -Force
                $Stats.duckdb_size = (Get-Item "$DuckDBBackup\ditto.duckdb").Length
                Write-Success "DuckDB database backed up (incremental)"
            } else {
                Write-Info "DuckDB database unchanged since last backup"
            }
        } else {
            Copy-Item $DuckDBPath $DuckDBBackup -Force
            $Stats.duckdb_size = (Get-Item "$DuckDBBackup\ditto.duckdb").Length
            Write-Success "DuckDB database backed up"
        }
        $Stats.total_files++
    }

    # SQLite database
    $SQLitePath = "$ProjectRoot\data\sqlite\ditto.sqlite"
    if (Test-Path $SQLitePath) {
        $SQLiteBackup = Join-Path $BackupPath "data\sqlite"
        New-Item -ItemType Directory -Path $SQLiteBackup -Force | Out-Null

        if ($Incremental -and $SinceTime) {
            if ((Get-Item $SQLitePath).LastWriteTime -gt $SinceTime) {
                Copy-Item $SQLitePath $SQLiteBackup -Force
                $Stats.sqlite_size = (Get-Item "$SQLiteBackup\ditto.sqlite").Length
                Write-Success "SQLite database backed up (incremental)"
            } else {
                Write-Info "SQLite database unchanged since last backup"
            }
        } else {
            Copy-Item $SQLitePath $SQLiteBackup -Force
            $Stats.sqlite_size = (Get-Item "$SQLiteBackup\ditto.sqlite").Length
            Write-Success "SQLite database backed up"
        }
        $Stats.total_files++
    }

    return $Stats
}

# Backup configuration files
function Backup-Configuration {
    param(
        [string]$BackupPath,
        [datetime]$SinceTime
    )

    Write-Info "Backing up configuration..."

    $Stats = @{
        config_files = 0
        total_size = 0
    }

    $ConfigItems = @(
        ".env",
        "pixi.toml",
        ".env.example"
    )

    $ConfigBackup = Join-Path $BackupPath "config"
    New-Item -ItemType Directory -Path $ConfigBackup -Force | Out-Null

    foreach ($Item in $ConfigItems) {
        $ItemPath = Join-Path $ProjectRoot $Item
        if (Test-Path $ItemPath) {
            $ShouldBackup = $true
            if ($Incremental -and $SinceTime) {
                $ShouldBackup = (Get-Item $ItemPath).LastWriteTime -gt $SinceTime
            }

            if ($ShouldBackup) {
                Copy-Item $ItemPath $ConfigBackup -Force
                $Size = (Get-Item (Join-Path $ConfigBackup $Item)).Length
                $Stats.total_size += $Size
                $Stats.config_files++
                Write-Info "Backed up: $Item"
            }
        }
    }

    # Backup packages configuration
    $PackagesConfig = Join-Path $ProjectRoot "packages\shared\src\config\settings.py"
    if (Test-Path $PackagesConfig) {
        $ShouldBackup = $true
        if ($Incremental -and $SinceTime) {
            $ShouldBackup = (Get-Item $PackagesConfig).LastWriteTime -gt $SinceTime
        }

        if ($ShouldBackup) {
            $PackagesBackup = Join-Path $BackupPath "packages\shared\src\config"
            New-Item -ItemType Directory -Path $PackagesBackup -Force | Out-Null
            Copy-Item $PackagesConfig $PackagesBackup -Force
            $Size = (Get-Item (Join-Path $PackagesBackup "settings.py")).Length
            $Stats.total_size += $Size
            $Stats.config_files++
            Write-Info "Backed up: settings.py"
        }
    }

    return $Stats
}

# Backup logs (optional)
function Backup-Logs {
    param(
        [string]$BackupPath,
        [datetime]$SinceTime
    )

    if (-not $IncludeLogs) {
        Write-Info "Skipping logs backup (--include-logs not specified)"
        return @{
            log_files = 0
            total_size = 0
        }
    }

    Write-Info "Backing up logs..."

    $Stats = @{
        log_files = 0
        total_size = 0
    }

    $LogDir = "$ProjectRoot\logs"
    if (Test-Path $LogDir) {
        $LogBackup = Join-Path $BackupPath "logs"
        New-Item -ItemType Directory -Path $LogBackup -Force | Out-Null

        # Get all log files
        $LogFiles = Get-ChildItem $LogDir -File
        foreach ($LogFile in $LogFiles) {
            $ShouldBackup = $true
            if ($Incremental -and $SinceTime) {
                $ShouldBackup = $LogFile.LastWriteTime -gt $SinceTime
            }

            if ($ShouldBackup) {
                Copy-Item $LogFile.FullName $LogBackup -Force
                $Size = (Get-Item (Join-Path $LogBackup $LogFile.Name)).Length
                $Stats.total_size += $Size
                $Stats.log_files++
                Write-Info "Backed up log: $($LogFile.Name)"
            }
        }
    }

    return $Stats
}

# Compress backup
function Compress-Backup {
    param(
        [string]$BackupPath
    )

    if (-not $Compress) {
        return
    }

    Write-Info "Compressing backup..."

    try {
        $CompressedPath = "$BackupPath.zip"
        Compress-Archive -Path $BackupPath -DestinationPath $CompressedPath -Force

        # Get size info
        $UncompressedSize = (Get-ChildItem $BackupPath -Recurse | Measure-Object -Property Length -Sum).Sum
        $CompressedSize = (Get-Item $CompressedPath).Length
        $CompressionRatio = [math]::Round((1 - $CompressedSize / $UncompressedSize) * 100, 2)

        Write-Success "Backup compressed"
        Write-Info "Size reduced: $UncompressedSize bytes → $CompressedSize bytes ($CompressionRatio% reduction)"

        # Remove uncompressed backup
        Remove-Item $BackupPath -Recurse -Force
        return $CompressedPath
    }
    catch {
        Write-Error "Failed to compress backup: $_"
        return $BackupPath
    }
}

# Clean up old backups
function Remove-OldBackups {
    $BackupRoot = if ([string]::IsNullOrEmpty($BackupDir)) { "$ProjectRoot\backups" } else { $BackupDir }

    Write-Info "Cleaning up backups older than $RetentionDays days..."

    $CutoffDate = (Get-Date).AddDays(-$RetentionDays)
    $OldBackups = Get-ChildItem $BackupRoot -Filter "ditto_backup_*" -Directory |
        Where-Object { $_.CreationTime -lt $CutoffDate }

    $RemovedCount = 0
    foreach ($OldBackup in $OldBackups) {
        try {
            Remove-Item $OldBackup.FullName -Recurse -Force
            $RemovedCount++
            Write-Info "Removed old backup: $($OldBackup.Name)"
        }
        catch {
            Write-Warning "Failed to remove old backup $($OldBackup.Name): $_"
        }
    }

    if ($RemovedCount -gt 0) {
        Write-Success "Removed $RemovedCount old backup(s)"
    } else {
        Write-Info "No old backups to remove"
    }
}

# Main execution
try {
    Write-Status "Ditto System Backup" "Magenta"
    Write-Status "===================" "Magenta"

    # Initialize backup
    $BackupPath = Initialize-BackupDir
    Write-Info "Backup location: $BackupPath"

    # Get incremental base time
    $SinceTime = $null
    if ($Incremental) {
        $SinceTime = Get-LastBackupTimestamp
        if ($SinceTime) {
            Write-Info "Incremental backup since: $($SinceTime.ToString('yyyy-MM-dd HH:mm:ss'))"
        } else {
            Write-Warning "No previous backup found, performing full backup"
            $Incremental = $false
        }
    }

    # Perform backups
    $TotalStats = @{
        databases = Backup-Databases -BackupPath $BackupPath -SinceTime $SinceTime
        config = Backup-Configuration -BackupPath $BackupPath -SinceTime $SinceTime
        logs = Backup-Logs -BackupPath $BackupPath -SinceTime $SinceTime
    }

    # Calculate totals
    $TotalFiles = $TotalStats.databases.total_files + $TotalStats.config.config_files + $TotalStats.logs.log_files
    $TotalSize = $TotalStats.databases.duckdb_size + $TotalStats.databases.sqlite_size + $TotalStats.config.total_size + $TotalStats.logs.total_size

    # Create manifest
    New-BackupManifest -BackupPath $BackupPath -Stats @{
        files_backed_up = $TotalFiles
        total_size_bytes = $TotalSize
        db_stats = $TotalStats.databases
        config_stats = $TotalStats.config
        log_stats = $TotalStats.logs
    }

    # Compress if requested
    $FinalPath = Compress-Backup -BackupPath $BackupPath

    # Clean up old backups
    Remove-OldBackups

    # Summary
    Write-Status "Backup completed successfully!" "Magenta"
    Write-Status "===========================" "Magenta"
    Write-Info "Type: $(if ($Incremental) { 'Incremental' } else { 'Full' })"
    Write-Info "Files: $TotalFiles"
    Write-Info "Size: $([math]::Round($TotalSize / 1MB, 2)) MB"
    Write-Info "Location: $FinalPath"

    if ($Compress) {
        Write-Info "To restore: Expand-Archive '$FinalPath' -DestinationPath '$BackupRoot'"
    }

    exit 0
}
catch {
    Write-Error "Backup failed: $_"
    Write-Error "Stack trace: $($_.ScriptStackTrace)"
    exit 1
}