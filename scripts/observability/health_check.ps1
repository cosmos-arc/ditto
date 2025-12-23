# Ditto 可观测性服务健康检查脚本
# 功能: 检查 VictoriaMetrics、VictoriaLogs、Vector、Grafana 健康状态

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Test-ServiceHealth {
    param(
        [string]$Name,
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            return @{
                Name   = $Name
                Status = "Healthy"
                Color  = "Green"
            }
        } else {
            return @{
                Name   = $Name
                Status = "Unhealthy ($($response.StatusCode))"
                Color  = "Red"
            }
        }
    } catch {
        return @{
            Name   = $Name
            Status = "Unreachable"
            Color  = "Red"
        }
    }
}

function Get-DockerContainerStatus {
    $containers = docker ps --filter "name=ditto-" --format "{{.Names}}" 2>$null
    if ($containers) {
        return $containers -split "`n"
    }
    return @()
}

function Show-HealthReport {
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "Ditto 可观测性服务健康检查" "Cyan"
    Write-ColorOutput "========================================`n" "Cyan"

    # Docker 容器状态
    Write-ColorOutput "Docker 容器状态:" "Cyan"
    $runningContainers = Get-DockerContainerStatus
    if ($runningContainers.Count -eq 0) {
        Write-ColorOutput "✗ 没有运行中的 Ditto 容器" "Red"
        Write-ColorOutput "`n提示: 运行 .\scripts\observability\start.ps1 启动服务" "Yellow"
        exit 1
    }

    foreach ($container in $runningContainers) {
        Write-ColorOutput "  ✓ $container" "Green"
    }

    # 服务健康状态
    Write-ColorOutput "`n服务健康状态:" "Cyan"

    $services = @(
        @{ Name = "VictoriaMetrics"; Url = "http://localhost:8428/health" },
        @{ Name = "VictoriaLogs"; Url = "http://localhost:9428/health" },
        @{ Name = "Vector"; Url = "http://localhost:8686/health" },
        @{ Name = "Grafana"; Url = "http://localhost:3000/api/health" }
    )

    $allHealthy = $true
    $results = @()

    foreach ($service in $services) {
        $result = Test-ServiceHealth -Name $service.Name -Url $service.Url
        $results += $result
        if ($result.Color -ne "Green") {
            $allHealthy = $false
        }
        Write-ColorOutput "  $($result.Name): " -NoNewline
        Write-ColorOutput $result.Status $result.Color
    }

    # 总结
    Write-ColorOutput "`n========================================" "Cyan"
    if ($allHealthy) {
        Write-ColorOutput "✓ 所有服务运行正常" "Green"
    } else {
        Write-ColorOutput "✗ 部分服务异常" "Red"
    }
    Write-ColorOutput "========================================`n" "Cyan"

    # 显示访问地址
    if ($allHealthy) {
        Write-ColorOutput "访问地址:" "Cyan"
        Write-ColorOutput "  Grafana:          http://localhost:3000" "White"
        Write-ColorOutput "  VictoriaMetrics:  http://localhost:8428" "White"
        Write-ColorOutput "  VictoriaLogs:     http://localhost:9428" "White"
        Write-ColorOutput "  Vector:           http://localhost:8686`n" "White"
    }

    return $allHealthy
}

function Main {
    $allHealthy = Show-HealthReport
    exit $(if ($allHealthy) { 0 } else { 1 })
}

Main
