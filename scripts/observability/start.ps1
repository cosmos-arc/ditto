# Ditto Observability Services Start Script
# Starts VictoriaMetrics, VictoriaLogs, Vector, Grafana

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Test-DockerDesktop {
    Write-ColorOutput "`nChecking Docker Desktop..." "Cyan"
    $dockerVersion = docker version --format "{{.Server.Version}}" 2>$null
    if (-not $?) {
        Write-ColorOutput "[ERROR] Docker Desktop is not running" "Red"
        Write-ColorOutput "Please start Docker Desktop and try again" "Yellow"
        exit 1
    }
    Write-ColorOutput "[OK] Docker Desktop is running (version $dockerVersion)" "Green"
}

function Test-PortAvailability {
    Write-ColorOutput "`nChecking port availability..." "Cyan"
    $ports = @(8428, 9428, 3000, 8686)
    $inUse = @()

    foreach ($port in $ports) {
        $connection = Test-NetConnection -ComputerName localhost -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($connection) {
            $inUse += $port
            Write-ColorOutput "[WARNING] Port $port is in use" "Yellow"
        }
    }

    if ($inUse.Count -gt 0) {
        Write-ColorOutput "[ERROR] Ports are already in use: $($inUse -join ', ')" "Red"
        Write-ColorOutput "Please stop conflicting services or change ports in docker-compose.yml" "Yellow"
        exit 1
    }
    Write-ColorOutput "[OK] All required ports are available" "Green"
}

function Start-Services {
    Write-ColorOutput "`nStarting observability services..." "Cyan"

    Push-Location deploy/observability
    try {
        docker-compose up -d
        Write-ColorOutput "`n[OK] Services started" "Green"
    } catch {
        Write-ColorOutput "`n[ERROR] Failed to start services: $_" "Red"
        exit 1
    } finally {
        Pop-Location
    }
}

function Wait-ForServices {
    Write-ColorOutput "`nWaiting for services to be ready..." "Cyan"
    $services = @(
        @{Name="VictoriaMetrics"; Port=8428; URL="http://localhost:8428/health"},
        @{Name="VictoriaLogs"; Port=9428; URL="http://localhost:9428/health"},
        @{Name="Grafana"; Port=3000; URL="http://localhost:3000/api/health"}
    )

    $timeout = 60
    $startTime = Get-Date

    foreach ($service in $services) {
        $elapsed = 0
        while ($elapsed -lt $timeout) {
            try {
                $response = Invoke-WebRequest -Uri $service.URL -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
                if ($response.StatusCode -eq 200) {
                    Write-ColorOutput "[OK] $($service.Name) is ready" "Green"
                    break
                }
            } catch {
                # Continue waiting
            }
            Start-Sleep -Seconds 2
            $elapsed = (Get-Date) - $startTime
        }

        if ($elapsed -ge $timeout) {
            Write-ColorOutput "[WARNING] $($service.Name) did not respond within ${timeout}s" "Yellow"
        }
    }
}

function Show-ServiceInfo {
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "Service Access Information" "Cyan"
    Write-ColorOutput "========================================`n" "Cyan"

    Write-ColorOutput "Grafana Dashboard:" "Cyan"
    Write-ColorOutput "  URL: http://localhost:3000" "White"
    Write-ColorOutput "  Purpose: Visualization dashboards`n" "White"

    Write-ColorOutput "VictoriaMetrics:" "Cyan"
    Write-ColorOutput "  URL: http://localhost:8428" "White"
    Write-ColorOutput "  Purpose: Metrics query UI`n" "White"

    Write-ColorOutput "VictoriaLogs:" "Cyan"
    Write-ColorOutput "  URL: http://localhost:9428" "White"
    Write-ColorOutput "  Purpose: Logs query UI`n" "White"

    Write-ColorOutput "Vector:" "Cyan"
    Write-ColorOutput "  URL: http://localhost:8686" "White"
    Write-ColorOutput "  Purpose: Log collection status`n" "White"
}

function Show-ContainerStatus {
    Write-ColorOutput "`nCurrent container status:" "Cyan"
    docker ps --filter "name=ditto-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

function Main {
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "Ditto Observability - Start Services" "Cyan"
    Write-ColorOutput "========================================`n" "Cyan"

    Test-DockerDesktop
    Test-PortAvailability
    Start-Services
    Wait-ForServices
    Show-ContainerStatus
    Show-ServiceInfo

    Write-ColorOutput "`n[OK] All services are running" "Green"
    Write-ColorOutput "Run '.\scripts\observability\health_check.ps1' to verify service health`n" "Cyan"
}

Main
