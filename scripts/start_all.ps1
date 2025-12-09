# Ditto System Startup Script
# This script starts all components of the Ditto quantitative trading system

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("development", "testing", "production")]
    [string]$Environment = "development",

    [Parameter(Mandatory=$false)]
    [switch]$NoDataUpdate,

    [Parameter(Mandatory=$false)]
    [switch]$NoValidation,

    [Parameter(Mandatory=$false)]
    [switch]$Detach,

    [Parameter(Mandatory=$false)]
    [int]$ServerPort = 8000
)

# Script configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir

# Color output functions
function Write-Status {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
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

# Check if pixi is installed
function Test-PixiInstalled {
    try {
        pixi --version | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

# Check if required directories exist
function Test-Directories {
    $RequiredDirs = @(
        "$ProjectRoot\logs",
        "$ProjectRoot\data",
        "$ProjectRoot\backups"
    )

    foreach ($Dir in $RequiredDirs) {
        if (!(Test-Path $Dir)) {
            Write-Info "Creating directory: $Dir"
            New-Item -ItemType Directory -Path $Dir -Force | Out-Null
        }
    }
}

# Check environment file
function Test-EnvironmentFile {
    $EnvFile = "$ProjectRoot\.env"
    if (!(Test-Path $EnvFile)) {
        Write-Warning ".env file not found. Copying from .env.example"
        if (Test-Path "$ProjectRoot\.env.example") {
            Copy-Item "$ProjectRoot\.env.example" $EnvFile
            Write-Warning "Please edit .env file with your configuration"
        } else {
            Write-Error ".env.example file not found!"
            exit 1
        }
    }
}

# Initialize database
function Initialize-Database {
    Write-Info "Initializing database..."
    try {
        Set-Location $ProjectRoot
        pixi run python scripts\init_db.py
        Write-Success "Database initialized"
    }
    catch {
        Write-Error "Failed to initialize database: $_"
        exit 1
    }
}

# Update data if requested
function Update-Data {
    if ($NoDataUpdate) {
        Write-Info "Skipping data update (--no-data-update specified)"
        return
    }

    Write-Info "Updating market data..."
    try {
        Set-Location $ProjectRoot
        pixi run python scripts\update_data.py daily --start-date "$(Get-Date).AddDays(-7).ToString('yyyy-MM-dd')" --end-date "$(Get-Date).ToString('yyyy-MM-dd')"
        Write-Success "Market data updated"
    }
    catch {
        Write-Warning "Failed to update market data: $_"
        Write-Warning "System will start with existing data"
    }
}

# Run data quality check
function Run-DataValidation {
    if ($NoValidation) {
        Write-Info "Skipping data validation (--no-validation specified)"
        return
    }

    Write-Info "Running data quality health check..."
    try {
        Set-Location $ProjectRoot
        $Result = pixi run python scripts\check_data_quality.py health --sample-size 3 --days-back 5
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Data quality check passed"
        } else {
            Write-Warning "Data quality check found issues"
        }
    }
    catch {
        Write-Warning "Failed to run data validation: $_"
    }
}

# Start API server
function Start-APIServer {
    Write-Info "Starting FastAPI server on port $ServerPort..."
    $ServerScript = "$ProjectRoot\apps\server\src\main.py"

    if (!(Test-Path $ServerScript)) {
        Write-Error "Server script not found: $ServerScript"
        exit 1
    }

    try {
        if ($Detach) {
            Write-Info "Starting server in background..."
            $Process = Start-Process -FilePath "pixi" -ArgumentList "run", "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", $ServerPort, "--reload" -WorkingDirectory "$(Split-Path $ServerScript)" -PassThru
            $ServerPid = $Process.Id
            Write-Success "Server started with PID: $ServerPid"
            return $ServerPid
        } else {
            Set-Location $(Split-Path $ServerScript)
            pixi run uvicorn main:app --host 0.0.0.0 --port $ServerPort --reload
        }
    }
    catch {
        Write-Error "Failed to start server: $_"
        exit 1
    }
}

# Monitor system health
function Monitor-System {
    Write-Info "Starting system health monitoring..."
    $HealthScript = "$ProjectRoot\scripts\health_check.ps1"

    if (Test-Path $HealthScript) {
        try {
            # Start health check in background
            Start-Job -ScriptBlock {
                param($ScriptPath)
                while ($true) {
                    & $ScriptPath -Quiet
                    Start-Sleep -Seconds 60
                }
            } -ArgumentList $HealthScript | Out-Null
            Write-Success "Health monitoring started"
        }
        catch {
            Write-Warning "Failed to start health monitoring: $_"
        }
    }
}

# Setup cleanup on exit
function Setup-Cleanup {
    if ($Detach) {
        # Create cleanup script for detached mode
        $CleanupScript = "$ProjectRoot\scripts\cleanup.ps1"
        @"
# Cleanup script for Ditto system
# Run this to stop all background processes

Write-Host "Stopping Ditto system..."

# Stop server by PID if known
`$ServerPid = Get-Content "$ProjectRoot\.server.pid" -ErrorAction SilentlyContinue
if (`$ServerPid) {
    try {
        Stop-Process -Id `$ServerPid -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped server PID: `$ServerPid"
    }
    catch {
        Write-Warning "Failed to stop server PID `$ServerPid"
    }
}

# Clean up PID file
Remove-Item "$ProjectRoot\.server.pid" -ErrorAction SilentlyContinue

# Stop any pixi processes related to ditto
Get-Process pixi -ErrorAction SilentlyContinue | Where-Object {$_.CommandLine -like "*ditto*"} | Stop-Process -Force

Write-Host "Ditto system stopped"
"@ | Out-File -FilePath $CleanupScript -Encoding UTF8

        Write-Info "Created cleanup script: scripts\cleanup.ps1"
    }
}

# Main execution
try {
    Write-Status "Ditto Quantitative Trading System" "Magenta"
    Write-Status "Environment: $Environment" "Magenta"
    Write-Status "====================================" "Magenta"

    # Pre-flight checks
    Write-Info "Running pre-flight checks..."

    if (!(Test-PixiInstalled)) {
        Write-Error "Pixi is not installed. Please install pixi first: https://pixi.sh"
        exit 1
    }
    Write-Success "Pixi is installed"

    Test-Directories
    Write-Success "Required directories checked"

    Test-EnvironmentFile
    Write-Success "Environment file checked"

    # Set environment variable
    $env:DITTO_ENV = $Environment

    # Initialize system
    Write-Info "Initializing Ditto system..."
    Initialize-Database

    # Update data
    Update-Data

    # Validate data
    Run-DataValidation

    # Start services
    Write-Info "Starting system services..."

    $ServerPid = Start-APIServer

    if ($Detach) {
        # Save server PID for cleanup
        $ServerPid | Out-File -FilePath "$ProjectRoot\.server.pid" -Encoding UTF8
        Setup-Cleanup

        # Start monitoring
        Monitor-System

        Write-Success "Ditto system started in detached mode!"
        Write-Info "Server running on: http://localhost:$ServerPort"
        Write-Info "API Documentation: http://localhost:$ServerPort/docs"
        Write-Info "To stop: .\scripts\cleanup.ps1"
    }

    exit 0
}
catch {
    Write-Error "Startup failed: $_"
    Write-Error "Stack trace: $($_.ScriptStackTrace)"
    exit 1
}
finally {
    # Clean up if not in detached mode
    if (!$Detach -and $ServerPid) {
        try {
            Stop-Process -Id $ServerPid -Force -ErrorAction SilentlyContinue
        }
        catch {
            # Ignore cleanup errors
        }
    }
}
