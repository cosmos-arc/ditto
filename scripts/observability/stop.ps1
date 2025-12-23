# Ditto Observability Services Stop Script
# Stops VictoriaMetrics, VictoriaLogs, Vector, Grafana

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Stop-Services {
    Write-ColorOutput "`nStopping observability services..." "Cyan"

    Push-Location deploy/observability
    try {
        docker-compose down
        Write-ColorOutput "`n[OK] Services stopped" "Green"
    } catch {
        Write-ColorOutput "`n[ERROR] Failed to stop services: $_" "Red"
        exit 1
    } finally {
        Pop-Location
    }
}

function Show-ContainerStatus {
    Write-ColorOutput "`nCurrent container status:" "Cyan"
    docker ps -a --filter "name=ditto-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

function Main {
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "Ditto Observability - Stop Services" "Cyan"
    Write-ColorOutput "========================================`n" "Cyan"

    Stop-Services
    Show-ContainerStatus

    $response = Read-Host "`nRemove data volumes? (y/N)"
    if ($response -eq "y") {
        Write-ColorOutput "`nRemoving data volumes..." "Yellow"
        Push-Location deploy/observability
        docker-compose down -v
        Pop-Location
        Write-ColorOutput "[OK] Data volumes removed" "Green"
    }
}

Main
