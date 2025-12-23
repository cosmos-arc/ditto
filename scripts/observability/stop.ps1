# Ditto 可观测性服务停止脚本
# 功能: 停止 VictoriaMetrics、VictoriaLogs、Vector、Grafana

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Stop-Services {
    Write-ColorOutput "`n停止可观测性服务..." "Cyan"

    Push-Location deploy/observability
    try {
        docker-compose down
        Write-ColorOutput "`n✓ 服务已停止" "Green"
    } catch {
        Write-ColorOutput "`n✗ 停止服务失败: $_" "Red"
        exit 1
    } finally {
        Pop-Location
    }
}

function Show-ContainerStatus {
    Write-ColorOutput "`n当前容器状态:" "Cyan"
    docker ps -a --filter "name=ditto-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

function Main {
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "Ditto 可观测性服务停止脚本" "Cyan"
    Write-ColorOutput "========================================`n" "Cyan"

    Stop-Services
    Show-ContainerStatus

    $response = Read-Host "`n是否清理数据卷? (y/N)"
    if ($response -eq "y") {
        Write-ColorOutput "`n清理数据卷..." "Yellow"
        Push-Location deploy/observability
        docker-compose down -v
        Pop-Location
        Write-ColorOutput "✓ 数据卷已清理" "Green"
    }
}

Main
