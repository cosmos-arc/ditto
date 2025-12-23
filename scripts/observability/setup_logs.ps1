# Ditto 可观测性 - 日志目录初始化脚本
# 功能: 创建并配置日志目录

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Initialize-LogsDirectory {
    $logDir = "logs"

    Write-ColorOutput "`n========================================" "Cyan"
    Write-ColorOutput "Ditto 日志目录初始化" "Cyan"
    Write-ColorOutput "========================================`n" "Cyan"

    # 创建日志目录
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        Write-ColorOutput "✓ 创建日志目录: $logDir" "Green"
    } else {
        Write-ColorOutput "✓ 日志目录已存在: $logDir" "Green"
    }

    # 创建 .gitkeep 确保 git 追踪空目录
    $gitkeep = Join-Path $logDir ".gitkeep"
    if (-not (Test-Path $gitkeep)) {
        New-Item -ItemType File -Path $gitkeep -Force | Out-Null
        Write-ColorOutput "✓ 创建 .gitkeep 文件" "Green"
    }

    # 创建 .gitignore 排除日志文件
    $gitignore = Join-Path $logDir ".gitignore"
    $gitignoreContent = @"
# 忽略所有日志文件
*.jsonl
*.log
*.log.*

# 但保留 .gitkeep 和 .gitignore
!.gitkeep
!.gitignore
"@

    if (-not (Test-Path $gitignore)) {
        Set-Content -Path $gitignore -Value $gitignoreContent -Encoding UTF8
        Write-ColorOutput "✓ 创建 .gitignore 文件" "Green"
    }

    Write-ColorOutput "`n✓ 日志目录初始化完成!" "Green"
    Write-ColorOutput "`n目录路径: $(Resolve-Path $logDir)`n" "Cyan"
}

Initialize-LogsDirectory
