# Ditto 可观测性服务启动脚本
# 功能: 启动 VictoriaMetrics、VictoriaLogs、Vector、Grafana

$ErrorActionPreference = "Stop"

# 颜色输出函数
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

# 检查 Docker Desktop 是否运行
function Test-DockerDesktop {
    Write-ColorOutput "检查 Docker Desktop 状态..." "Cyan"
    try {
        $null = docker version 2>&1
        Write-ColorOutput "✓ Docker Desktop 运行正常" "Green"
        return $true
    } catch {
        Write-ColorOutput "✗ Docker Desktop 未运行" "Red"
        Write-ColorOutput "请先启动 Docker Desktop，然后重新运行此脚本" "Yellow"
        return $false
    }
}

# 检查端口占用
function Test-PortOccupied {
    param(
        [int]$Port
    )
    $connection = Test-NetConnection -ComputerName localhost -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
    return $connection -eq "Success"
}

function Show-PortCheck {
    Write-ColorOutput "`n检查端口占用..." "Cyan"
    $ports = @{
        "VictoriaMetrics" = 8428
        "VictoriaLogs"     = 9428
        "Vector"           = 8686
        "Grafana"          = 3000
    }

    $occupied = @()
    foreach ($service in $ports.Keys) {
        $port = $ports[$service]
        if (Test-PortOccupied -Port $port) {
            Write-ColorOutput "✗ 端口 $port ($service) 已被占用" "Red"
            $occupied += $service
        } else {
            Write-ColorOutput "✓ 端口 $port ($service) 可用" "Green"
        }
    }

    if ($occupied.Count -gt 0) {
        Write-ColorOutput "`n以下服务端口已被占用: $($occupied -join ', ')" "Red"
        $response = Read-Host "是否继续启动? (y/N)"
        if ($response -ne "y") {
            exit 1
        }
    }
}

# 创建必要的目录
function Initialize-Directories {
    Write-ColorOutput "`n初始化目录..." "Cyan"
    $dirs = @(
        "logs",
        "deploy/observability"
    )

    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-ColorOutput "✓ 创建目录: $dir" "Green"
        }
    }
}

# 启动 Docker Compose 服务
function Start-Services {
    Write-ColorOutput "`n启动可观测性服务..." "Cyan"

    Push-Location deploy/observability
    try {
        docker-compose up -d
        Write-ColorOutput "`n✓ 服务启动成功!" "Green"
    } catch {
        Write-ColorOutput "`n✗ 服务启动失败: $_" "Red"
        exit 1
    } finally {
        Pop-Location
    }
}

# 等待服务就绪
function Wait-ServiceReady {
    Write-ColorOutput "`n等待服务就绪..." "Cyan"

    $services = @(
        @{ Name = "VictoriaMetrics"; Url = "http://localhost:8428/health" },
        @{ Name = "VictoriaLogs"; Url = "http://localhost:9428/health" },
        @{ Name = "Vector"; Url = "http://localhost:8686/health" },
        @{ Name = "Grafana"; Url = "http://localhost:3000/api/health" }
    )

    $maxWait = 60
    foreach ($service in $services) {
        $elapsed = 0
        while ($elapsed -lt $maxWait) {
            try {
                $response = Invoke-WebRequest -Uri $service.Url -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) {
                    Write-ColorOutput "✓ $($service.Name) 就绪" "Green"
                    break
                }
            } catch {
                # 继续等待
            }
            Start-Sleep -Seconds 2
            $elapsed += 2
            Write-Host "." -NoNewline
        }

        if ($elapsed -ge $maxWait) {
            Write-ColorOutput "`n✗ $($service.Name) 启动超时" "Yellow"
        }
    }
    Write-Host ""
}

# 显示访问信息
function Show-AccessInfo {
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "可观测性服务访问地址:" "Cyan"
    Write-ColorOutput "========================================" "Cyan"
    Write-ColorOutput "  Grafana:          http://localhost:3000" "White"
    Write-ColorOutput "  VictoriaMetrics:  http://localhost:8428" "White"
    Write-ColorOutput "  VictoriaLogs:     http://localhost:9428" "White"
    Write-ColorOutput "  Vector:           http://localhost:8686" "White"
    Write-ColorOutput "========================================`n" "Cyan"
}

# 主函数
function Main {
    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "Ditto 可观测性服务启动脚本" "Cyan"
    Write-ColorOutput "========================================`n" "Cyan"

    # 检查 Docker Desktop
    if (-not (Test-DockerDesktop)) {
        exit 1
    }

    # 检查端口
    Show-PortCheck

    # 初始化目录
    Initialize-Directories

    # 启动服务
    Start-Services

    # 等待服务就绪
    Wait-ServiceReady

    # 显示访问信息
    Show-AccessInfo
}

Main
