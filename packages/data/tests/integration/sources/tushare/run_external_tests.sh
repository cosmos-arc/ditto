#!/bin/bash
# Tushare 端到端集成测试运行脚本
#
# 使用方法：
#   ./run_external_tests.sh
#
# 前置条件：
#   1. 已设置 TUSHARE_TOKEN 环境变量
#   2. 网络连接正常

set -e

echo "=========================================="
echo "Tushare 端到端集成测试"
echo "=========================================="
echo ""

# 检查 TUSHARE_TOKEN
if [ -z "$TUSHARE_TOKEN" ]; then
    echo "错误：未设置 TUSHARE_TOKEN 环境变量"
    echo ""
    echo "请先设置 token："
    echo "  export TUSHARE_TOKEN='your_token_here'"
    echo ""
    exit 1
fi

echo "Token: ${TUSHARE_TOKEN:0:10}...（已脱敏）"
echo ""

# 运行测试
echo "运行测试..."
echo ""

pixi run -e dev pytest \
    packages/datahub/tests/integration/sources/tushare/test_end_to_end.py \
    -m external \
    -v \
    --tb=short

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
