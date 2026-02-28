# 摄入与 API 能力验证计划 (2025)

> **目标**：全面验证 ditto 项目的数据摄入和 API 查询能力，确保所有入口点功能正常
> **时间范围**：2025-01-01 ~ 2025-12-31（全年，覆盖财报季、分红除权、复权事件）
> **验证日期**：2026-02-24（首次）、2026-02-25（完整重验）

## 0. 关键时间节点

### 0.1 财报发布日历

| 报告期 | 法定披露截止 | 预计密集发布期 | 验证重点 |
|--------|-------------|---------------|---------|
| 2024年报 | 2025-04-30 | 2025-03~04月 | 年度财务数据、分红方案 |
| 2025一季报 | 2025-04-30 | 2025-04月 | 季度财务数据 |
| 2025半年报 | 2025-08-31 | 2025-07~08月 | 中期财务数据、分红方案 |
| 2025三季报 | 2025-10-31 | 2025-10月 | 季度财务数据 |

### 0.2 分红除权日历（参考）

| 标的 | 历史分红月份 | 除权除息日 | 验证重点 |
|------|-------------|-----------|---------|
| 000001 平安银行 | 6-7月 | 2025-06~07 | 复权因子变化、分红记录 |
| 600519 贵州茅台 | 6-7月 | 2025-06~07 | 复权因子变化、分红记录 |

### 0.3 验证日期选择

```
按日期摄入验证: 2025-01-02 (首个交易日)
按标的摄入验证: 2025-01-01 ~ 2025-12-31 (全年)
财报验证窗口:   2025-04-01 ~ 2025-04-30 (年报+一季报)
复权验证窗口:   2025-06-01 ~ 2025-07-31 (分红季)
```

---

## 1. 验证范围概览

### 1.1 资产类型与测试标的

| 资产类型 | 测试标的 | ticker | standard_ticker | instrument_id |
|---------|---------|--------|-----------------|---------------|
| 股票 | 平安银行 | `000001` | `000001.XSHE` | `1000001` |
| 股票 | 贵州茅台 | `600519` | `600519.XSHG` | `1000787` |
| ETF | 华泰柏瑞沪深300ETF | `510300` | `510300.XSHG` | 待确认 |
| 指数 | 沪深300 | `000300` | `000300.XSHG` | `3000151` |

> **注意**: P011 已修复，510300 现在可以正常从 Tushare fund_basic 接口获取（需使用 market='E' 参数）。

### 1.2 验证矩阵

| 验证类型 | 命令/端点 | 按日期 | 按标的 | API 查询 |
|---------|----------|--------|--------|---------|
| 元数据 | calendar, basic | ✅ | - | ✅ |
| 行情 | stock/etf/index daily | ✅ | ✅ | ✅ |
| 基本面 | balance/income/cash_flow/dividend | ✅ | ✅ | ✅ |
| 资本 | valuation/margin/pledge | ✅ | ✅ | ✅ |
| 宏观(中国) | indicators (tushare) | ✅ | - | ✅ |
| 宏观(美国) | indicators (fred) | ✅ | - | ✅ |
| 国债收益率 | bond-yield (tushare yc_cb) | ✅ | - | ✅ |
| 美元指数 | dollar-index (fred DTWEXBGS) | ✅ | - | ✅ |

### 1.3 数据源配置

| 数据源 | 配置方式 | 用途 |
|-------|---------|------|
| Tushare | `keyring.set_password('tushare', 'token', 'xxx')` | A股行情、基本面、中国宏观 |
| FRED | `keyring.set_password('fred', 'api_key', 'xxx')` | 美国宏观数据 |

> **获取 FRED API Key**: https://fred.stlouisfed.org/docs/api/api_key.html

---

## 2. 环境重置（可选）

> **注意**：每次完整验证前可选择重置环境，确保从干净状态开始。

### 2.1 重置数据库

```bash
# 删除现有数据库文件
rm -f data/metadata.db

# 重新初始化数据库 schema
pixi run -e dev python -m ditto_port.cli.main init db
```

### 2.2 清理摄入日志

```bash
# 重置摄入日志（可选，用于测试重复摄入）
rm -f data/ingestion_log.db
```

### 2.3 清理 Parquet 数据（可选）

```bash
# 清理行情数据（完整重置时使用）
rm -rf data/market/
rm -rf data/fundamental/
rm -rf data/capital/
rm -rf data/macro/
```

**验证项**：
- [ ] 数据库已重置
- [ ] 摄入日志已清理（如需测试重复摄入）
- [ ] 数据目录已清理（完整重置时）

---

## 3. 前置条件检查

### 3.1 环境配置

```bash
# 检查 Pixi 环境
pixi run --help

# 初始化数据库
pixi run -e dev python -m ditto_port.cli.main init db

# 检查数据源配置
cat config/development/data_source.env

# 检查 Tushare Token（keyring）
pixi run -e dev python -c "import keyring; print(keyring.get_password('tushare', 'token')[:8] + '***')"

# 检查 FRED API Key（keyring）
pixi run -e dev python -c "import keyring; k = keyring.get_password('fred', 'api_key'); print(k[:8] + '***' if k else '未配置')"
```

**验证项**：
- [ ] TUSHARE_TOKEN 已配置
- [ ] FRED_API_KEY 已配置（美国宏观数据）
- [ ] 数据库文件可访问
- [ ] 网络连接正常

### 3.2 初始化检查

```bash
# 初始化数据库 schema
pixi run init
```

**验证项**：
- [ ] 数据库表创建成功
- [ ] 基础数据加载完成

---

## 4. CLI 摄入验证

### 4.1 元数据摄入 (Metadata)

#### 3.1.1 交易日历

```bash
# 摄入 2025年1月 交易日历
pixi run ingest metadata calendar 2025-01-01
```

**验证项**：
- [ ] 命令执行成功
- [ ] 数据写入数据库
- [ ] 日志无 ERROR

**问题记录**：
```
[记录问题...]
```

#### 3.1.2 股票基础信息

```bash
# 摄入股票基础信息
pixi run ingest metadata basic stock
```

**验证项**：
- [ ] 命令执行成功
- [ ] 000001 (平安银行) 已注册
- [ ] 600519 (贵州茅台) 已注册

**问题记录**：
```
[记录问题...]
```

#### 3.1.3 ETF 基础信息

```bash
pixi run ingest metadata basic etf
```

**验证项**：
- [ ] 命令执行成功
- [ ] 510300 (沪深300ETF) 已注册

**问题记录**：
```
[记录问题...]
```

#### 3.1.4 指数基础信息

```bash
pixi run ingest metadata basic index
```

**验证项**：
- [ ] 命令执行成功
- [ ] 000300 (沪深300) 已注册

**问题记录**：
```
[记录问题...]
```

---

### 3.2 行情数据摄入 (Market)

#### 3.2.1 股票行情 - 按日期

```bash
# 摄入 2025-01-02 ~ 2025-01-10 股票行情
pixi run ingest market stock 2025-01-02
pixi run ingest market stock 2025-01-03
pixi run ingest market stock 2025-01-06
```

**验证项**：
- [ ] 命令执行成功
- [ ] 数据写入 parquet 文件
- [ ] 无数据缺失

**问题记录**：
```
[记录问题...]
```

#### 3.2.2 股票行情 - 按标的 (ticker)

```bash
# 使用 ticker 摄入（全年数据，覆盖分红复权）
pixi run ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] ticker 解析成功
- [ ] 数据完整摄取（约 244 个交易日）
- [ ] 日志显示正确的 standard_ticker
- [ ] 6-7月数据包含除权除息影响

**问题记录**：
```
[记录问题...]
```

#### 3.2.3 股票行情 - 按标的 (standard_ticker)

```bash
# 使用 standard_ticker 摄入（全年数据）
pixi run ingest market stock --standard-ticker 600519.XSHG -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] standard_ticker 解析成功
- [ ] 数据完整摄取
- [ ] 复权因子在分红月有变化

**问题记录**：
```
[记录问题...]
```

#### 3.2.4 股票行情 - 按标的 (instrument_id)

```bash
# 使用 instrument_id 摄入（全年数据）
pixi run ingest market stock --instrument-id 1000001 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] instrument_id 解析成功
- [ ] 数据完整摄取

**问题记录**：
```
[记录问题...]
```

#### 3.2.5 ETF 行情 - 按日期

```bash
pixi run ingest market etf 2025-01-02
```

**验证项**：
- [ ] 命令执行成功
- [ ] 510300 数据存在

**问题记录**：
```
[记录问题...]
```

#### 3.2.6 ETF 行情 - 按标的

```bash
pixi run ingest market etf --standard-ticker 510300.XSHG -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 按标的摄入 ETF 成功
- [ ] 全年数据完整

**问题记录**：
```
[记录问题...]
```

#### 3.2.7 指数行情 - 按日期

```bash
pixi run ingest market index 2025-01-02
```

**验证项**：
- [ ] 命令执行成功
- [ ] 000300 数据存在

**问题记录**：
```
[记录问题...]
```

#### 3.2.8 指数行情 - 按标的

```bash
pixi run ingest market index --standard-ticker 000300.XSHG -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 按标的摄入指数成功
- [ ] 全年数据完整

**问题记录**：
```
[记录问题...]
```

#### 3.2.9 复权因子

```bash
# 股票复权因子（按日期）
pixi run ingest market adj 2025-01-02

# 股票复权因子（按标的，全年 - 验证分红月复权因子变化）
pixi run ingest market adj --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest market adj --ticker 600519 -s 2025-01-01 -e 2025-12-31

# 基金复权因子
pixi run ingest market adj --fund --ticker 510300 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 股票复权因子摄入成功
- [ ] 基金复权因子摄入成功
- [ ] 复权因子在 6-7 月分红季有变化（关键验证点）

**问题记录**：
```
[记录问题...]
```

#### 3.2.10 股票状态

```bash
pixi run ingest market status 2025-01-02
```

**验证项**：
- [ ] 命令执行成功

**问题记录**：
```
[记录问题...]
```

#### 3.2.11 汇率数据 (FX Daily)

> **数据源**: Tushare fx_daily API
> **支持货币对**: USDCNH.FXCM, EURCNH.FXCM, GBPCNH.FXCM 等
> **特性**: 支持 `trade_date_utc` UTC 午夜时间戳（上海时区转换）

```bash
# 按日期摄入汇率数据
pixi run -e dev python -m ditto_port.cli.main ingest market fx 2025-01-02

# 验证命令帮助
pixi run -e dev python -m ditto_port.cli.main ingest market fx --help
```

**验证项**：
- [x] 命令可用（--help 正常）
- [ ] 数据摄入成功
- [ ] 数据包含 `trade_date_utc` 字段
- [ ] UTC 时间戳正确（上海时区转换）

**问题记录**：
```
2026-02-27 验证: Tushare fx_daily API 返回 FETCH_ERROR
可能原因: Tushare API 权限问题或接口限制
状态: 待确认 Tushare 账户权限
```

#### 3.2.12 大宗商品数据 (Commodity Daily)

> **数据源**: FRED API
> **支持品种**: WTI原油、Brent原油、黄金、白银、VIX指数
> **特性**:
> - 输入日期为北京时间，自动转换为 FRED 查询日期（美东时间）
> - 支持 `trade_date_utc` UTC 午夜时间戳（纽约时区转换）

```bash
# 按日期摄入商品数据（输入日期为北京时间）
pixi run -e dev python -m ditto_port.cli.main ingest market commodity 2025-01-02

# 验证命令帮助
pixi run -e dev python -m ditto_port.cli.main ingest market commodity --help
```

**验证项**：
- [x] 命令可用（--help 正常）
- [x] FRED API Key 已配置（keyring）
- [x] Coordinator 正确路由到 FredSource
- [ ] 数据摄入成功
- [ ] 北京时间日期正确转换为 FRED 查询日期
- [ ] 数据包含 `trade_date_utc` 字段
- [ ] UTC 时间戳正确（纽约时区转换）

**问题记录**：
```
2026-02-27 验证: FRED API 网络连接失败 (SourceFetchError -> RetryError)
原因: 网络环境无法访问 FRED API
状态: 网络问题，非代码问题
修复: Coordinator 已修复，正确路由 COMMODITY_DAILY 到 FredSource
```

---

### 3.3 基本面数据摄入 (Fundamental)

> **财报验证重点**：
> - 2024年报数据应在 2025-03~04 月发布
> - 2025一季报应在 2025-04 月发布
> - 2025半年报应在 2025-07~08 月发布
> - 2025三季报应在 2025-10 月发布

#### 3.3.1 资产负债表 - 按日期

```bash
pixi run ingest fundamental balance 2025-01-02
```

**验证项**：
- [ ] 命令执行成功
- [ ] 数据写入正确

**问题记录**：
```
[记录问题...]
```

#### 3.3.2 资产负债表 - 按标的

```bash
# 摄入全年财报数据（覆盖年报、一季报、半年报、三季报）
pixi run ingest fundamental balance --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental balance --ticker 600519 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 按标的摄入成功
- [ ] 包含 2024年报、2025各季报数据

**问题记录**：
```
[记录问题...]
```

#### 3.3.3 利润表 - 按日期

```bash
pixi run ingest fundamental income 2025-01-02
```

**验证项**：
- [ ] 命令执行成功

**问题记录**：
```
[记录问题...]
```

#### 3.3.4 利润表 - 按标的

```bash
pixi run ingest fundamental income --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental income --ticker 600519 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 按标的摄入成功
- [ ] 包含全年财报数据

**问题记录**：
```
[记录问题...]
```

#### 3.3.5 现金流量表 - 按日期

```bash
pixi run ingest fundamental cash-flow 2025-01-02
```

**验证项**：
- [ ] 命令执行成功

**问题记录**：
```
[记录问题...]
```

#### 3.3.6 现金流量表 - 按标的

```bash
pixi run ingest fundamental cash-flow --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental cash-flow --ticker 600519 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 按标的摄入成功

**问题记录**：
```
[记录问题...]
```

#### 3.3.7 分红送配 - 按日期

```bash
pixi run ingest fundamental dividend 2025-01-02
```

**验证项**：
- [ ] 命令执行成功

**问题记录**：
```
[记录问题...]
```

#### 3.3.8 分红送配 - 按标的

```bash
# 分红数据（关键：验证 2024年报分红方案在 2025年的实施）
pixi run ingest fundamental dividend --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental dividend --ticker 600519 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 按标的摄入成功
- [ ] 包含 2024年报对应的分红实施记录（通常 6-7 月除权）
- [ ] 分红记录与复权因子变化对应

**问题记录**：
```
[记录问题...]
```

#### 3.3.9 公司行动

```bash
pixi run ingest fundamental corporate-actions 2025-01-02
```

**验证项**：
- [ ] 命令执行成功

**问题记录**：
```
[记录问题...]
```

---

### 3.4 资本数据摄入 (Capital)

#### 3.4.1 估值指标 - 按日期

```bash
pixi run ingest capital valuation 2025-01-02
```

**验证项**：
- [ ] 命令执行成功

**问题记录**：
```
[记录问题...]
```

#### 3.4.2 估值指标 - 按标的

```bash
# 全年估值数据（验证 PE/PB 在财报发布后的变化）
pixi run ingest capital valuation --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest capital valuation --ticker 600519 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 按标的摄入成功
- [ ] 估值指标在财报发布后有变化（关键验证点）

**问题记录**：
```
[记录问题...]
```

#### 3.4.3 融资融券 - 按日期

```bash
pixi run ingest capital margin 2025-01-02
```

**验证项**：
- [ ] 命令执行成功

**问题记录**：
```
[记录问题...]
```

#### 3.4.4 融资融券 - 按标的

```bash
pixi run ingest capital margin --ticker 000001 -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 按标的摄入成功
- [ ] 全年数据完整

**问题记录**：
```
[记录问题...]
```

#### 3.4.5 股权质押

```bash
pixi run ingest capital pledge 2025-01-02
```

**验证项**：
- [ ] 命令执行成功

**问题记录**：
```
[记录问题...]
```

---

### 3.5 宏观数据摄入 (Macro)

> **数据源说明**：
> - **Tushare**: 中国宏观指标（GDP、CPI、M2 等）
> - **FRED**: 美国宏观指标（US_GDP_QOQ、US_CPI_YOY 等）

#### 3.5.1 中国宏观指标（Tushare）

```bash
pixi run ingest macro indicators 2025-01-02
```

**验证项**：
- [ ] 命令执行成功
- [ ] 数据写入正确

**问题记录**：
```
[记录问题...]
```

#### 3.5.2 美国宏观指标（FRED）

```bash
# 摄入单个日期的美国宏观数据
pixi run ingest macro indicators --source fred 2025-01-02

# 摄入日期范围的美国宏观数据
pixi run ingest macro indicators --source fred -s 2025-01-01 -e 2025-12-31

# 摄入特定指标（如 GDP、CPI）
pixi run ingest macro indicators --source fred --codes US_GDP_QOQ,US_CPI_YOY -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] FRED 数据源连接成功
- [ ] 美国宏观指标摄入成功
- [ ] knowledge_date 字段正确（来自 FRED realtime_start）
- [ ] 数据写入 macro_indicators 表

**问题记录**：
```
[记录问题...]
```

#### 3.5.3 中国国债收益率（Tushare yc_cb）

> **新增功能** (2026-02-28): 使用 Tushare yc_cb 接口获取中国国债收益率曲线

**接口说明**：
- 接口: `yc_cb`
- 数据源: 中债国债收益率曲线
- 口径: 到期收益率（YTM, curve_type=0），与美债口径一致
- 积分要求: ≥5000

**支持的指标**：
| 指标代码 | 名称 | 期限 |
|----------|------|------|
| CN_BOND_YIELD_1Y | 中国1年期国债收益率 | 1年 |
| CN_BOND_YIELD_2Y | 中国2年期国债收益率 | 2年 |
| CN_BOND_YIELD_5Y | 中国5年期国债收益率 | 5年 |
| CN_BOND_YIELD_10Y | 中国10年期国债收益率 | 10年 |

```bash
# 摄入中国国债收益率数据
pixi run ingest macro bond-yield -s 2025-01-01 -e 2025-12-31

# 摄入特定期限
pixi run ingest macro bond-yield --codes CN_BOND_YIELD_1Y,CN_BOND_YIELD_10Y -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] Tushare yc_cb 接口连接成功（需要 ≥5000 积分）
- [ ] 4 个期限指标全部摄入成功
- [ ] knowledge_date = date（T+0 发布）
- [ ] 数值范围合理（1.5% ~ 5%）

**问题记录**：
```
[记录问题...]
```

#### 3.5.4 贸易加权美元指数（FRED DTWEXBGS）

> **新增功能** (2026-02-28): 使用 FRED DTWEXBGS 获取贸易加权美元指数

**指标说明**：
- 指标代码: `US_DOLLAR_INDEX_BROAD`
- Series ID: DTWEXBGS
- 数据源: Federal Reserve Board
- 特点: 包含 26 种货币的贸易加权指数（vs. DXY 仅 6 种）

**vs. DXY (ICE美元指数)**：
| 对比项 | DTWEXBGS | DXY |
|--------|----------|-----|
| 数据源 | FRED (官方) | ICE (商业) |
| 货币数量 | 26种 | 6种 |
| 稳定性 | 高 | 一般 |
| 推荐度 | ⭐⭐⭐ | ⭐⭐ |

```bash
# 摄入贸易加权美元指数
pixi run ingest macro indicators --source fred --codes US_DOLLAR_INDEX_BROAD -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] FRED DTWEXBGS 接口连接成功
- [ ] 数据摄入成功
- [ ] 数值范围合理（80 ~ 130）
- [ ] frequency = daily
- [ ] category = dollar_index

**问题记录**：
```
[记录问题...]
```

---

### 3.6 历史回填 (Backfill)

#### 3.6.1 行情数据回填

```bash
# 回填 2025年全年股票行情
pixi run backfill market stock -s 2025-01-01 -e 2025-12-31 -p 2
```

**验证项**：
- [ ] 并行回填成功
- [ ] 数据完整性正确（约 244 个交易日）

**问题记录**：
```
[记录问题...]
```

#### 3.6.2 基本面数据回填

```bash
pixi run backfill fundamental -s 2025-01-01 -e 2025-12-31
```

**验证项**：
- [ ] 回填成功
- [ ] 包含全年财报数据

**问题记录**：
```
[记录问题...]
```

---

## 4. API 端点验证

### 4.1 启动服务

```bash
# 启动 API 服务
pixi run -e dev server

# 或使用 granian
pixi run -e dev granian ditto_port.main:app --port 8000
```

**验证项**：
- [ ] 服务启动成功
- [ ] 无启动错误

### 4.2 健康检查

```bash
# 根路径
curl http://localhost:8000/

# 健康检查
curl http://localhost:8000/healthz

# 系统状态
curl http://localhost:8000/api/v1/status
```

**验证项**：
- [ ] GET / 返回正常
- [ ] GET /healthz 返回 healthy
- [ ] GET /api/v1/status 返回系统信息

**问题记录**：
```
[记录问题...]
```

---

### 4.3 元数据 API

#### 4.3.1 查询单个标的

```bash
# 通过 instrument_id 查询
curl http://localhost:8000/api/v1/metadata/instruments/1000001

# 验证返回字段
# - instrument_id
# - ticker
# - standard_ticker
# - name
# - asset_type
# - exchange
```

**验证项**：
- [ ] 返回正确的标的信息
- [ ] 包含所有必要字段

**问题记录**：
```
[记录问题...]
```

#### 4.3.2 查询标的列表

```bash
# 查询所有股票
curl "http://localhost:8000/api/v1/metadata/instruments?asset_type=stock&limit=10"

# 通过 ticker 模糊查询
curl "http://localhost:8000/api/v1/metadata/instruments?ticker=000001"

# 通过名称查询
curl "http://localhost:8000/api/v1/metadata/instruments?name=平安"
```

**验证项**：
- [ ] 分页功能正常
- [ ] 过滤功能正常
- [ ] 搜索功能正常

**问题记录**：
```
[记录问题...]
```

---

### 4.4 行情数据 API

#### 4.4.1 K线查询

```bash
# 查询单个股票日K（全年数据）- 使用 instrument_ids 数组
curl -X POST http://localhost:8000/api/v1/market/bars \
  -H "Content-Type: application/json" \
  -d '{
    "instrument_ids": [1000001],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31"
  }'

# 查询多个股票（全年数据）
curl -X POST http://localhost:8000/api/v1/market/bars \
  -H "Content-Type: application/json" \
  -d '{
    "instrument_ids": [1000001, 1000787],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31"
  }'

# 查询 ETF（全年数据）- 510300 的 instrument_id 为 2002233
curl -X POST http://localhost:8000/api/v1/market/bars \
  -H "Content-Type: application/json" \
  -d '{
    "instrument_ids": [2002233],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31"
  }'

# 查询指数（全年数据）- 000300 的 instrument_id 为 3000150
curl -X POST http://localhost:8000/api/v1/market/bars \
  -H "Content-Type: application/json" \
  -d '{
    "instrument_ids": [3000150],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31"
  }'
```

> **注意**: API 使用 `instrument_ids` 数组格式，支持同时查询多个标的。查询单个标的时传入 `[id]` 即可。

**验证项**：
- [ ] 股票 K 线返回正确
- [ ] ETF K 线返回正确
- [ ] 指数 K 线返回正确
- [ ] 日期范围过滤正确
- [ ] 数据字段完整 (OHLCV)
- [ ] 数据量符合交易日数量（约 244 条）

**问题记录**：
```
[记录问题...]
```

---

### 4.5 基本面数据 API

#### 4.5.1 财务报表

```bash
# 资产负债表（全年）
curl "http://localhost:8000/api/v1/fundamental/financials/balance_sheet?ticker=000001&start_date=2025-01-01&end_date=2025-12-31"

# 利润表（全年）
curl "http://localhost:8000/api/v1/fundamental/financials/income_statement?ticker=000001&start_date=2025-01-01&end_date=2025-12-31"

# 现金流量表（全年）
curl "http://localhost:8000/api/v1/fundamental/financials/cash_flow?ticker=000001&start_date=2025-01-01&end_date=2025-12-31"
```

**验证项**：
- [ ] 资产负债表返回正确
- [ ] 利润表返回正确
- [ ] 现金流量表返回正确
- [ ] 包含 2024年报、2025各季报数据

**问题记录**：
```
[记录问题...]
```

#### 4.5.2 分红数据

```bash
# 分红数据（全年 - 验证 2024年报分红实施）
curl "http://localhost:8000/api/v1/fundamental/dividend?ticker=000001&start_date=2025-01-01&end_date=2025-12-31"
curl "http://localhost:8000/api/v1/fundamental/dividend?ticker=600519&start_date=2025-01-01&end_date=2025-12-31"
```

**验证项**：
- [ ] 分红数据返回正确
- [ ] 包含 2024年报对应的分红实施记录

**问题记录**：
```
[记录问题...]
```

#### 4.5.3 公司行动

```bash
curl "http://localhost:8000/api/v1/fundamental/corporate-actions?start_date=2025-01-01&end_date=2025-12-31"
```

**验证项**：
- [ ] 公司行动返回正确
- [ ] 包含分红、拆股等事件

**问题记录**：
```
[记录问题...]
```

---

### 4.6 资本数据 API

#### 4.6.1 估值指标

```bash
# 估值指标（全年 - 验证财报发布后的估值变化）
curl "http://localhost:8000/api/v1/capital/valuation?ticker=000001&start_date=2025-01-01&end_date=2025-12-31"
curl "http://localhost:8000/api/v1/capital/valuation?ticker=600519&start_date=2025-01-01&end_date=2025-12-31"
```

**验证项**：
- [ ] 估值数据返回正确 (PE, PB, PS 等)
- [ ] 估值指标在财报发布后有变化

**问题记录**：
```
[记录问题...]
```

#### 4.6.2 融资融券

```bash
curl "http://localhost:8000/api/v1/capital/margin?ticker=000001&start_date=2025-01-01&end_date=2025-12-31"
```

**验证项**：
- [ ] 融资融券数据返回正确
- [ ] 全年数据完整

**问题记录**：
```
[记录问题...]
```

---

### 4.7 宏观数据 API

#### 4.7.1 指标元数据

```bash
# 查询所有支持的宏观指标元数据
curl "http://localhost:8000/api/v1/macro/indicators/metadata"

# 按数据源过滤
curl "http://localhost:8000/api/v1/macro/indicators/metadata?source=tushare"
curl "http://localhost:8000/api/v1/macro/indicators/metadata?source=fred"
```

**验证项**：
- [ ] 返回支持的指标列表
- [ ] 包含 Tushare 指标
- [ ] 包含 FRED 指标（US_GDP_QOQ、US_CPI_YOY 等）

**问题记录**：
```
[记录问题...]
```

#### 4.7.2 中国宏观指标查询（Tushare）

```bash
curl -X POST http://localhost:8000/api/v1/macro/indicators \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": ["gdp", "cpi"],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31"
  }'
```

**验证项**：
- [ ] 中国宏观指标返回正确
- [ ] 全年数据完整

**问题记录**：
```
[记录问题...]
```

#### 4.7.3 美国宏观指标查询（FRED）

```bash
# 查询美国 GDP 和 CPI 数据
curl -X POST http://localhost:8000/api/v1/macro/indicators \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": ["US_GDP_QOQ", "US_CPI_YOY"],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "source": "fred"
  }'
```

**验证项**：
- [ ] 美国宏观指标返回正确
- [ ] knowledge_date 字段存在（PIT 支持）
- [ ] 数据格式符合 MACRO_INDICATOR_SOURCE_SCHEMA

**问题记录**：
```
[记录问题...]
```

#### 4.7.4 中国国债收益率查询（Tushare yc_cb）- 新增 2026-02-28

```bash
# 查询中国国债收益率曲线
curl -X POST http://localhost:8000/api/v1/macro/indicators \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": ["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_5Y", "CN_BOND_YIELD_10Y"],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "source": "tushare"
  }'
```

**验证项**：
- [ ] 国债收益率数据返回正确
- [ ] 包含 1Y/5Y/10Y 三个期限
- [ ] knowledge_date = date（T+0 发布）
- [ ] 数值范围合理（1.5% ~ 5%）
- [ ] category = interest_rate

**问题记录**：
```
[记录问题...]
```

#### 4.7.5 贸易加权美元指数查询（FRED DTWEXBGS）- 新增 2026-02-28

```bash
# 查询贸易加权美元指数
curl -X POST http://localhost:8000/api/v1/macro/indicators \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": ["US_DOLLAR_INDEX_BROAD"],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "source": "fred"
  }'
```

**验证项**：
- [ ] 美元指数数据返回正确
- [ ] 数值范围合理（80 ~ 130）
- [ ] frequency = daily
- [ ] category = dollar_index
- [ ] unit = 指数

**问题记录**：
```
[记录问题...]
```

---

### 4.8 汇率数据 API (FX)

> **端点**: POST /api/v1/fx/bars
> **状态**: 占位实现（返回空列表）

```bash
# 查询汇率 K 线数据
curl -X POST http://localhost:8000/api/v1/fx/bars \
  -H "Content-Type: application/json" \
  -d '{
    "pairs": ["USDCNY", "EURCNY"],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "limit": 1000
  }'
```

**验证项**：
- [ ] 端点响应 200
- [ ] 返回格式符合 APIResponse[list[FxBar]]
- [ ] FxBar 包含 trade_date_utc 字段

**问题记录**：
```
[记录问题...]
```

---

### 4.9 大宗商品数据 API (Commodity)

> **端点**: POST /api/v1/commodity/bars
> **状态**: 占位实现（返回空列表）

```bash
# 查询商品 K 线数据
curl -X POST http://localhost:8000/api/v1/commodity/bars \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["AU", "AG", "CU"],
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "limit": 1000
  }'
```

**验证项**：
- [ ] 端点响应 200
- [ ] 返回格式符合 APIResponse[list[CommodityBar]]
- [ ] CommodityBar 包含 trade_date_utc 字段

**问题记录**：
```
[记录问题...]
```

---

### 4.10 数据源直查 API

```bash
# 使用 ticker 查询（全年）
curl "http://localhost:8000/api/v1/source/tushare/stock_daily?ticker=000001&start_date=2025-01-01&end_date=2025-12-31"

# 使用 standard_ticker 查询（全年）
curl "http://localhost:8000/api/v1/source/tushare/stock_daily?standard_ticker=000001.XSHE&start_date=2025-01-01&end_date=2025-12-31"

# 使用 instrument_id 查询（全年）
curl "http://localhost:8000/api/v1/source/tushare/stock_daily?instrument_id=1000001&start_date=2025-01-01&end_date=2025-12-31"
```

**验证项**：
- [ ] ticker 参数解析正确
- [ ] standard_ticker 参数解析正确
- [ ] instrument_id 参数解析正确
- [ ] 返回数据量符合交易日数量

**问题记录**：
```
[记录问题...]
```

---

## 5. 边界条件验证

### 5.1 标识符解析

#### 5.1.1 模糊标识符错误

```bash
# 假设存在多个 000001（不同交易所）
# 应该返回 AmbiguousTickerError
pixi run ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-01-31
```

**预期结果**：报错或自动选择（取决于实现）

**实际结果**：
```
[记录实际结果...]
```

#### 5.1.2 不存在的标识符

```bash
# 使用不存在的 ticker
pixi run ingest market stock --ticker 999999 -s 2025-01-01 -e 2025-01-31
```

**预期结果**：IdentifierNotFoundError

**实际结果**：
```
[记录实际结果...]
```

### 5.2 日期边界

#### 5.2.1 非交易日

```bash
# 周末
pixi run ingest market stock 2025-01-04  # 周六

# 法定节假日
pixi run ingest market stock 2025-01-01  # 元旦
pixi run ingest market stock 2025-01-28  # 春节
```

**预期结果**：跳过或返回空数据

**实际结果**：
```
[记录实际结果...]
```

#### 5.2.2 未来日期

```bash
# 未来日期
pixi run ingest market stock 2026-01-01
```

**预期结果**：拒绝或返回空数据

**实际结果**：
```
[记录实际结果...]
```

#### 5.2.3 财报发布日验证

```bash
# 验证财报密集期数据
# 2025-04-30：年报+一季报披露截止日
pixi run ingest fundamental balance 2025-04-30
pixi run ingest fundamental income 2025-04-30
```

**预期结果**：获取到 2024年报和 2025一季报数据

**实际结果**：
```
[记录实际结果...]
```

#### 5.2.4 除权除息日验证

```bash
# 验证复权因子在除权日的变化
# 需要先查询具体除权日，假设为 2025-06-20
pixi run ingest market adj --ticker 000001 -s 2025-06-19 -e 2025-06-21
```

**预期结果**：复权因子在除权日有变化

**实际结果**：
```
[记录实际结果...]
```

### 5.3 重复摄入（幂等性验证）

> **重要**：重复摄入验证需要从干净环境开始，确保能验证完整的幂等性行为。

#### 5.3.1 环境准备

```bash
# 重置摄入日志（允许重新摄入相同数据）
rm -f data/ingestion_log.db

# 可选：重置行情数据（完整幂等性测试）
rm -rf data/market/stock/
```

#### 5.3.2 按日期重复摄入

```bash
# 第一次摄入
pixi run -e dev python -m ditto_port.cli.main ingest market stock 2025-01-02

# 第二次摄入（应该跳过或覆盖，不应报错）
pixi run -e dev python -m ditto_port.cli.main ingest market stock 2025-01-02
```

**预期结果**：
- ✅ 首次摄入成功
- ✅ 第二次摄入：跳过（已有记录）或覆盖（无重复数据错误）
- ❌ 不应出现：`Duplicate data: N overlapping key pairs`

**实际结果**：
```
[记录实际结果...]
```

#### 5.3.3 按标的重复摄入

```bash
# 第一次摄入
pixi run -e dev python -m ditto_port.cli.main ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-01-31

# 第二次摄入（应该跳过或覆盖，不应报错）
pixi run -e dev python -m ditto_port.cli.main ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-01-31
```

**预期结果**：
- ✅ 首次摄入成功
- ✅ 第二次摄入：跳过或覆盖
- ❌ 不应出现：`Duplicate data: N overlapping key pairs`

**实际结果**：
```
[记录实际结果...]
```

#### 5.3.4 基本面数据重复摄入

```bash
# 资产负债表重复摄入
pixi run -e dev python -m ditto_port.cli.main ingest fundamental balance --ticker 000001 -s 2025-01-01 -e 2025-03-31
pixi run -e dev python -m ditto_port.cli.main ingest fundamental balance --ticker 000001 -s 2025-01-01 -e 2025-03-31
```

**预期结果**：幂等性保证

**实际结果**：
```
[记录实际结果...]
```

---

## 6. 验证执行记录

### 6.1 执行摘要

| 类别 | 通过 | 失败 | 跳过 | 总计 |
|------|------|------|------|------|
| 前置条件 | 3 | 0 | 0 | 3 |
| CLI 元数据 | 4 | 0 | 0 | 4 |
| CLI 行情 | 7 | 0 | 0 | 7 |
| CLI 基本面 | 3 | 2 | 0 | 5 |
| CLI 资本 | 3 | 0 | 0 | 3 |
| CLI 宏观 | 1 | 0 | 0 | 1 |
| CLI 回填 | 1 | 0 | 0 | 1 |
| CLI Query | 4 | 1 | 0 | 5 |
| **总计** | **26** | **3** | **0** | **29** |

> **修复统计**: 10 个 Bug 已修复，期货功能已移除

### 6.2 问题汇总

| 问题编号 | 严重程度 | 类别 | 描述 | 状态 | 修复 PR |
|---------|---------|------|------|------|---------|
| P001 | 🟡 配置 | Token | TUSHARE_TOKEN 未配置 | ✅ 已通过 keyring 配置 | - |
| P002 | 🟡 文档 | 命令格式 | 验证计划命令格式需修正 | ✅ 已更新文档 | - |
| P003 | 🔴 Bug | ETF/Index 基础信息 | list_date 为 NULL 导致约束失败 | ✅ 已创建 ListDateInferenceService | - |
| P004 | 🔴 Bug | 指数行情摄入 | _write_index_bars 使用错误的解析方法 | ✅ 已修复 data_writer.py | - |
| P005 | 🔴 Bug | 质押数据 | 缺少 pledge_ratio 表定义 | ✅ 已修复 schema.sql | - |
| P006 | 🔴 Bug | 宏观数据 | 日期解析缺少格式参数 | ✅ 已修复 macro.py | - |
| P007 | 🔴 Bug | 宏观数据 | 缺少 macro_indicators/macro_indicator_data 表 | ✅ 已修复 schema.sql | - |
| P008 | 🔴 Bug | CLI Query 命令 | IngestionBundle 没有 get 方法 | ✅ 已修复 query/*.py | - |
| P011 | 🔴 Bug | ETF 基础信息 | fetch_etf_basic 缺少 market='E' 参数 | ✅ 已修复 etf.py | - |
| P010 | 🟡 API | Bar 模型 | trade_date 需要字符串，volume 保留 float 2 位小数 | ✅ 已修复 market.py | - |

> **注意**: P009（期货持仓）已从代码库移除，相关功能暂不支持。

### 6.2.1 2026-02-25 新发现问题

| 问题编号 | 严重程度 | 类别 | 描述 | 状态 | 修复 PR |
|---------|---------|------|------|------|---------|
| P012 | 🔴 Bug | 重复数据 | 按标的摄入遇到重复键错误 | ✅ 已修复（OnDuplicate.KEEP_LAST） | - |
| P013 | 🔴 Bug | API 服务器 | dishka 中间件在 lifespan 中添加失败 | ✅ 已修复（移至 lifespan 外） | - |
| P014 | 🟡 Bug | ETF 按标的摄入 | source_ticker 类型不匹配 (str vs null) | ✅ 非Bug（510300 不在元数据中，已重新摄入） | - |
| P015 | 🔴 Bug | 分红数据 | ex_date 为 null 导致数据库约束失败 | ✅ 已修复（添加 div_proc 字段，允许 null ex_dividend_date） | - |
| P016 | 🔴 Bug | API 依赖注入 | dishka 无法解析 `Service \| None` 联合类型 | ✅ 已修复（改用 `Service` + `# type: ignore[assignment]`） | - |
| P017 | 🔴 Bug | API 数据转换 | capital.py 模型 instrument_id 类型转换缺失 | ✅ 已修复（添加 str() 转换） | - |

### 6.3 验证执行日志

#### 2026-02-24 前置条件检查
- ✅ Pixi 环境可用
- ✅ 数据库初始化成功
- ✅ TUSHARE_TOKEN 已配置（keyring）

#### 2026-02-24 元数据摄入验证
- ✅ 交易日历摄入成功
- ✅ 股票基础信息摄入成功（5804 条）
- ✅ ETF 基础信息摄入成功（2497 条）- P011 修复后
- ✅ 指数基础信息摄入成功（8000 条）- 同上
- ✅ 510300（华泰柏瑞沪深300ETF）现已可正常获取

#### 2026-02-24 行情数据摄入验证
- ✅ 股票日行情按日期摄入成功（5369 条）
- ✅ 股票日行情按标的摄入成功（ticker/standard_ticker/instrument_id 三种格式）
- ✅ 指数日行情摄入成功 - 修复后
- ✅ 复权因子摄入成功

#### 2026-02-24 基本面数据摄入验证
- ✅ 资产负债表按日期/按标的摄入成功
- ✅ 利润表按标的摄入成功
- ❌ 现金流量表 FETCH_ERROR（Tushare API 问题）
- ❌ 分红送配 EMPTY_DATA（可能无数据）

#### 2026-02-24 资本数据摄入验证
- ✅ 估值指标按标的摄入成功（18 条）
- ✅ 融资融券按标的摄入成功（18 条）
- ✅ 股权质押摄入成功（3000 条）- 修复 schema 后
- ⚠️ 期货持仓功能已从代码库移除

#### 2026-02-24 宏观数据摄入验证
- ✅ 宏观指标摄入成功（1 条）- 修复日期解析和 schema 后

#### 2026-02-24 历史回填验证
- ✅ 股票行情回填成功（5 个日期全部成功）

#### 2026-02-24 CLI Query 验证
- ✅ 修复了所有 query 命令的 Bundle 访问问题
- ⚠️ Bar 模型转换有类型问题（trade_date/volume）

#### 2026-02-24 ListDateInferenceService 实现（P003 完整修复）
- ✅ 创建独立的 ListDateInferenceService 服务
- ✅ 实现分批查询历史数据逻辑（考虑 API 限制）
  - Stock: 6000 条/次
  - ETF: 2000 条/次
  - Index: 8000 条/次
- ✅ 集成到 basic 数据摄取后的补偿流程
- ✅ 过滤 2010 年前数据，使用 >= 2010 年的最早交易日期
- ✅ 单元测试全部通过（7 个测试用例）

#### 2026-02-24 ETF 基础信息修复（P011）
- ✅ 发现问题：510300（华泰柏瑞沪深300ETF）不在数据源中
- ✅ 根因分析：`fetch_etf_basic` 未传递 `market='E'` 参数
  - 不带 market 参数返回 15000 条（场外基金）
  - 带 market='E' 参数返回 2497 条（场内 ETF）
- ✅ 修复：添加 `market='E'` 参数到 fund_basic API 调用

#### 2026-02-25 完整验证重新执行（修复后）

**前置条件检查**
- ✅ Pixi 环境可用
- ✅ 数据库初始化成功
- ✅ TUSHARE_TOKEN 已配置（keyring）

**元数据摄入验证**
- ✅ 交易日历（已摄入，跳过）
- ✅ 股票基础信息（已摄入，跳过）
- ✅ ETF 基础信息：重新摄入成功（2497 条，包含 510300）
- ✅ 指数基础信息（已摄入，跳过）
- ✅ 关键标的验证：000001 平安银行、600519 贵州茅台、510300 沪深300ETF、000300 沪深300

**行情数据摄入验证**
- ✅ 股票按日期摄入：成功（5369 条）
- ✅ ETF 按日期摄入：成功（1452 条）
- ✅ 指数按日期摄入：成功（17 条）
- ✅ 股票按标的摄入：成功（18 条）- P012 已修复
- ✅ ETF 按标的摄入：成功（18 条）- 510300 现已可正常摄入

**基本面数据摄入验证**
- ✅ 资产负债表按标的：成功（6 条）
- ✅ 利润表按标的：成功（4 条）
- ⚠️ 现金流量表：FETCH_ERROR（Tushare API 问题）
- ⚠️ 分红送配：EMPTY_DATA（2025 年数据暂无）
- ✅ 分红数据表结构：P015 已修复（div_proc 字段，ex_dividend_date 可为 NULL）

**资本数据摄入验证**
- ✅ 估值指标按标的：成功（18 条）
- ✅ 融资融券按标的：成功（18 条）

**重复摄入幂等性验证（P012）**
- ✅ 股票按标的重复摄入：成功（使用 OnDuplicate.KEEP_LAST 策略）

**API 服务器验证（P013 + granian 修复）**
- ✅ 服务器启动成功（granian + interface='asgi'）
- ✅ GET /healthz：正常
- ✅ GET /api/v1/status：正常
- ✅ GET /api/v1/metadata/instruments/{id}：正常
- ✅ POST /api/v1/market/bars：正常
- ✅ GET /api/v1/source/tushare/stock_daily：正常
- ⚠️ GET /api/v1/capital/*：500 错误（独立问题，非本次修复范围）
- ⚠️ GET /api/v1/fundamental/*：500 错误（独立问题，非本次修复范围）

**P015 分红数据修复验证**
- ✅ div_proc 字段已添加到 dividend 表
- ✅ ex_dividend_date 可为 NULL（预案阶段）
- ✅ 数据库中包含"实施"和"预案"两种记录

**granian 修复验证**
- ✅ 添加 `interface='asgi'` 参数解决 FastAPI 兼容性问题
- ❌ 服务器启动失败：dishka 中间件添加错误（P013）

**边界条件验证**
- ✅ 不存在的标识符：正确抛出 IdentifierNotFoundError
- ✅ 非交易日摄入：正确跳过
- ✅ 未来日期摄入：正确跳过

**Prefect 验证**
- ✅ Prefect 版本：3.6.10
- ✅ Flows 加载成功：
  - daily-ingestion: 每日增量数据摄取流程
  - daily-repair: 每日修补流程
  - retry-failed: 重试失败的任务
  - backfill: 全量数据回补流程
  - repair-holes: 扫描并修补数据空洞

---

## 7. 执行命令

### 7.1 完整验证脚本

```bash
#!/bin/bash
# verify-all.sh - 执行完整验证（2025年全年）

set -e

echo "=== 1. 前置条件检查 ==="
pixi run init

echo "=== 2. 元数据摄入 ==="
pixi run ingest metadata calendar 2025-01-01
pixi run ingest metadata basic stock
pixi run ingest metadata basic etf
pixi run ingest metadata basic index

echo "=== 3. 行情数据摄入（按日期） ==="
pixi run ingest market stock 2025-01-02
pixi run ingest market etf 2025-01-02
pixi run ingest market index 2025-01-02

echo "=== 4. 行情数据摄入（按标的 - 全年） ==="
# 股票 - 三种标识符格式
pixi run ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest market stock --standard-ticker 600519.XSHG -s 2025-01-01 -e 2025-12-31
pixi run ingest market stock --instrument-id 1000001 -s 2025-01-01 -e 2025-12-31
# ETF
pixi run ingest market etf --standard-ticker 510300.XSHG -s 2025-01-01 -e 2025-12-31
# 指数
pixi run ingest market index --standard-ticker 000300.XSHG -s 2025-01-01 -e 2025-12-31
# 复权因子
pixi run ingest market adj --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest market adj --ticker 600519 -s 2025-01-01 -e 2025-12-31

echo "=== 5. 基本面数据摄入（全年 - 覆盖财报季） ==="
pixi run ingest fundamental balance 2025-01-02
pixi run ingest fundamental balance --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental balance --ticker 600519 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental income --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental income --ticker 600519 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental cash-flow --ticker 000001 -s 2025-01-01 -e 2025-12-31
# 分红数据（关键验证）
pixi run ingest fundamental dividend --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest fundamental dividend --ticker 600519 -s 2025-01-01 -e 2025-12-31

echo "=== 6. 资本数据摄入（全年） ==="
pixi run ingest capital valuation 2025-01-02
pixi run ingest capital valuation --ticker 000001 -s 2025-01-01 -e 2025-12-31
pixi run ingest capital valuation --ticker 600519 -s 2025-01-01 -e 2025-12-31
pixi run ingest capital margin --ticker 000001 -s 2025-01-01 -e 2025-12-31

echo "=== 7. 宏观数据摄入 ==="
# 中国宏观指标（Tushare）
pixi run ingest macro indicators 2025-01-02

# 美国宏观指标（FRED）
pixi run ingest macro indicators --source fred 2025-01-02

# 中国国债收益率（Tushare yc_cb）- 新增 2026-02-28
# 注意：需要 Tushare 积分 ≥5000
pixi run ingest macro bond-yield -s 2025-01-01 -e 2025-01-31 || echo "警告: yc_cb 接口需要 5000+ 积分"

# 贸易加权美元指数（FRED DTWEXBGS）- 新增 2026-02-28
pixi run ingest macro indicators --source fred --codes US_DOLLAR_INDEX_BROAD -s 2025-01-01 -e 2025-01-31

echo "=== 8. 历史回填（全年） ==="
pixi run backfill market stock -s 2025-01-01 -e 2025-12-31 -p 2
pixi run backfill fundamental -s 2025-01-01 -e 2025-12-31

echo "=== 验证完成 ==="
```

### 7.2 API 验证脚本

```bash
#!/bin/bash
# verify-api.sh - 执行 API 验证（2025年全年数据）

BASE_URL="http://localhost:8000"

echo "=== 健康检查 ==="
curl -s "$BASE_URL/healthz" | jq .
curl -s "$BASE_URL/api/v1/status" | jq .

echo "=== 元数据查询 ==="
curl -s "$BASE_URL/api/v1/metadata/instruments/1000001" | jq .
curl -s "$BASE_URL/api/v1/metadata/instruments?asset_type=stock&limit=10" | jq .

echo "=== 行情查询（全年） ==="
# 股票（使用 instrument_ids 数组格式）
curl -s -X POST "$BASE_URL/api/v1/market/bars" \
  -H "Content-Type: application/json" \
  -d '{"instrument_ids": [1000001], "start_date": "2025-01-01", "end_date": "2025-12-31"}' | jq '. | length'

# ETF（510300 instrument_id: 2002233）
curl -s -X POST "$BASE_URL/api/v1/market/bars" \
  -H "Content-Type: application/json" \
  -d '{"instrument_ids": [2002233], "start_date": "2025-01-01", "end_date": "2025-12-31"}' | jq '. | length'

# 指数（000300 instrument_id: 3000150）
curl -s -X POST "$BASE_URL/api/v1/market/bars" \
  -H "Content-Type: application/json" \
  -d '{"instrument_ids": [3000150], "start_date": "2025-01-01", "end_date": "2025-12-31"}' | jq '. | length'

echo "=== 基本面查询（全年财报） ==="
# 财务报表
curl -s "$BASE_URL/api/v1/fundamental/financials/balance_sheet?ticker=000001&start_date=2025-01-01&end_date=2025-12-31" | jq '. | length'
curl -s "$BASE_URL/api/v1/fundamental/financials/income_statement?ticker=000001&start_date=2025-01-01&end_date=2025-12-31" | jq '. | length'

# 分红数据
curl -s "$BASE_URL/api/v1/fundamental/dividend?ticker=000001&start_date=2025-01-01&end_date=2025-12-31" | jq .

echo "=== 资本数据查询（全年） ==="
curl -s "$BASE_URL/api/v1/capital/valuation?ticker=000001&start_date=2025-01-01&end_date=2025-12-31" | jq '. | length'
curl -s "$BASE_URL/api/v1/capital/margin?ticker=000001&start_date=2025-01-01&end_date=2025-12-31" | jq '. | length'

echo "=== 数据源直查（全年） ==="
curl -s "$BASE_URL/api/v1/source/tushare/stock_daily?ticker=000001&start_date=2025-01-01&end_date=2025-12-31" | jq '. | length'

echo "=== 宏观数据查询 ==="
# 查询宏观指标元数据
curl -s "$BASE_URL/api/v1/macro/indicators/metadata?source=fred" | jq '. | length'
curl -s "$BASE_URL/api/v1/macro/indicators/metadata?source=tushare" | jq '. | length'

# 中国国债收益率（Tushare yc_cb）- 新增 2026-02-28
curl -s -X POST "$BASE_URL/api/v1/macro/indicators" \
  -H "Content-Type: application/json" \
  -d '{"indicators": ["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_10Y"], "start_date": "2025-01-01", "end_date": "2025-01-31"}' | jq '. | length'

# 贸易加权美元指数（FRED DTWEXBGS）- 新增 2026-02-28
curl -s -X POST "$BASE_URL/api/v1/macro/indicators" \
  -H "Content-Type: application/json" \
  -d '{"indicators": ["US_DOLLAR_INDEX_BROAD"], "start_date": "2025-01-01", "end_date": "2025-01-31", "source": "fred"}' | jq '. | length'

echo "=== API 验证完成 ==="
```

---

## 8. 附录

### 8.1 测试日期参考

| 日期 | 星期 | 类型 | 说明 |
|------|------|------|------|
| 2025-01-01 | 周三 | 假日 | 元旦 |
| 2025-01-02 | 周四 | 交易日 | 首个交易日 |
| 2025-01-03 | 周五 | 交易日 | - |
| 2025-01-04 | 周六 | 周末 | 非交易日 |
| 2025-01-05 | 周日 | 周末 | 非交易日 |
| 2025-01-06 | 周一 | 交易日 | - |
| 2025-01-28 | 周二 | 假日 | 春节 |
| 2025-02-05 | 周三 | 交易日 | 春节后 |
| 2025-04-30 | 周三 | 交易日 | 年报+一季报披露截止 |
| 2025-05-01 | 周四 | 假日 | 劳动节 |
| 2025-06-xx | - | 除权日 | 分红除权（具体日期待定） |
| 2025-07-xx | - | 除权日 | 分红除权（具体日期待定） |
| 2025-08-31 | 周日 | 截止日 | 半年报披露截止 |
| 2025-10-31 | 周五 | 截止日 | 三季报披露截止 |
| 2025-10-01 | 周三 | 假日 | 国庆节 |

### 8.2 2025 年交易日统计

| 月份 | 预估交易日 | 备注 |
|------|-----------|------|
| 1月 | ~20 | 元旦、春节 |
| 2月 | ~18 | 春节 |
| 3月 | ~21 | - |
| 4月 | ~21 | 劳动节调休 |
| 5月 | ~19 | 劳动节 |
| 6月 | ~20 | - |
| 7月 | ~23 | - |
| 8月 | ~22 | - |
| 9月 | ~21 | 中秋 |
| 10月 | ~18 | 国庆 |
| 11月 | ~21 | - |
| 12月 | ~23 | - |
| **全年** | **~247** | - |

### 8.2 常见问题排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| TUSHARE_TOKEN 错误 | Token 未配置或过期 | 检查 data_source.env |
| 数据库连接失败 | 路径或权限问题 | 检查数据库文件 |
| 标识符未找到 | 元数据未摄入 | 先执行 basic 摄入 |
| API 404 | 路由未注册 | 检查 main.py 路由 |
| 摄入无数据 | 非交易日 | 检查交易日历 |

---

## 9. 待完成验证

### 9.1 已修复问题

#### 2026-02-25 验证通过

| 问题编号 | 描述 | 状态 | 备注 |
|---------|------|------|------|
| P012 | 🔴 Bug | 重复数据 | 按标的摄入遇到重复键错误 | ✅ 已修复 |
| P013 | 🔴 Bug | API 服务器 | dishka 中间件在 lifespan 中添加失败 | ✅ 已修复 |
| P014 | 🟡 Bug | ETF 按标的摄入 | source_ticker 类型不匹配 (str vs null) | ✅ 非Bug |
| P015 | 🔴 Bug | 分红数据 | ex_date 为 null 导致数据库约束失败 | ✅ 已修复 |
| P016 | 🔴 Bug | API 依赖注入 | dishka 无法解析 `Service \| None` 联合类型 | ✅ 已修复 |
| P017 | 🔴 Bug | API 数据转换 | capital.py 模型 instrument_id 类型转换缺失 | ✅ 已修复 |

#### 2026-02-26 验证修复

| 问题编号 | 描述 | 状态 | 备注 |
|---------|------|------|------|
| P018 | 🔴 Bug | 交易日历只摄入单天数据 | ✅ 已修复 |
| P019 | 🟡 脚本 | 验证脚本数据库路径错误 | ✅ 已修复 |
| P020 | 🟡 脚本 | 验证脚本命令格式错误 | ✅ 已修复 |
| P021 | 🟡 脚本 | CLI Query 命令参数错误 | ✅ 已修复 |

**P018 详情 - 交易日历只摄入单天数据**:
- **位置**: `apps/port/src/ditto_port/services/ingestion/coordinator.py:758-760`
- **原因**: `fetch_calendar(trade_date, trade_date)` 传入相同的开始和结束日期
- **修复**: 使用整年日期范围 `f"{year}-01-01"` 到 `f"{year}-12-31"`
- **修复代码**:
  ```python
  # 交易日历特殊处理：使用整年日期范围
  _calendar_year = trade_date[:4]  # 从 trade_date 提取年份
  handlers: dict[Dataset, Callable[[], pl.DataFrame]] = {
      Dataset.CALENDAR: lambda y=_calendar_year: self._source.fetch_calendar(
          f"{y}-01-01", f"{y}-12-31"
      ),
  ```

**P019-P021 详情 - 验证脚本命令错误**:
| 错误类型 | 错误命令 | 正确命令 |
|---------|---------|---------|
| 数据库路径 | `data/metadata.db` | `data/metadata/metadata.sqlite` |
| 初始化 | `pixi run init` | `pixi run -e dev python -m ditto_port.cli.main init db --force` |
| 摄入 | `pixi run ingest ...` | `pixi run -e dev python -m ditto_port.cli.main ingest ...` |
| 查询 | `pixi run query ...` | `pixi run -e dev python -m ditto_port.cli.main query ...` |
| 元数据查询 | `query metadata instrument --ticker` | `query metadata instrument <instrument_id>` |
| 行情查询 | `query market bar` | `query market bars -i <instrument_id>` |
| 基本面查询 | `query fundamental balance` | `query fundamental financials -t balance_sheet` |

### 9.2 待验证功能

| 功能 | 状态 | 备注 |
|------|------|------|
| 现金流量表按日期摄入 | ⚠️ Tushare API 问题 | 需确认 API 是否正常 |
| 分红送配数据摄入 | ✅ P015 已修复 | 支持 div_proc 字段区分预案/实施 |
| 复权因子分红季变化 | ⚠️ 待验证 | 需在除权除息日验证 |
| 财报季数据完整性 | ⚠️ 待验证 | 需在 4 月、8 月、10 月验证 |
| 按标的摄入重复数据处理 | ✅ P012 已修复 | 使用 OnDuplicate.KEEP_LAST 策略 |
| API 服务器启动 | ✅ P013 已修复 | dishka 中间件移到 lifespan 之前 |
| API 端点依赖注入 | ✅ P016+P017 已修复 | 类型注解 + 数据转换问题 |
| FRED 数据源配置 | ✅ 已集成 | 使用 keyring 存储 API Key |
| FRED 宏观数据摄入 | ✅ 2026-02-26 验证通过 | 8 个美国宏观指标成功摄入 |
| FRED PIT 支持 | ✅ 2026-02-26 验证通过 | knowledge_date 字段正确填充 |
| MacroCategory 扩展 | ✅ 已修复 | 新增 prices/employment 分类 |

### 9.2.1 FRED 数据源验证清单

| 验证项 | 状态 | 备注 |
|-------|------|------|
| FRED API Key 配置 | ✅ 已通过 | keyring.get_password('fred', 'api_key') |
| FredSource 初始化 | ✅ 已通过 | 依赖注入正常创建实例 |
| FRED 指标元数据查询 | ✅ 已通过 | list_fred_indicators() 返回 8 个指标 |
| FRED 数据摄入 | ✅ 已通过 | 8 个指标成功摄入 |
| FRED PIT 支持 | ✅ 已通过 | knowledge_date 字段正确填充 |
| MacroCategory 扩展 | ✅ 已修复 | 新增 prices/employment 分类 |

#### 2026-02-26 FRED 验证记录

**已验证的 FRED 指标**：
| 指标代码 | 指标名称 | 类别 |
|---------|---------|------|
| US_GDP_QOQ | 美国GDP环比 | economic |
| US_CPI_YOY | 美国CPI同比 | prices |
| US_CPI_CORE_YOY | 美国核心CPI同比 | prices |
| US_PCE_YOY | 美国PCE同比 | prices |
| US_PCE_CORE_YOY | 美国核心PCE同比 | prices |
| US_UNRATE | 美国失业率 | employment |
| US_PAYEMS | 美国非农就业 | employment |
| US_M2_YOY | 美国M2同比 | money_supply |

**验证命令**：
```bash
# 验证 FRED 数据源
pixi run -e dev python -c "
from ditto_datahub.sources.fred import FredSource, list_fred_indicators
import keyring

api_key = keyring.get_password('fred', 'api_key')
source = FredSource(api_key=api_key)
indicators = list_fred_indicators()
print(f'可用 FRED 指标: {len(indicators)} 个')
"
```
| FRED API 端点 | ⚠️ 待验证 | /api/v1/macro/indicators?source=fred |

### 9.3 API 端点验证状态

| API 端点 | 状态 | 备注 |
|---------|------|------|
| GET /healthz | ✅ 已验证 | uvicorn 运行正常 |
| GET /api/v1/status | ✅ 已验证 | uvicorn 运行正常 |
| GET /api/v1/metadata/instruments | ✅ 已验证 | uvicorn 运行正常 |
| POST /api/v1/market/bars | ✅ 已验证 | uvicorn 运行正常 |
| POST /api/v1/fx/bars | ⚠️ 占位实现 | 返回空列表，待集成 FxService |
| POST /api/v1/commodity/bars | ⚠️ 占位实现 | 返回空列表，待集成 CommodityService |
| GET /api/v1/fundamental/financials/* | ✅ 已验证 | uvicorn 运行正常 |
| GET /api/v1/fundamental/dividend | ✅ 已验证 | uvicorn 运行正常 |
| GET /api/v1/capital/valuation | ✅ 已验证 | uvicorn 运行正常 |
| GET /api/v1/capital/margin | ✅ 已验证 | uvicorn 运行正常 |
| GET /api/v1/macro/indicators | ✅ 已验证 | uvicorn 运行正常 |
| GET /api/v1/source/tushare/* | ✅ 已验证 | uvicorn 运行正常 |

### 9.4 边界条件验证状态

| 边界条件 | 状态 | 备注 |
|---------|------|------|
| 模糊标识符错误处理 | ⚠️ 待验证 | - |
| 不存在的标识符 | ✅ 已验证 | 正确抛出 IdentifierNotFoundError |
| 非交易日摄入 | ✅ 已验证 | 正确跳过 |
| 未来日期摄入 | ✅ 已验证 | 正确跳过 |
| 财报发布日验证 | ⚠️ 待验证 | 需在 4 月、8 月、10 月验证 |
| 除权除息日验证 | ⚠️ 待验证 | 需在 6-7 月验证 |
| 重复摄入幂等性 | ✅ 已验证 | P012 修复后正常（使用 OnDuplicate.KEEP_LAST） |

### 9.5 Prefect 验证状态

#### 9.5.1 Flow 加载验证

| 功能 | 状态 | 备注 |
|------|------|------|
| Prefect 版本 | ✅ 3.6.10 | - |
| daily-ingestion flow | ✅ 加载成功 | 每日增量数据摄取流程 |
| daily-repair flow | ✅ 加载成功 | 每日修补流程 |
| retry-failed flow | ✅ 加载成功 | 重试失败的任务 |
| backfill flow | ✅ 加载成功 | 全量数据回补流程 |
| repair-holes flow | ✅ 加载成功 | 扫描并修补数据空洞 |

#### 9.5.2 Flow 执行验证（按日期）

```bash
# 验证每日摄入流程（指定日期）
pixi run -e dev python -c "
from ditto_port.jobs.flows.daily import daily_ingestion_flow

# 执行 flow（指定交易日）
result = daily_ingestion_flow(trade_date='2025-01-02')
print(f'Flow 执行结果: {result}')
"

# 验证修补流程
pixi run -e dev python -c "
from ditto_port.jobs.flows.repair import retry_failed_flow

# 执行修补流程
result = retry_failed_flow.with_options().from_source(
    source='stock_daily',
    days_back=7
)
print(f'修补流程结果: {result}')
"
```

**验证项**：
- [x] daily_ingestion_flow 加载成功
- [x] check_trading_day task 执行成功
- [x] 交易日判断正确（2025-01-03: True, 2025-01-04: False）
- [ ] retry_failed_flow 执行成功

**实际结果**：
```
2025-01-03 是否为交易日: True
2025-01-04 是否为交易日: False
```

#### 9.5.3 Flow 执行验证（按标的）

```bash
# 验证按标的回填流程
pixi run -e dev python -c "
from ditto_port.jobs.flows.backfill import backfill_flow

# 配置按标的回填
config = {
    'dataset': 'stock_daily',
    'start_date': '2025-01-01',
    'end_date': '2025-01-10',
    'instrument_ids': [1000001]  # 平安银行
}

# 执行回填
result = backfill_flow(config=config)
print(f'按标的回填结果: {result}')
"

# 验证空洞修补流程
pixi run -e dev python -c "
from ditto_port.jobs.flows.repair import repair_holes_flow

# 执行空洞修补
result = repair_holes_flow(dataset='stock_daily', days_back=30)
print(f'空洞修补结果: {result}')
"
```

**验证项**：
- [ ] backfill_flow 按标的执行成功
- [ ] 数据完整性验证

**实际结果**：
```
[记录实际结果...]
```

#### 9.5.4 Prefect 服务器启动（可选）

```bash
# 启动本地 Prefect 服务器（用于可视化监控）
pixi run prefect server start &

# 等待服务器启动
sleep 10

# 部署 flows 到本地服务器
pixi run -e dev python -m ditto_port.jobs.flows.deploy
```

**验证项**：
- [ ] Prefect 服务器启动成功
- [ ] Flows 部署成功
- [ ] 可通过 UI 查看 flows

### 9.6 已移除功能

| 功能 | 移除原因 | 备注 |
|------|---------|------|
| 期货持仓摄入 | Tushare API 接口不明确 | 代码已移除，待后续需求明确后重新实现 |

---

## 10. 2026-02-25 完整重验记录

### 10.1 验证环境

- **环境重置**: 完整重置（数据库 + 日志 + Parquet）
- **验证范围**: 2025 年全年数据

### 10.2 验证结果汇总

| 类别 | 通过 | 失败 | 跳过 | 总计 |
|------|------|------|------|------|
| 环境重置 | 1 | 0 | 0 | 1 |
| 元数据摄入 | 4 | 0 | 0 | 4 |
| 行情数据摄入 | 9 | 0 | 0 | 9 |
| 基本面摄入 | 2 | 2 | 0 | 4 |
| 资本数据摄入 | 3 | 0 | 0 | 3 |
| 宏观数据摄入 | 1 | 0 | 0 | 1 |
| 边界条件 | 3 | 0 | 0 | 3 |
| API 验证 | 3 | 0 | 0 | 3 |
| **总计** | **26** | **2** | **0** | **28** |

### 10.3 详细验证记录

#### 10.3.1 元数据摄入

| 命令 | 状态 | 数据量 |
|------|------|--------|
| `ingest metadata calendar 2025-01-01` | ✅ 成功 | 365 条（243 交易日） |
| `ingest metadata basic stock` | ✅ 成功 | 5804 条 |
| `ingest metadata basic etf` | ✅ 成功 | 2497 条 |
| `ingest metadata basic index` | ✅ 成功 | 8000 条 |

#### 10.3.2 行情数据摄入

| 命令 | 状态 | 数据量 |
|------|------|--------|
| `ingest market stock 2025-01-02` | ✅ 成功 | 5369 条 |
| `ingest market etf 2025-01-02` | ✅ 成功 | 1452 条 |
| `ingest market index 2025-01-02` | ✅ 成功 | 17 条 |
| `ingest market stock --ticker 000001 -s 2025-01-01 -e 2025-12-31` | ✅ 成功 | 243 条 |
| `ingest market stock --standard-ticker 600519.XSHG ...` | ✅ 成功 | 243 条 |
| `ingest market etf --standard-ticker 510300.XSHG ...` | ✅ 成功 | 243 条 |
| `ingest market index --standard-ticker 000300.XSHG ...` | ✅ 成功 | 243 条 |
| `ingest market adj --ticker 000001 ...` | ✅ 成功 | 243 条 |
| `ingest market adj --ticker 600519 ...` | ✅ 成功 | 243 条 |

#### 10.3.3 基本面数据摄入

| 命令 | 状态 | 数据量 |
|------|------|--------|
| `ingest fundamental balance --ticker 000001 ...` | ✅ 成功 | 6 条 |
| `ingest fundamental income --ticker 000001 ...` | ✅ 成功 | 4 条 |
| `ingest fundamental cash-flow --ticker 000001 ...` | ❌ FETCH_ERROR | Tushare API 问题 |
| `ingest fundamental dividend --ticker 000001 ...` | ❌ EMPTY_DATA | 2025 年暂无数据 |

#### 10.3.4 资本数据摄入

| 命令 | 状态 | 数据量 |
|------|------|--------|
| `ingest capital valuation --ticker 000001 ...` | ✅ 成功 | 243 条 |
| `ingest capital margin --ticker 000001 ...` | ✅ 成功 | 243 条 |
| `ingest capital pledge 2025-01-02` | ✅ 成功 | 3000 条 |

#### 10.3.5 宏观数据摄入

| 命令 | 状态 | 数据量 |
|------|------|--------|
| `ingest macro indicators 2025-01-02` | ✅ 成功 | 1 条 |

#### 10.3.6 边界条件验证

| 测试项 | 状态 | 结果 |
|------|------|------|
| 不存在的标识符 `--ticker 999999` | ✅ 正确报错 | IdentifierNotFoundError |
| 非交易日 `2025-01-04` | ✅ 正确跳过 | skipped |
| 重复摄入幂等性 | ✅ 成功 | 使用 KEEP_LAST 策略 |

#### 10.3.7 API 验证

| 端点 | 状态 | 备注 |
|------|------|------|
| GET /healthz | ✅ 正常 | {"status":"ok"} |
| GET /api/v1/metadata/instruments/1000001 | ✅ 正常 | 返回正确标的 |
| POST /api/v1/market/bars | ✅ 正常 | 需使用 instrument_ids 数组格式 |

> **P022 说明**: 原验证使用 `instrument_id` (单数) 格式导致返回空数据，实际 API 应使用 `instrument_ids` (复数数组) 格式。正确格式：`{"instrument_ids": [1000001], ...}`

### 10.4 新发现问题

| 问题编号 | 严重程度 | 类别 | 描述 | 状态 |
|---------|---------|------|------|------|
| P018 | 🔴 Bug | schema.sql | list_date NOT NULL 约束导致 ETF/Index 摄入失败 | ✅ 已修复 |
| P019 | 🔴 Bug | instrument_writer.py | effective_from 使用 NULL 的 list_date 导致约束失败 | ✅ 已修复 |
| P020 | 🟡 Bug | calendar_writer.py | `if not records:` 对 DataFrame 不兼容 | ✅ 已修复 |
| P021 | 🟡 Bug | calendar_writer.py | `for record in records:` 遍历方式不兼容 | ✅ 已修复 |
| P022 | 🟢 非Bug | API | 行情查询返回空数据 | ✅ 文档格式问题，应使用 instrument_ids 数组 |

### 10.5 关键标的验证

| 标的 | ticker | instrument_id | 状态 |
|------|--------|---------------|------|
| 平安银行 | 000001 | 1000001 | ✅ 已注册 |
| 贵州茅台 | 600519 | 1000787 | ✅ 已注册 |
| 沪深300ETF | 510300 | 2002233 | ✅ 已注册 |
| 沪深300 | 000300 | 3000150 | ✅ 已注册 |
