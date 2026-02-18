# 指数数据摄入架构设计

## 背景

当前指数数据摄入存在以下问题：
1. Adapter 层硬编码了 `COMMON_INDEX_CODES`（仅 8 个市场指数）
2. 不支持申万（SW）行业指数
3. 配置与获取逻辑耦合在 Adapter 层

## 设计目标

1. **关注点分离**：配置在编排层，获取在 Adapter 层
2. **完整覆盖**：支持市场指数 + SW L1/L2/L3 行业指数
3. **动态获取**：SW 指数代码从现有行业数据动态查询，避免硬编码
4. **选股支持**：L3 颗粒度支持后续选股策略

## 指数分类

### 固定配置（~17 个）

| 分类 | 数量 | 用途 | 示例 |
|------|------|------|------|
| 市场基准 | 8 | 大盘趋势判断、市场情绪 | 000001.SH, 000300.SH |
| 风格指数 | 9 | 大小盘/价值成长轮动 | 399373.SZ, 000992.SH |

### 动态获取（~411 个）

| 分类 | 数量 | 来源 | 用途 |
|------|------|------|------|
| SW L1 | 31 | 行业数据查询 | 大类轮动、资产配置 |
| SW L2 | ~134 | 行业数据查询 | 子行业轮动、产业链分析 |
| SW L3 | ~246 | 行业数据查询 | 选股映射、细分赛道择时 |

**总计**：~430 个指数

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      编排层 (Pipeline)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐     ┌──────────────────┐             │
│  │ IndexConfig      │     │ IndexRegistry    │             │
│  │ (固定配置)        │     │ (动态获取)        │             │
│  │                  │     │                  │             │
│  │ MARKET_INDEX = [ │     │ get_sw_codes(    │             │
│  │   "000001.SH",   │     │   level=1/2/3    │             │
│  │   ...            │     │ ) → from SW数据   │             │
│  │ ]                │     │                  │             │
│  └────────┬─────────┘     └────────┬─────────┘             │
│           │                        │                        │
│           └──────────┬─────────────┘                        │
│                      ▼                                      │
│              ┌──────────────┐                               │
│              │ get_all_codes│                               │
│              │ () → list    │                               │
│              └──────┬───────┘                               │
│                     │                                       │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                      Source 层                               │
├─────────────────────────────────────────────────────────────┤
│  TushareSource.fetch_index_daily(trade_date, ts_codes)      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                      Adapter 层                              │
├─────────────────────────────────────────────────────────────┤
│  IndexTushareAdapter.fetch_daily_by_codes(trade_date, codes)│
│  - 纯数据获取逻辑                                            │
│  - 不包含任何默认指数列表                                    │
└─────────────────────────────────────────────────────────────┘
```

## 配置定义

### 固定配置（编排层）

```python
# config/index_config.py

from typing import Final

# 市场基准指数
MARKET_INDEX_CODES: Final = [
    "000001.SH",  # 上证指数
    "399001.SZ",  # 深证成指
    "000300.SH",  # 沪深300
    "000852.SH",  # 中证1000
    "000016.SH",  # 上证50
    "399006.SZ",  # 创业板指
    "000688.SH",  # 科创50
    "399673.SZ",  # 创业板50
]

# 风格指数
STYLE_INDEX_CODES: Final = [
    "399373.SZ",  # 大盘价值
    "399374.SZ",  # 大盘成长
    "399375.SZ",  # 中盘价值
    "399376.SZ",  # 中盘成长
    "399377.SZ",  # 小盘价值
    "399378.SZ",  # 小盘成长
    "000992.SH",  # 全指价值
    "000993.SH",  # 全指成长
    "000991.SH",  # 全指红利
]
```

### 动态获取（从 SW 行业数据）

```python
# services/ingestion/index_config.py

from typing import Protocol, Literal

class SWIndustryProvider(Protocol):
    """申万行业数据提供者协议."""
    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame: ...

def get_sw_index_codes(source: SWIndustryProvider, level: Literal[1, 2] = 1) -> list[str]:
    """从 Tushare API 动态获取申万行业指数代码列表.

    Args:
        source: 数据源，需实现 fetch_sw_industry 方法.
        level: 行业级别 (1=一级行业, 2=二级行业).

    Returns:
        SW 行业指数代码列表（Tushare source_ticker 格式）.
    """
    df = source.fetch_sw_industry(level=level)
    if df.is_empty():
        return []
    return df["source_ticker"].unique().sort().to_list()

def get_all_index_codes(
    source: SWIndustryProvider,
    include_style: bool = True,
    include_sw_levels: list[Literal[1, 2]] | None = None,
) -> list[str]:
    """获取所有指数代码列表（包含动态获取的 SW 行业指数）."""
    codes = get_default_index_codes(include_style=include_style)

    if include_sw_levels:
        for level in include_sw_levels:
            sw_codes = get_sw_index_codes(source, level=level)
            codes.extend(sw_codes)

    return codes
```

## 黄金数据集配置

黄金数据集需要明确每个 ticker 的资产类别，便于：
- E2E 测试按类别验证
- 数据摄入按类别路由
- 报告按类别分组

### 命名规范

| 字段 | 格式 | 示例 | 用途 |
|------|------|------|------|
| `ticker` | 纯代码 | `600519` | 内部标识 |
| `exchange` | 内部交易所 | `XSHG` | 内部规范 |
| `standard_ticker` | ticker.exchange | `600519.XSHG` | 内部标准格式 |
| `source_ticker` | 转换后格式 | `600519.SH` | 数据源 API 调用 |

### 交易所映射

| 内部代码 | 说明 | Tushare 格式 |
|----------|------|-------------|
| `XSHG` | 上海证券交易所 | `SH` |
| `XSHE` | 深圳证券交易所 | `SZ` |
| `SW` | 申万指数 | `SI` |

### 资产类别定义

| asset_type | 说明 | 示例 | exchange |
|------------|------|------|----------|
| `stock` | A股股票 | 600519 | XSHG/XSHE |
| `etf` | ETF基金 | 510300 | XSHG/XSHE |
| `index_market` | 市场指数 | 000001 | XSHG/XSHE |
| `index_sw` | 申万行业指数 | 801010 | SW |
| `index_style` | 风格指数 | 399373 | XSHE |

### 配置格式

```yaml
tickers:
  # 股票
  - ticker: "600519"
    name: "贵州茅台"
    asset_type: "stock"
    exchange: "XSHG"
    tags: ["大盘", "白酒", "高流动性"]

  # ETF
  - ticker: "510300"
    name: "沪深300ETF"
    asset_type: "etf"
    exchange: "XSHG"
    tags: ["宽基", "高流动性"]

  # 市场指数
  - ticker: "000001"
    name: "上证指数"
    asset_type: "index_market"
    exchange: "XSHG"
    tags: ["市场基准"]

  # SW 行业指数
  - ticker: "801010"
    name: "申万农林牧渔"
    asset_type: "index_sw"
    exchange: "SW"
    tags: ["SW一级行业"]
```

## API 调用优化

全量 ~430 次调用/天，建议：

1. **并行请求**：使用 asyncio 并行获取
2. **增量更新**：非交易日跳过
3. **分批调度**：市场指数优先，SW 行业指数延后

## 实施计划

### Phase 1: 重构 Adapter 层
- [x] 移除 `COMMON_INDEX_CODES` 硬编码
- [x] 确保 `fetch_daily_by_codes` 接受外部传入的代码列表

### Phase 2: 创建编排层配置
- [x] 创建 `services/ingestion/index_config.py`（固定配置）
- [x] 实现 `get_default_index_codes()` 函数（市场指数 + 风格指数）
- [x] 实现 `get_sw_index_codes()` 函数（通过 Tushare API 动态获取）
- [x] 实现 `get_all_index_codes()` 函数（组合固定配置 + 动态获取）

### Phase 3: 更新数据源层
- [x] `DataSource` 基类添加 `fetch_sw_industry` 抽象方法
- [x] `TushareSource` 实现 `fetch_sw_industry` 方法
- [x] `IngestionDataSource` 协议添加 `fetch_sw_industry` 方法

### Phase 4: 更新协调器
- [x] `IngestionCoordinator` 使用 `get_all_index_codes()` 获取完整指数列表
- [x] 支持 SW L1/L2 行业指数动态获取

### Phase 5: 测试验证
- [x] 更新 `test_base_unit.py` 测试覆盖新的抽象方法
- [x] 运行单元测试验证 (1753 passed)
- [x] 运行类型检查验证 (0 errors)

## 参考资料

- Tushare 指数接口：https://tushare.pro/document/2?doc_id=95
- 申万行业分类：https://www.swsresearch.com/
