@echo off
REM Tushare 端到端集成测试运行脚本 (Windows)
REM
REM 使用方法：
REM   run_external_tests.bat
REM
REM 前置条件：
REM   1. 已设置 TUSHARE_TOKEN 环境变量
REM   2. 网络连接正常

setlocal enabledelayedexpansion

echo ==========================================
echo Tushare 端到端集成测试
echo ==========================================
echo.

REM 检查 TUSHARE_TOKEN
if "%TUSHARE_TOKEN%"=="" (
    echo 错误：未设置 TUSHARE_TOKEN 环境变量
    echo.
    echo 请先设置 token：
    echo   set TUSHARE_TOKEN=your_token_here
    echo.
    exit /b 1
)

REM 显示 token（脱敏）
set TOKEN_MASK=%TUSHARE_TOKEN:~0,10%
echo Token: %TOKEN_MASK%...（已脱敏）
echo.

REM 运行测试
echo 运行测试...
echo.

pixi run -e dev pytest ^
    packages/datahub/tests/integration/sources/tushare/test_end_to_end.py ^
    -m external ^
    -v ^
    --tb=short

echo.
echo ==========================================
echo 测试完成
echo ==========================================

endlocal
