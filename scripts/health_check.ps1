# Ditto System Health Check Script
# Monitors system health and reports issues

param(
    [Parameter(Mandatory=$false)]
    [string]$ReportPath = "",

    [Parameter(Mandatory=$false)]
    [switch]$Quiet,

    [Parameter(Mandatory=$false)]
    [switch]$EmailAlert,

    [Parameter(Mandatory=$false)]
    [switch]$SlackAlert
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

# Initialize health report
$HealthReport = @{
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    status = "healthy"
    checks = @{}
    issues = @()
    summary = @{
        total_checks = 0
        passed_checks = 0
        failed_checks = 0
        warning_checks = 0
    }
}

# Add check result to report
function Add-CheckResult {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Message,
        [string]$Severity = "error",  # error, warning, info
        [hashtable]$Details = $null
    )

    $HealthReport.checks[$Name] = @{
        passed = $Passed
        message = $Message
        severity = $Severity
        timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        details = $Details
    }

    $HealthReport.summary.total_checks++

    if ($Passed) {
        $HealthReport.summary.passed_checks++
    } else {
        $HealthReport.summary.failed_checks++
        if ($Severity -eq "warning") {
            $HealthReport.summary.warning_checks++
        }

        $HealthReport.issues += @{
            check = $Name
            message = $Message
            severity = $Severity
        }

        # Update overall status
        if ($Severity -eq "error") {
            $HealthReport.status = "unhealthy"
        } elseif ($HealthReport.status -eq "healthy" -and $Severity -eq "warning") {
            $HealthReport.status = "warning"
        }
    }
}

# Check disk space
function Test-DiskSpace {
    Write-Info "Checking disk space..."

    $RequiredSpaceGB = 1  # Minimum 1GB free
    $Drives = Get-PSDrive -PSProvider FileSystem

    $Passed = $true
    $Message = "All drives have sufficient space"
    $Details = @{}

    foreach ($Drive in $Drives) {
        $FreeSpaceGB = [math]::Round($Drive.Free / 1GB, 2)
        $Details[$Drive.Name] = @{
            free_gb = $FreeSpaceGB
            total_gb = [math]::Round(($Drive.Used + $Drive.Free) / 1GB, 2)
            usage_percent = [math]::Round(($Drive.Used / ($Drive.Used + $Drive.Free)) * 100, 2)
        }

        if ($FreeSpaceGB -lt $RequiredSpaceGB) {
            $Passed = $false
            $Message = "Drive $($Drive.Name) has only $FreeSpaceGB GB free (requires at least $RequiredSpaceGB GB)"
        }
    }

    Add-CheckResult -Name "disk_space" -Passed $Passed -Message $Message -Details $Details
}

# Check database connectivity
function Test-DatabaseConnectivity {
    Write-Info "Checking database connectivity..."

    try {
        # Check DuckDB
        $DuckDBPath = "$ProjectRoot\data\duckdb\ditto.duckdb"
        $DuckDBExists = Test-Path $DuckDBPath

        # Check SQLite
        $SQLitePath = "$ProjectRoot\data\sqlite\ditto.sqlite"
        $SQLiteExists = Test-Path $SQLitePath

        if ($DuckDBExists -and $SQLiteExists) {
            Add-CheckResult -Name "database_connectivity" -Passed $true -Message "Both databases accessible"
        } else {
            $Missing = @()
            if (-not $DuckDBExists) { $Missing += "DuckDB" }
            if (-not $SQLiteExists) { $Missing += "SQLite" }
            Add-CheckResult -Name "database_connectivity" -Passed $false -Message "Missing databases: $($Missing -join ', ')"
        }
    }
    catch {
        Add-CheckResult -Name "database_connectivity" -Passed $false -Message "Database check failed: $($_.Exception.Message)"
    }
}

# Check data freshness
function Test-DataFreshness {
    Write-Info "Checking data freshness..."

    try {
        # Check latest data in database
        # This would typically involve querying the database
        # For now, check file modification times
        $DuckDBPath = "$ProjectRoot\data\duckdb\ditto.duckdb"
        $SQLitePath = "$ProjectRoot\data\sqlite\ditto.sqlite"

        $LastUpdate = $null
        if (Test-Path $DuckDBPath) {
            $LastUpdate = (Get-Item $DuckDBPath).LastWriteTime
        }
        if (Test-Path $SQLitePath) {
            $SQLiteUpdate = (Get-Item $SQLitePath).LastWriteTime
            if (-not $LastUpdate -or $SQLiteUpdate -gt $LastUpdate) {
                $LastUpdate = $SQLiteUpdate
            }
        }

        if ($LastUpdate) {
            $DaysSinceUpdate = (Get-Date) - $LastUpdate
            if ($DaysSinceUpdate.Days -le 2) {
                Add-CheckResult -Name "data_freshness" -Passed $true -Message "Data updated $($DaysSinceUpdate.Days) days ago"
            } else {
                Add-CheckResult -Name "data_freshness" -Passed $false -Message "Data not updated for $($DaysSinceUpdate.Days) days" -Severity "warning"
            }
        } else {
            Add-CheckResult -Name "data_freshness" -Passed $false -Message "No data found"
        }
    }
    catch {
        Add-CheckResult -Name "data_freshness" -Passed $false -Message "Failed to check data freshness: $($_.Exception.Message)"
    }
}

# Check API server
function Test-APIServer {
    Write-Info "Checking API server..."

    try {
        # Check if server is running on default port
        $Port = 8000
        $Response = Invoke-WebRequest -Uri "http://localhost:$Port/healthz" -TimeoutSec 5 -ErrorAction SilentlyContinue

        if ($Response.StatusCode -eq 200) {
            Add-CheckResult -Name "api_server" -Passed $true -Message "API server responding"
        } else {
            Add-CheckResult -Name "api_server" -Passed $false -Message "API server returned status $($Response.StatusCode)"
        }
    }
    catch {
        # Server might not be running, which is ok in some contexts
        Add-CheckResult -Name "api_server" -Passed $false -Message "API server not reachable" -Severity "warning"
    }
}

# Check log files
function Test-LogFiles {
    Write-Info "Checking log files..."

    try {
        $LogDir = "$ProjectRoot\logs"
        $LogFile = "$LogDir\ditto.log"
        $ErrorLogFile = "$LogDir\ditto_error.log"

        $Issues = @()

        # Check if log directory exists
        if (-not (Test-Path $LogDir)) {
            Add-CheckResult -Name "log_files" -Passed $false -Message "Log directory does not exist"
            return
        }

        # Check recent error logs
        if (Test-Path $ErrorLogFile) {
            $RecentErrors = Get-Content $ErrorLogFile -Tail 100 | Where-Object { $_ -match "ERROR" }
            if ($RecentErrors.Count -gt 10) {
                $Issues += "High number of recent errors: $($RecentErrors.Count)"
            }
        }

        # Check log file size
        if (Test-Path $LogFile) {
            $LogSizeMB = (Get-Item $LogFile).Length / 1MB
            if ($LogSizeMB -gt 100) {
                $Issues += "Log file is large: $([math]::Round($LogSizeMB, 2)) MB"
            }
        }

        if ($Issues.Count -eq 0) {
            Add-CheckResult -Name "log_files" -Passed $true -Message "Log files are healthy"
        } else {
            Add-CheckResult -Name "log_files" -Passed $false -Message ($Issues -join "; ") -Severity "warning"
        }
    }
    catch {
        Add-CheckResult -Name "log_files" -Passed $false -Message "Failed to check log files: $($_.Exception.Message)"
    }
}

# Check configuration
function Test-Configuration {
    Write-Info "Checking configuration..."

    try {
        $EnvFile = "$ProjectRoot\.env"
        $ConfigFile = "$ProjectRoot\pixi.toml"

        $Missing = @()
        if (-not (Test-Path $EnvFile)) {
            $Missing += ".env"
        }
        if (-not (Test-Path $ConfigFile)) {
            $Missing += "pixi.toml"
        }

        if ($Missing.Count -eq 0) {
            Add-CheckResult -Name "configuration" -Passed $true -Message "All configuration files present"
        } else {
            Add-CheckResult -Name "configuration" -Passed $false -Message "Missing configuration files: $($Missing -join ', ')"
        }
    }
    catch {
        Add-CheckResult -Name "configuration" -Passed $false -Message "Failed to check configuration: $($_.Exception.Message)"
    }
}

# Check data quality
function Test-DataQuality {
    Write-Info "Checking data quality..."

    try {
        # Run data quality check
        Set-Location $ProjectRoot
        $Result = & pixi run python scripts\check_data_quality.py health --sample-size 3 --days-back 5 2>&1

        if ($LASTEXITCODE -eq 0) {
            Add-CheckResult -Name "data_quality" -Passed $true -Message "Data quality check passed"
        } else {
            Add-CheckResult -Name "data_quality" -Passed $false -Message "Data quality issues detected" -Severity "warning"
        }
    }
    catch {
        # Data quality check might fail if Python environment not set up
        Add-CheckResult -Name "data_quality" -Passed $false -Message "Could not run data quality check" -Severity "warning"
    }
}

# Generate health report
function Export-HealthReport {
    if ([string]::IsNullOrEmpty($ReportPath)) {
        $ReportPath = "$ProjectRoot\logs\health_report_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    }

    $HealthReport | ConvertTo-Json -Depth 3 | Out-File -FilePath $ReportPath -Encoding UTF8
    Write-Info "Health report saved to: $ReportPath"

    return $ReportPath
}

# Send alerts (placeholder functions)
function Send-EmailAlert {
    param([hashtable]$Report)

    if (-not $EmailAlert) {
        return
    }

    Write-Warning "Email alerting not implemented"
    # TODO: Implement email alerting
}

function Send-SlackAlert {
    param([hashtable]$Report)

    if (-not $SlackAlert) {
        return
    }

    Write-Warning "Slack alerting not implemented"
    # TODO: Implement Slack alerting
}

# Main execution
try {
    if (-not $Quiet) {
        Write-Status "Ditto System Health Check" "Magenta"
        Write-Status "========================" "Magenta"
    }

    # Run all health checks
    Test-DiskSpace
    Test-DatabaseConnectivity
    Test-DataFreshness
    Test-APIServer
    Test-LogFiles
    Test-Configuration
    Test-DataQuality

    # Generate summary
    if (-not $Quiet) {
        Write-Status "Health Check Results" "Magenta"
        Write-Status "====================" "Magenta"
        Write-Status "Overall Status: $($HealthReport.status.ToUpper())" $(if ($HealthReport.status -eq "healthy") { "Green" } elseif ($HealthReport.status -eq "warning") { "Yellow" } else { "Red" })
        Write-Status "Total Checks: $($HealthReport.summary.total_checks)" "Cyan"
        Write-Status "Passed: $($HealthReport.summary.passed_checks)" "Green"
        Write-Status "Failed: $($HealthReport.summary.failed_checks)" "Red"
        Write-Status "Warnings: $($HealthReport.summary.warning_checks)" "Yellow"

        if ($HealthReport.issues.Count -gt 0) {
            Write-Status "`nIssues Found:" "Red"
            foreach ($Issue in $HealthReport.issues) {
                $Icon = if ($Issue.severity -eq "error") { "✗" } else { "⚠" }
                Write-Host "  $Icon $($Issue.check): $($Issue.message)" -ForegroundColor $(if ($Issue.severity -eq "error") { "Red" } else { "Yellow" })
            }
        }
    }

    # Export report
    $ReportFile = Export-HealthReport

    # Send alerts if needed
    if ($HealthReport.status -ne "healthy") {
        Send-EmailAlert -Report $HealthReport
        Send-SlackAlert -Report $HealthReport
    }

    # Exit with appropriate code
    if ($HealthReport.status -eq "unhealthy") {
        exit 1
    } elseif ($HealthReport.status -eq "warning") {
        exit 2
    } else {
        exit 0
    }
}
catch {
    Write-Error "Health check failed: $_"
    Write-Error "Stack trace: $($_.ScriptStackTrace)"
    exit 3
}