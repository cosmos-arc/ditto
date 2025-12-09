# Ditto Log Cleanup Script
# Rotates and cleans up old log files

param(
    [Parameter(Mandatory=$false)]
    [string]$LogDir = "",

    [Parameter(Mandatory=$false)]
    [int]$RetentionDays = 30,

    [Parameter(Mandatory=$false)]
    [switch]$CompressOld,

    [Parameter(Mandatory=$false)]
    [switch]$DryRun,

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

# Set log directory
if ([string]::IsNullOrEmpty($LogDir)) {
    $LogDir = "$ProjectRoot\logs"
}

# Verify log directory exists
if (!(Test-Path $LogDir)) {
    Write-Warning "Log directory not found: $LogDir"
    exit 0
}

# Get log files
function Get-LogFiles {
    return Get-ChildItem $LogDir -Filter "*.log*" -File
}

# Compress old log files
function Compress-LogFiles {
    Write-Info "Compressing old log files..."

    $CompressedCount = 0
    $TotalSizeBefore = 0
    $TotalSizeAfter = 0

    $LogFiles = Get-LogFiles
    foreach ($LogFile in $LogFiles) {
        # Skip already compressed files
        if ($LogFile.Extension -eq ".gz") {
            continue
        }

        # Check if file is older than 1 day
        if ($LogFile.LastWriteTime -lt (Get-Date).AddDays(-1)) {
            $OriginalSize = $LogFile.Length
            $TotalSizeBefore += $OriginalSize

            $CompressedPath = "$($LogFile.FullName).gz"

            if (-not $DryRun) {
                try {
                    # Compress the file
                    $OriginalContent = Get-Content $LogFile.FullName -Raw
                    $CompressedContent = [System.IO.Compression.GzipStream]::new(
                        [System.IO.MemoryStream]::new(),
                        [System.IO.Compression.CompressionMode]::Compress,
                        $false
                    )

                    # Write compressed content
                    $FileStream = [System.IO.File]::Create($CompressedPath)
                    $CompressedStream.CopyTo($FileStream)
                    $FileStream.Close()
                    $CompressedStream.Close()

                    # Get compressed size
                    $CompressedSize = (Get-Item $CompressedPath).Length
                    $TotalSizeAfter += $CompressedSize

                    # Remove original file
                    Remove-Item $LogFile.FullName -Force

                    $CompressedCount++
                    $Ratio = [math]::Round((1 - $CompressedSize / $OriginalSize) * 100, 2)
                    Write-Info "Compressed: $($LogFile.Name) (saved $($Ratio)%)"
                }
                catch {
                    Write-Warning "Failed to compress $($LogFile.Name): $($_.Exception.Message)"
                }
            } else {
                Write-Info "[DRY RUN] Would compress: $($LogFile.Name)"
                $CompressedCount++
            }
        }
    }

    if ($CompressedCount -gt 0) {
        $SavedSpace = $TotalSizeBefore - $TotalSizeAfter
        Write-Success "Compressed $CompressedCount log files"
        Write-Info "Space saved: $([math]::Round($SavedSpace / 1MB, 2)) MB"
    } else {
        Write-Info "No files to compress"
    }

    return @{
        compressed_count = $CompressedCount
        space_saved_mb = [math]::Round(($TotalSizeBefore - $TotalSizeAfter) / 1MB, 2)
    }
}

# Clean up old log files
function Remove-OldLogFiles {
    Write-Info "Removing log files older than $RetentionDays days..."

    $RemovedCount = 0
    $TotalSizeRemoved = 0

    $CutoffDate = (Get-Date).AddDays(-$RetentionDays)
    $LogFiles = Get-ChildItem $LogDir -File -Recurse

    foreach ($LogFile in $LogFiles) {
        if ($LogFile.LastWriteTime -lt $CutoffDate) {
            $FileSize = $LogFile.Length
            $TotalSizeRemoved += $FileSize

            if (-not $DryRun) {
                try {
                    Remove-Item $LogFile.FullName -Force -Recurse
                    $RemovedCount++
                    Write-Info "Removed: $($LogFile.FullName)"
                }
                catch {
                    Write-Warning "Failed to remove $($LogFile.FullName): $($_.Exception.Message)"
                }
            } else {
                Write-Info "[DRY RUN] Would remove: $($LogFile.FullName)"
                $RemovedCount++
            }
        }
    }

    if ($RemovedCount -gt 0) {
        Write-Success "Removed $RemovedCount old log files"
        Write-Info "Space freed: $([math]::Round($TotalSizeRemoved / 1MB, 2)) MB"
    } else {
        Write-Info "No files to remove"
    }

    return @{
        removed_count = $RemovedCount
        space_freed_mb = [math]::Round($TotalSizeRemoved / 1MB, 2)
    }
}

# Analyze log directory
function Get-LogStats {
    Write-Info "Analyzing log directory..."

    $LogFiles = Get-LogFiles
    $Stats = @{
        total_files = $LogFiles.Count
        total_size_mb = 0
        file_types = @{}
        oldest_file = $null
        newest_file = $null
    }

    foreach ($LogFile in $LogFiles) {
        $Size = $LogFile.Length
        $Stats.total_size_mb += $Size

        # Track file types
        $Ext = if ($LogFile.Extension -eq ".gz") { "compressed" } else { "plain" }
        if ($Stats.file_types.ContainsKey($Ext)) {
            $Stats.file_types[$Ext]++
        } else {
            $Stats.file_types[$Ext] = 1
        }

        # Track oldest and newest
        if ($Stats.oldest_file -eq $null -or $LogFile.LastWriteTime -lt $Stats.oldest_file.LastWriteTime) {
            $Stats.oldest_file = $LogFile
        }
        if ($Stats.newest_file -eq $null -or $LogFile.LastWriteTime -gt $Stats.newest_file.LastWriteTime) {
            $Stats.newest_file = $LogFile
        }
    }

    $Stats.total_size_mb = [math]::Round($Stats.total_size_mb / 1MB, 2)

    Write-Status "Log Directory Statistics:" "Magenta"
    Write-Info "  Total files: $($Stats.total_files)"
    Write-Info "  Total size: $($Stats.total_size_mb) MB"
    Write-Info "  File types: $($Stats.file_types | ForEach-Object { "$($_.Key): $($_.Value)" } -join ', ')"

    if ($Stats.oldest_file) {
        $DaysOld = (Get-Date) - $Stats.oldest_file.LastWriteTime
        Write-Info "  Oldest file: $($Stats.oldest_file.Name) ($($DaysOld.Days) days old)"
    }
    if ($Stats.newest_file) {
        $DaysOld = (Get-Date) - $Stats.newest_file.LastWriteTime
        Write-Info "  Newest file: $($Stats.newest_file.Name) ($($DaysOld.Days) days old)"
    }

    return $Stats
}

# Check log file health
function Test-LogFileHealth {
    Write-Info "Checking log file health..."

    $HealthIssues = @()

    # Check for very large log files (>100MB)
    $LogFiles = Get-LogFiles
    foreach ($LogFile in $LogFiles) {
        $SizeMB = $LogFile.Length / 1MB
        if ($SizeMB -gt 100) {
            $HealthIssues += "Large log file: $($LogFile.Name) ($([math]::Round($SizeMB, 2)) MB)"
        }

        # Check for very old uncompressed files
        if ($LogFile.Extension -ne ".gz" -and $LogFile.LastWriteTime -lt (Get-Date).AddDays(-30)) {
            $HealthIssues += "Old uncompressed log file: $($LogFile.Name) ($(($LogFile.LastWriteTime).ToString('yyyy-MM-dd')))"
        }
    }

    if ($HealthIssues.Count -eq 0) {
        Write-Success "No log health issues found"
    } else {
        Write-Warning "Found $($HealthIssues.Count) log health issues:"
        foreach ($Issue in $HealthIssues) {
            Write-Warning "  - $Issue"
        }
    }

    return $HealthIssues
}

# Generate cleanup report
function Export-CleanupReport {
    param(
        [hashtable]$Stats,
        [hashtable]$CompressResult,
        [hashtable]$RemoveResult,
        [array]$HealthIssues
    )

    $ReportPath = "$LogDir\cleanup_report_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"

    $Report = @{
        timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        log_directory = $LogDir
        retention_days = $RetentionDays
        dry_run = $DryRun
        statistics = $Stats
        compression = $CompressResult
        cleanup = $RemoveResult
        health_issues = $HealthIssues
        recommendations = @()
    }

    # Add recommendations
    if ($Stats.total_size_mb -gt 1000) {
        $Report.recommendations += "Consider reducing log retention days - total size exceeds 1GB"
    }
    if ($Stats.file_types.ContainsKey("plain") -and $Stats.file_types.plain -gt 10) {
        $Report.recommendations += "Enable automatic log compression - many uncompressed files"
    }
    if ($HealthIssues.Count -gt 5) {
        $Report.recommendations += "Run cleanup more frequently - multiple health issues detected"
    }

    $Report | ConvertTo-Json -Depth 3 | Out-File -FilePath $ReportPath -Encoding UTF8
    Write-Info "Cleanup report saved to: $ReportPath"

    return $ReportPath
}

# Main execution
try {
    if (-not $Quiet) {
        Write-Status "Ditto Log Cleanup Script" "Magenta"
        Write-Status "=======================" "Magenta"
    }

    Write-Info "Log directory: $LogDir"
    Write-Info "Retention period: $RetentionDays days"

    if ($DryRun) {
        Write-Warning "DRY RUN MODE - No actual changes will be made"
    }

    # Get initial statistics
    $InitialStats = Get-LogStats

    # Check health
    $HealthIssues = Test-LogFileHealth

    # Compress old files if requested
    $CompressResult = @{}
    if ($CompressOld) {
        $CompressResult = Compress-LogFiles
    }

    # Remove old files
    $RemoveResult = Remove-OldLogFiles

    # Get final statistics
    Write-Info "`nFinal Statistics:"
    $FinalStats = Get-LogStats

    # Generate report
    $ReportPath = Export-CleanupReport `
        -Stats $FinalStats `
        -CompressResult $CompressResult `
        -RemoveResult $RemoveResult `
        -HealthIssues $HealthIssues

    # Summary
    Write-Status "Cleanup completed!" "Magenta"
    Write-Status "================" "Magenta"
    Write-Info "Files processed: $($InitialStats.total_files) → $($FinalStats.total_files)"
    Write-Info "Size change: $($InitialStats.total_size_mb) MB → $($FinalStats.total_size_mb) MB"

    if ($CompressResult.compressed_count -gt 0) {
        Write-Success "Compressed: $($CompressResult.compressed_count) files ($($CompressResult.space_saved_mb) MB saved)"
    }

    if ($RemoveResult.removed_count -gt 0) {
        Write-Success "Removed: $($RemoveResult.removed_count) files ($($RemoveResult.space_freed_mb) MB freed)"
    }

    if ($HealthIssues.Count -eq 0) {
        Write-Success "Log health is good"
    } else {
        Write-Warning "Found $($HealthIssues.Count) health issues (see report for details)"
    }

    exit 0
}
catch {
    Write-Error "Cleanup failed: $_"
    Write-Error "Stack trace: $($_.ScriptStackTrace)"
    exit 1
}