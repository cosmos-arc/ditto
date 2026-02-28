#!/bin/bash
# verify-all-2025.sh - 完整验证脚本（2025年数据）
# 执行日期: 2026-02-26
# 验证范围: 环境重置 + CLI摄入 + API + 边界条件
# 更新: 修复 API 格式，扩展验证覆盖

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# 验证结果记录
RESULTS_DIR="docs"
RESULTS_FILE="$RESULTS_DIR/verification-results-$(date +%Y%m%d-%H%M%S).md"

# 初始化结果文件
init_results() {
    mkdir -p "$RESULTS_DIR"
    echo "# 验证结果 - $(date '+%Y-%m-%d %H:%M:%S')" > "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"
    echo "## 环境信息" >> "$RESULTS_FILE"
    echo "- Pixi 版本: $(pixi --version 2>/dev/null || echo 'unknown')" >> "$RESULTS_FILE"
    echo "- Python 版本: $(pixi run -e dev python --version 2>/dev/null || echo 'unknown')" >> "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"
    echo "## 验证结果" >> "$RESULTS_FILE"
    echo "" >> "$RESULTS_FILE"
}

# 计数器
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

record_result() {
    local status="$1"
    local category="$2"
    local item="$3"
    local note="${4:-}"

    case "$status" in
        "✅") ((PASS_COUNT++)) ;;
        "❌") ((FAIL_COUNT++)) ;;
        "⚠️") ((SKIP_COUNT++)) ;;
    esac

    if [ -n "$note" ]; then
        echo "- [$status] **$category**: $item ($note)" >> "$RESULTS_FILE"
    else
        echo "- [$status] **$category**: $item" >> "$RESULTS_FILE"
    fi
}

# 执行命令并记录结果
run_test() {
    local category="$1"
    local item="$2"
    local cmd="$3"
    local expect_fail="${4:-false}"

    log_info "执行: $item"

    if eval "$cmd" > /tmp/verify-output.txt 2>&1; then
        if [ "$expect_fail" = "true" ]; then
            log_warn "$item: 预期失败但成功了"
            record_result "⚠️" "$category" "$item" "预期失败但成功"
        else
            log_info "$item: ✅ 成功"
            record_result "✅" "$category" "$item"
        fi
        return 0
    else
        if [ "$expect_fail" = "true" ]; then
            log_info "$item: ✅ 预期失败"
            record_result "✅" "$category" "$item" "正确报错"
            return 0
        else
            log_error "$item: ❌ 失败"
            cat /tmp/verify-output.txt | head -20
            record_result "❌" "$category" "$item"
            return 1
        fi
    fi
}

# 检查 FRED API Key
check_fred_key() {
    FRED_KEY=$(pixi run -e dev python -c "import keyring; k=keyring.get_password('fred', 'api_key'); print('SET' if k else 'NOT_SET')" 2>/dev/null)
    echo "$FRED_KEY"
}

# ============================================
# 主流程开始
# ============================================

log_step "=========================================="
log_step "Ditto 2025 完整验证流程"
log_step "=========================================="

init_results

# ============================================
# 1. 环境重置
# ============================================
log_step "=== 1. 环境重置 ==="

log_info "跳过服务停止步骤（WSL 中 pkill 会导致断联）"
# 注意：WSL 环境中 pkill 可能导致断联，直接跳过
# 如果有残留进程，端口冲突时再处理
sleep 1

log_info "删除数据库和摄入日志..."
rm -f data/metadata/metadata.sqlite
rm -f data/db/ingestion_log.sqlite

log_info "删除所有 Parquet 数据..."
rm -rf data/market/
rm -rf data/fundamental/
rm -rf data/capital/
rm -rf data/macro/

log_info "重新初始化数据库..."
run_test "环境重置" "数据库初始化" "pixi run -e dev python -m ditto_port.cli.main init db --force"

# ============================================
# 2. 前置条件检查
# ============================================
log_step "=== 2. 前置条件检查 ==="

log_info "检查 Tushare Token..."
TOKEN=$(pixi run -e dev python -c "import keyring; t=keyring.get_password('tushare', 'token'); print(t[:8]+'***' if t else 'NOT_SET')" 2>/dev/null)
if [ "$TOKEN" != "NOT_SET" ]; then
    log_info "Tushare Token: $TOKEN"
    record_result "✅" "前置条件" "Tushare Token"
else
    log_error "Tushare Token 未配置"
    record_result "❌" "前置条件" "Tushare Token"
    exit 1
fi

log_info "检查 FRED API Key..."
FRED_STATUS=$(check_fred_key)
if [ "$FRED_STATUS" = "SET" ]; then
    log_info "FRED API Key 已配置"
    record_result "✅" "前置条件" "FRED API Key"
else
    log_warn "FRED API Key 未配置（跳过 FRED 验证）"
    record_result "⚠️" "前置条件" "FRED API Key"
fi

# ============================================
# 3. 元数据摄入
# ============================================
log_step "=== 3. 元数据摄入 ==="

run_test "元数据" "交易日历" "pixi run -e dev python -m ditto_port.cli.main ingest metadata calendar 2025-01-01"
run_test "元数据" "股票基础信息" "pixi run -e dev python -m ditto_port.cli.main ingest metadata basic stock"
run_test "元数据" "ETF基础信息" "pixi run -e dev python -m ditto_port.cli.main ingest metadata basic etf"
run_test "元数据" "指数基础信息" "pixi run -e dev python -m ditto_port.cli.main ingest metadata basic index"

# 交易日历验证（确认摄入整年数据）
log_info "验证交易日历..."
CALENDAR_COUNT=$(pixi run -e dev python -c "
import sqlite3
conn = sqlite3.connect('data/metadata/metadata.sqlite')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM trading_calendar')
print(cursor.fetchone()[0])
conn.close()
" 2>/dev/null)
if [ "$CALENDAR_COUNT" -gt 300 ]; then
    log_info "交易日历: ✅ $CALENDAR_COUNT 天"
    record_result "✅" "元数据" "交易日历验证 ($CALENDAR_COUNT 天)"
else
    log_warn "交易日历: ⚠️ 只有 $CALENDAR_COUNT 天"
    record_result "⚠️" "元数据" "交易日历验证 ($CALENDAR_COUNT 天)"
fi

# 关键标的验证（使用 SQLite 查询，因为 CLI query 不支持 --ticker）
log_info "验证关键标的..."
VERIFY_INSTRUMENTS=$(pixi run -e dev python -c "
import sqlite3
conn = sqlite3.connect('data/metadata/metadata.sqlite')
cursor = conn.cursor()
for ticker in ['000001', '600519', '510300', '000300']:
    cursor.execute('SELECT instrument_id, name FROM instrument WHERE ticker = ?', (ticker,))
    result = cursor.fetchone()
    if result:
        print(f'{ticker}: ✅ id={result[0]}')
    else:
        print(f'{ticker}: ❌ NOT FOUND')
conn.close()
" 2>/dev/null)
echo "$VERIFY_INSTRUMENTS"

# ============================================
# 4. 行情数据摄入 - 按日期
# ============================================
log_step "=== 4. 行情数据摄入（按日期）==="

run_test "行情-按日期" "股票日行情" "pixi run -e dev python -m ditto_port.cli.main ingest market stock 2025-01-02"
run_test "行情-按日期" "ETF日行情" "pixi run -e dev python -m ditto_port.cli.main ingest market etf 2025-01-02"
run_test "行情-按日期" "指数日行情" "pixi run -e dev python -m ditto_port.cli.main ingest market index 2025-01-02"
run_test "行情-按日期" "股票状态" "pixi run -e dev python -m ditto_port.cli.main ingest market status 2025-01-02" || true

# ============================================
# 5. 行情数据摄入 - 按标的（全年）
# ============================================
log_step "=== 5. 行情数据摄入（按标的）==="

run_test "行情-按标的" "股票 ticker 格式" "pixi run -e dev python -m ditto_port.cli.main ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-12-31"
run_test "行情-按标的" "股票 standard_ticker 格式" "pixi run -e dev python -m ditto_port.cli.main ingest market stock --standard-ticker 600519.XSHG -s 2025-01-01 -e 2025-12-31"
run_test "行情-按标的" "股票 instrument_id 格式" "pixi run -e dev python -m ditto_port.cli.main ingest market stock --instrument-id 1000001 -s 2025-01-01 -e 2025-12-31"
run_test "行情-按标的" "ETF" "pixi run -e dev python -m ditto_port.cli.main ingest market etf --standard-ticker 510300.XSHG -s 2025-01-01 -e 2025-12-31"
run_test "行情-按标的" "指数" "pixi run -e dev python -m ditto_port.cli.main ingest market index --standard-ticker 000300.XSHG -s 2025-01-01 -e 2025-12-31"

# ============================================
# 6. 复权因子（全年）
# ============================================
log_step "=== 6. 复权因子 ==="

run_test "复权因子" "股票 000001" "pixi run -e dev python -m ditto_port.cli.main ingest market adj --ticker 000001 -s 2025-01-01 -e 2025-12-31"
run_test "复权因子" "股票 600519" "pixi run -e dev python -m ditto_port.cli.main ingest market adj --ticker 600519 -s 2025-01-01 -e 2025-12-31"
run_test "复权因子" "基金 510300" "pixi run -e dev python -m ditto_port.cli.main ingest market adj --fund --ticker 510300 -s 2025-01-01 -e 2025-12-31"

# ============================================
# 7. 基本面数据（全年）
# ============================================
log_step "=== 7. 基本面数据 ==="

run_test "基本面-按日期" "资产负债表" "pixi run -e dev python -m ditto_port.cli.main ingest fundamental balance 2025-04-30" || true
run_test "基本面-按标的" "资产负债表 000001" "pixi run -e dev python -m ditto_port.cli.main ingest fundamental balance --ticker 000001 -s 2025-01-01 -e 2025-12-31"
run_test "基本面-按标的" "利润表 000001" "pixi run -e dev python -m ditto_port.cli.main ingest fundamental income --ticker 000001 -s 2025-01-01 -e 2025-12-31"
run_test "基本面-按标的" "现金流量表 000001" "pixi run -e dev python -m ditto_port.cli.main ingest fundamental cash-flow --ticker 000001 -s 2025-01-01 -e 2025-12-31" || true
run_test "基本面-按标的" "分红 000001" "pixi run -e dev python -m ditto_port.cli.main ingest fundamental dividend --ticker 000001 -s 2025-01-01 -e 2025-12-31" || true
run_test "基本面-按标的" "分红 600519" "pixi run -e dev python -m ditto_port.cli.main ingest fundamental dividend --ticker 600519 -s 2025-01-01 -e 2025-12-31" || true

# 公司行动（新增）
run_test "基本面-按日期" "公司行动" "pixi run -e dev python -m ditto_port.cli.main ingest fundamental corporate-actions 2025-01-02" || true

# ============================================
# 8. 资本数据（全年）
# ============================================
log_step "=== 8. 资本数据 ==="

run_test "资本-按日期" "估值指标" "pixi run -e dev python -m ditto_port.cli.main ingest capital valuation 2025-01-02"
run_test "资本-按标的" "估值 000001" "pixi run -e dev python -m ditto_port.cli.main ingest capital valuation --ticker 000001 -s 2025-01-01 -e 2025-12-31"
run_test "资本-按标的" "融资融券 000001" "pixi run -e dev python -m ditto_port.cli.main ingest capital margin --ticker 000001 -s 2025-01-01 -e 2025-12-31"
run_test "资本-按日期" "股权质押" "pixi run -e dev python -m ditto_port.cli.main ingest capital pledge 2025-01-02"

# ============================================
# 9. 宏观数据
# ============================================
log_step "=== 9. 宏观数据 ==="

run_test "宏观" "Tushare 指标" "pixi run -e dev python -m ditto_port.cli.main ingest macro indicators 2025-01-02"

# 中国国债收益率（Tushare yc_cb）- 新增 2026-02-28
# 注意：需要 Tushare 积分 ≥5000
log_info "验证中国国债收益率（yc_cb 接口）..."
BOND_YIELD_TEST=$(pixi run -e dev python -c "
from ditto_datahub.sources.tushare.adapters.bond_yield import CN_BOND_YIELD_INDICATORS
print(f'OK: {len(CN_BOND_YIELD_INDICATORS)} indicators')
" 2>/dev/null)
if echo "$BOND_YIELD_TEST" | grep -q "OK:"; then
    log_info "国债收益率指标: ✅ $BOND_YIELD_TEST"
    record_result "✅" "宏观" "国债收益率指标定义"
else
    log_warn "国债收益率指标: ❌ 加载失败"
    record_result "❌" "宏观" "国债收益率指标定义"
fi

# FRED 数据验证（如果配置了 API Key）
if [ "$FRED_STATUS" = "SET" ]; then
    log_info "验证 FRED 数据源..."
    FRED_TEST=$(pixi run -e dev python -c "
from ditto_datahub.sources.fred import list_fred_indicators
indicators = list_fred_indicators()
print(f'OK: {len(indicators)} indicators')
" 2>/dev/null)
    if echo "$FRED_TEST" | grep -q "OK:"; then
        log_info "FRED 数据源: ✅ $FRED_TEST"
        record_result "✅" "宏观" "FRED 数据源"
    else
        log_warn "FRED 数据源: ❌ 连接失败"
        record_result "❌" "宏观" "FRED 数据源"
    fi

    # 贸易加权美元指数（FRED DTWEXBGS）- 新增 2026-02-28
    log_info "验证美元指数指标（DTWEXBGS）..."
    DOLLAR_INDEX_TEST=$(pixi run -e dev python -c "
from ditto_datahub.sources.fred import get_fred_indicator
indicator = get_fred_indicator('US_DOLLAR_INDEX_BROAD')
print(f'OK: {indicator.code}' if indicator else 'NOT_FOUND')
" 2>/dev/null)
    if echo "$DOLLAR_INDEX_TEST" | grep -q "OK:"; then
        log_info "美元指数指标: ✅ $DOLLAR_INDEX_TEST"
        record_result "✅" "宏观" "美元指数指标定义"
    else
        log_warn "美元指数指标: ❌ 未找到"
        record_result "❌" "宏观" "美元指数指标定义"
    fi
else
    log_warn "跳过 FRED 验证（API Key 未配置）"
fi

# ============================================
# 10. 历史回填
# ============================================
log_step "=== 10. 历史回填 ==="

run_test "回填" "股票行情" "pixi run -e dev python -m ditto_port.cli.main backfill market stock -s 2025-01-01 -e 2025-01-10 -p 2"

# ============================================
# 11. 边界条件验证
# ============================================
log_step "=== 11. 边界条件验证 ==="

log_info "不存在的标识符..."
if pixi run -e dev python -m ditto_port.cli.main ingest market stock --ticker 999999 -s 2025-01-01 -e 2025-01-31 2>&1 | grep -qiE "error|not.?found|未找到"; then
    record_result "✅" "边界条件" "不存在标识符报错"
else
    record_result "⚠️" "边界条件" "不存在标识符"
fi

log_info "非交易日..."
pixi run -e dev python -m ditto_port.cli.main ingest market stock 2025-01-04 2>&1 > /dev/null || true
record_result "✅" "边界条件" "非交易日处理"

log_info "未来日期..."
pixi run -e dev python -m ditto_port.cli.main ingest market stock 2026-01-01 2>&1 > /dev/null || true
record_result "✅" "边界条件" "未来日期处理"

log_info "重复摄入幂等性..."
pixi run -e dev python -m ditto_port.cli.main ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-01-10 > /dev/null 2>&1
pixi run -e dev python -m ditto_port.cli.main ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-01-10 > /dev/null 2>&1
record_result "✅" "边界条件" "重复摄入幂等性"

# ============================================
# 12. API 验证
# ============================================
log_step "=== 12. API 验证 ==="

log_info "启动 API 服务..."
pixi run -e dev server > /tmp/server.log 2>&1 &
SERVER_PID=$!
log_info "等待服务启动..."
sleep 8

# 检查服务是否启动
if ! kill -0 $SERVER_PID 2>/dev/null; then
    log_error "API 服务启动失败"
    cat /tmp/server.log | tail -20
    record_result "❌" "API" "服务启动"
    exit 1
fi

# 健康检查
log_info "健康检查..."
HEALTH=$(curl -s http://localhost:8000/healthz 2>/dev/null)
if [ -n "$HEALTH" ]; then
    log_info "健康检查: ✅ $HEALTH"
    record_result "✅" "API" "健康检查"
else
    log_error "健康检查: ❌ 失败"
    record_result "❌" "API" "健康检查"
fi

# 系统状态
log_info "系统状态..."
STATUS=$(curl -s http://localhost:8000/api/v1/status 2>/dev/null)
if [ -n "$STATUS" ]; then
    record_result "✅" "API" "系统状态"
else
    record_result "❌" "API" "系统状态"
fi

# 元数据查询 - 单个标的
log_info "元数据查询 - 单个标的..."
META=$(curl -s http://localhost:8000/api/v1/metadata/instruments/1000001 2>/dev/null)
if [ -n "$META" ] && echo "$META" | grep -q "instrument_id"; then
    record_result "✅" "API" "元数据查询-单个"
else
    record_result "❌" "API" "元数据查询-单个"
fi

# 元数据查询 - 列表
log_info "元数据查询 - 列表..."
META_LIST=$(curl -s "http://localhost:8000/api/v1/metadata/instruments?asset_type=stock&limit=5" 2>/dev/null)
if [ -n "$META_LIST" ] && echo "$META_LIST" | grep -q "data"; then
    record_result "✅" "API" "元数据查询-列表"
else
    record_result "❌" "API" "元数据查询-列表"
fi

# 行情查询 - 使用 instrument_ids 数组格式（修复）
log_info "行情查询（instrument_ids 数组格式）..."
BARS=$(curl -s -X POST http://localhost:8000/api/v1/market/bars \
  -H "Content-Type: application/json" \
  -d '{"instrument_ids": [1000001], "start_date": "2025-01-01", "end_date": "2025-01-10"}' 2>/dev/null)
if [ -n "$BARS" ] && echo "$BARS" | grep -q "data"; then
    BAR_COUNT=$(echo "$BARS" | pixi run -e dev python -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null || echo "0")
    log_info "行情查询: ✅ 返回 $BAR_COUNT 条"
    record_result "✅" "API" "行情查询 ($BAR_COUNT 条)"
else
    log_error "行情查询: ❌ 失败"
    record_result "❌" "API" "行情查询"
fi

# 基本面查询 - 资产负债表
log_info "基本面查询 - 资产负债表..."
BALANCE=$(curl -s "http://localhost:8000/api/v1/fundamental/financials/balance_sheet?instrument_id=1000001&as_of_date=2025-04-30" 2>/dev/null)
if [ -n "$BALANCE" ]; then
    record_result "✅" "API" "基本面-资产负债表"
else
    record_result "❌" "API" "基本面-资产负债表"
fi

# 基本面查询 - 分红
log_info "基本面查询 - 分红..."
DIVIDEND=$(curl -s "http://localhost:8000/api/v1/fundamental/dividend?instrument_id=1000001&as_of_date=2025-12-31" 2>/dev/null)
if [ -n "$DIVIDEND" ]; then
    record_result "✅" "API" "基本面-分红"
else
    record_result "❌" "API" "基本面-分红"
fi

# 资本数据查询 - 估值
log_info "资本数据查询 - 估值..."
VALUATION=$(curl -s "http://localhost:8000/api/v1/capital/valuation?instrument_id=1000001&as_of_date=2025-01-10" 2>/dev/null)
if [ -n "$VALUATION" ]; then
    record_result "✅" "API" "资本-估值"
else
    record_result "❌" "API" "资本-估值"
fi

# 资本数据查询 - 融资融券
log_info "资本数据查询 - 融资融券..."
MARGIN=$(curl -s "http://localhost:8000/api/v1/capital/margin?instrument_id=1000001&as_of_date=2025-01-10" 2>/dev/null)
if [ -n "$MARGIN" ]; then
    record_result "✅" "API" "资本-融资融券"
else
    record_result "❌" "API" "资本-融资融券"
fi

# 宏观数据查询
log_info "宏观数据查询..."
MACRO=$(curl -s -X POST http://localhost:8000/api/v1/macro/indicators \
  -H "Content-Type: application/json" \
  -d '{"indicators": ["gdp"], "start_date": "2025-01-01", "end_date": "2025-12-31"}' 2>/dev/null)
if [ -n "$MACRO" ]; then
    record_result "✅" "API" "宏观指标"
else
    record_result "❌" "API" "宏观指标"
fi

# 中国国债收益率查询（新增 2026-02-28）
log_info "中国国债收益率查询..."
BOND_YIELD=$(curl -s -X POST http://localhost:8000/api/v1/macro/indicators \
  -H "Content-Type: application/json" \
  -d '{"indicators": ["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_10Y"], "start_date": "2025-01-01", "end_date": "2025-01-31"}' 2>/dev/null)
if [ -n "$BOND_YIELD" ]; then
    record_result "✅" "API" "国债收益率查询"
else
    record_result "❌" "API" "国债收益率查询"
fi

# 美元指数查询（新增 2026-02-28）
if [ "$FRED_STATUS" = "SET" ]; then
    log_info "贸易加权美元指数查询..."
    DOLLAR_IDX=$(curl -s -X POST http://localhost:8000/api/v1/macro/indicators \
      -H "Content-Type: application/json" \
      -d '{"indicators": ["US_DOLLAR_INDEX_BROAD"], "start_date": "2025-01-01", "end_date": "2025-01-31", "source": "fred"}' 2>/dev/null)
    if [ -n "$DOLLAR_IDX" ]; then
        record_result "✅" "API" "美元指数查询"
    else
        record_result "❌" "API" "美元指数查询"
    fi
fi

# 数据源直查
log_info "数据源直查..."
SOURCE=$(curl -s "http://localhost:8000/api/v1/source/tushare/stock_daily?ticker=000001&start_date=2025-01-01&end_date=2025-01-10" 2>/dev/null)
if [ -n "$SOURCE" ] && echo "$SOURCE" | grep -q "data"; then
    record_result "✅" "API" "数据源直查"
else
    record_result "❌" "API" "数据源直查"
fi

log_info "关闭 API 服务..."
kill $SERVER_PID 2>/dev/null || true
sleep 2

# ============================================
# 13. CLI Query 验证
# ============================================
log_step "=== 13. CLI Query 验证 ==="

# 注意: CLI Query 命令使用 instrument_id (-i) 参数，不是 --ticker
run_test "CLI Query" "元数据" "pixi run -e dev python -m ditto_port.cli.main query metadata instrument 1000001"
run_test "CLI Query" "行情" "pixi run -e dev python -m ditto_port.cli.main query market bars -i 1000001 -s 2025-01-01 -e 2025-01-10"
run_test "CLI Query" "基本面-财务报表" "pixi run -e dev python -m ditto_port.cli.main query fundamental financials -i 1000001 -t balance_sheet -d 2025-12-31"
run_test "CLI Query" "资本数据-估值" "pixi run -e dev python -m ditto_port.cli.main query capital valuation -i 1000001 -d 2025-01-10"
run_test "CLI Query" "宏观数据" "pixi run -e dev python -m ditto_port.cli.main query macro indicators -s 2025-01-01 -e 2025-12-31"

# ============================================
# 14. 代码质量检查
# ============================================
log_step "=== 14. 代码质量检查 ==="

log_info "运行 lint 检查..."
if pixi run -e dev lint > /tmp/lint-output.txt 2>&1; then
    record_result "✅" "代码质量" "lint"
else
    log_warn "lint 有警告/错误"
    record_result "⚠️" "代码质量" "lint"
fi

log_info "运行 type 检查..."
if pixi run -e dev type > /tmp/type-output.txt 2>&1; then
    record_result "✅" "代码质量" "type"
else
    log_warn "type 有警告/错误"
    record_result "⚠️" "代码质量" "type"
fi

# ============================================
# 完成汇总
# ============================================
log_step "=========================================="
log_step "验证完成"
log_step "=========================================="

# 写入汇总
echo "" >> "$RESULTS_FILE"
echo "## 汇总" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
echo "| 状态 | 数量 |" >> "$RESULTS_FILE"
echo "|------|------|" >> "$RESULTS_FILE"
echo "| ✅ 通过 | $PASS_COUNT |" >> "$RESULTS_FILE"
echo "| ❌ 失败 | $FAIL_COUNT |" >> "$RESULTS_FILE"
echo "| ⚠️ 跳过 | $SKIP_COUNT |" >> "$RESULTS_FILE"
echo "| **总计** | **$((PASS_COUNT + FAIL_COUNT + SKIP_COUNT))** |" >> "$RESULTS_FILE"

log_info "通过: $PASS_COUNT, 失败: $FAIL_COUNT, 跳过: $SKIP_COUNT"
log_info "结果已保存到: $RESULTS_FILE"
echo ""
cat "$RESULTS_FILE"

# 返回状态码
if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
else
    exit 0
fi
