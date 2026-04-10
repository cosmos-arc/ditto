# 数据摄入能力覆盖与架构优化设计

> 创建日期: 2026-02-12
> 状态: Draft
> 作者: Claude

## 1. 背景与问题

### 1.1 当前状态

项目数据摄入能力存在以下问题：

1. **CLI 覆盖不完整**：仅覆盖 8/18 种数据集（44%）
2. **指数数据集缺失**：存储层已实现，但摄入层未补全
3. **DQ 检查引用无效数据集**：`index_daily` 在检查中被引用但未注册
4. **参数类型不统一**：`Dataset` 枚举与 `str` 混合使用

### 1.2 数据集注册表（当前 18 种）

| 层级 | 数据集 | 描述 | CLI | Prefect |
|------|--------|------|:---:|:-------:|
| T0 | calendar | 交易日历 | ✅ | ✅ |
| T0 | stock_basic | 股票基础信息 | ✅ | ✅ |
| T0 | etf_basic | ETF基础信息 | ✅ | ✅ |
| T1 | stock_daily | 股票日行情 | ✅ | ✅ |
| T1 | etf_daily | ETF日行情 | ✅ | ✅ |
| T1 | stock_status | 股票状态 | ❌ | ✅ |
| T1 | adj_factor | 复权因子 | ✅ | ✅ |
| T1 | fund_adj | 基金复权因子 | ✅ | ✅ |
| T1 | balance_sheet | 资产负债表 | ❌ | ✅ |
| T1 | income_statement | 利润表 | ❌ | ✅ |
| T1 | cash_flow | 现金流量表 | ❌ | ✅ |
| T1 | dividend | 分红送配 | ❌ | ✅ |
| T1 | valuation_metrics | 估值指标 | ❌ | ✅ |
| T1 | margin_trading | 融资融券 | ❌ | ✅ |
| T1 | pledge_ratio | 股权质押 | ❌ | ✅ |
| T1 | macro_indicators | 宏观指标 | ❌ | ✅ |
| T1 | futures | 期货数据 | ❌ | ✅ |
| T1 | corporate_actions | 公司行为 | ❌ | ✅ |

---

## 2. 问题分析

### 2.1 指数数据集缺失链路

```
存储层: IndexBarsReader/Writer ✅ → "market/index/bars"
    ↓
Dataset 枚举: INDEX_DAILY ❌ 缺失
    ↓
DATASET_REGISTRY: 未注册
    ↓
Source 协议: fetch_index_daily() ❌ 缺失
    ↓
CLI/Prefect: 无入口
```

### 2.2 DQ 检查 Bug

```python
# port/jobs/flows/daily.py:181-185
dqc_future = dq_batch_check.submit(
    trade_date=trade_date,
    datasets=["etf_daily", "index_daily", "stock_daily", "adj_factor"],
    #                       ^^^^^^^^^^ 无效！未在 Dataset 枚举中定义
)
```

### 2.3 参数类型不统一

| 层级 | 方法 | 当前类型 | 应改为 |
|------|------|----------|--------|
| Port | `IngestionCoordinator.ingest_date()` | `str` | `Dataset` |
| Port | `IngestionCoordinator._fetch_data()` | `str` | `Dataset` |
| DataHub | `MarketService.save_bars()` | `Literal[...]` | `Dataset` |

---

## 3. 架构设计

### 3.1 统一枚枚举使用原则

```
┌──────────────────────────────────────────────────────────────┐
│                    边界层 (Boundary)                          │
│  职责：str → Dataset 转换                                     │
│  - CLI (typer)                                               │
│  - HTTP API (FastAPI)                                        │
│  - Config 文件解析                                           │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼ 只传递 Dataset 枚举
┌──────────────────────────────────────────────────────────────┐
│                    核心层 (Core)                              │
│  职责：内部传递使用 Dataset 枚举                              │
│  - Service 方法签名                                          │
│  - Coordinator 方法签名                                      │
│  - DQ 检查方法签名                                           │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼ Dataset.value 或映射获取存储路径
┌──────────────────────────────────────────────────────────────┐
│                    存储层 (Storage)                           │
│  职责：物理路径存储                                           │
│  - Store 使用字符串路径                                      │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 语义区分

| 概念 | 命名 | 位置 | 示例值 |
|------|------|------|--------|
| 存储路径 | Store 内部 `DATASET` 属性 | DataHub | `"market/stock/bars"` |
| 数据集标识 | `Dataset` 枚举 | DataHub | `STOCK_DAILY = "stock_daily"` |
| 摄取任务配置 | `DATASET_REGISTRY` | Port | `DatasetSpec(...)` |

### 3.3 CLI 命令重组方案

```
ditto
├── init                    # 配置初始化
├── meta                    # T0 元数据
│   ├── calendar update
│   ├── stock-basic
│   └── etf-basic
├── market                  # T1 行情数据
│   ├── stock daily/backfill
│   ├── etf daily/backfill
│   ├── index daily/backfill/basic  🆕
│   ├── adj-factor daily/backfill   🔧 补充 backfill
│   └── fund-adj daily/backfill     🔧 补充 backfill
├── fundamental             # T1 基本面 🆕
│   ├── balance-sheet daily/backfill
│   ├── income-statement daily/backfill
│   ├── cash-flow daily/backfill
│   └── dividend daily/backfill
├── capital                 # T1 资本面 🆕
│   ├── valuation daily/backfill
│   ├── margin daily/backfill
│   └── pledge daily/backfill
├── macro                   # T1 宏观 🆕
│   └── indicators daily/backfill
├── futures                 # T1 期货 🆕
│   └── daily/backfill
└── corporate-actions       # T1 公司行为 🆕
    └── daily/backfill
```

---

## 4. 实施计划

### 4.1 Phase 1: 补全指数数据集 (P0)

| 序号 | 任务 | 文件 | 估计工作量 |
|------|------|------|-----------|
| 1.1 | Dataset 枚举添加 `INDEX_BASIC`, `INDEX_DAILY` | `datahub/models/common.py` | S |
| 1.2 | Source 协议添加 `fetch_index_basic/daily` | `port/services/ingestion/protocols.py` | S |
| 1.3 | Tushare Source 实现指数获取 | `datahub/sources/tushare/adapters/` | M |
| 1.4 | DATASET_REGISTRY 注册指数任务 | `port/models/config.py` | S |
| 1.5 | IngestionCoordinator 添加指数处理 | `port/services/ingestion/coordinator.py` | S |
| 1.6 | 添加存储路径映射 | `datahub/services/market_service.py` | S |
| 1.7 | 添加单元测试 | `tests/` | M |
| 1.8 | DQ 检查自动修复（index_daily 现在有效） | `port/jobs/tasks/dq_batch.py` | S |

### 4.2 Phase 2: 统一内部枚举使用 (P1)

| 序号 | 任务 | 文件 | 估计工作量 |
|------|------|------|-----------|
| 2.1 | `IngestionCoordinator` 方法签名改用 `Dataset` | `port/services/ingestion/coordinator.py` | M |
| 2.2 | `MarketService.save_bars()` 改用 `Dataset` | `datahub/services/market_service.py` | M |
| 2.3 | DQ 相关方法改用 `Dataset` | `core/quality/`, `port/services/ingestion/quality/` | M |
| 2.4 | 更新所有调用点 | 多文件 | M |

### 4.3 Phase 3: CLI 补全 (P2)

| 序号 | 任务 | 新增命令 | 估计工作量 |
|------|------|----------|-----------|
| 3.1 | 为 `adj` 添加 backfill 能力 | `ditto adj adj-factor backfill`, `ditto adj fund-adj backfill` | S |
| 3.2 | 添加 `index` 命令组 | `ditto index daily/backfill/basic` | S |
| 3.3 | 添加 `fundamental` 命令组 | `ditto fundamental balance/income/cashflow/dividend` | M |
| 3.4 | 添加 `capital` 命令组 | `ditto capital valuation/margin/pledge` | M |
| 3.5 | 添加 `macro` 命令组 | `ditto macro indicators` | S |
| 3.6 | 添加 `futures` 命令组 | `ditto futures daily/backfill` | S |
| 3.7 | 添加 `corporate-actions` 命令组 | `ditto corporate-actions daily/backfill` | S |

---

## 5. 代码示例

### 5.1 Dataset 枚举扩展

```python
# datahub/models/common.py
class Dataset(str, Enum):
    """数据集标识枚举 - 系统内部统一使用."""

    # T0: Meta datasets
    CALENDAR = "calendar"
    STOCK_BASIC = "stock_basic"
    ETF_BASIC = "etf_basic"
    INDEX_BASIC = "index_basic"  # 🆕

    # T1: Market datasets
    STOCK_DAILY = "stock_daily"
    ETF_DAILY = "etf_daily"
    INDEX_DAILY = "index_daily"  # 🆕
    STOCK_STATUS = "stock_status"
    ADJ_FACTOR = "adj_factor"
    FUND_ADJ = "fund_adj"

    # T1: Fundamental datasets
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW = "cash_flow"
    DIVIDEND = "dividend"

    # T1: Capital datasets
    VALUATION_METRICS = "valuation_metrics"
    MARGIN_TRADING = "margin_trading"
    PLEDGE_RATIO = "pledge_ratio"

    # T1: Macro/Futures/Corporate
    MACRO_INDICATORS = "macro_indicators"
    FUTURES = "futures"
    CORPORATE_ACTIONS = "corporate_actions"
```

### 5.2 摄入协调器改进

```python
# port/services/ingestion/coordinator.py
class IngestionCoordinator:
    def ingest_date(
        self,
        dataset: Dataset,  # ✅ 使用枚举
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        """摄取单个交易日数据."""
        # 检查是否应该跳过
        if skip_result := self._check_should_skip(dataset, trade_date, force):
            return skip_result

        # 检查交易日
        if not self._is_trading_day_for_dataset(dataset, trade_date):
            return self._create_skipped_result(dataset, trade_date, "非交易日")

        return self._fetch_and_ingest(dataset, trade_date, force)

    def _fetch_data(self, dataset: Dataset, trade_date: str) -> pl.DataFrame:
        """获取数据 - 使用枚举作为 key."""
        handlers: dict[Dataset, Callable[[], pl.DataFrame]] = {
            # ... 现有数据集
            Dataset.INDEX_BASIC: lambda: self._source.fetch_index_basic(),
            Dataset.INDEX_DAILY: lambda: self._source.fetch_index_daily(trade_date),
        }

        if dataset not in handlers:
            raise ValueError(f"不支持的数据集: {dataset}")

        return handlers[dataset]()
```

### 5.3 存储路径映射

```python
# datahub/services/market_service.py
class MarketService:
    # 数据集到存储路径的映射
    _BARS_DATASET_PATH_MAP: dict[Dataset, str] = {
        Dataset.STOCK_DAILY: "market/stock/bars",
        Dataset.ETF_DAILY: "market/etf/bars",
        Dataset.INDEX_DAILY: "market/index/bars",
    }

    def save_bars(
        self,
        dataset: Dataset,  # ✅ 使用枚举
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """保存K线数据."""
        if dataset not in self._BARS_DATASET_PATH_MAP:
            raise ValueError(f"Unsupported dataset: {dataset}")

        # 选择对应的 writer
        writers = {
            Dataset.STOCK_DAILY: self._stock_bars_writer,
            Dataset.ETF_DAILY: self._etf_bars_writer,
            Dataset.INDEX_DAILY: self._index_bars_writer,
        }

        writer = writers[dataset]
        # ...
```

### 5.4 CLI 边界转换

```python
# port/cli/commands/index.py
from ditto_data.models import Dataset

app = typer.Typer(help="指数数据摄取命令")

_daily_impl = create_daily_command(Dataset.INDEX_DAILY.value, "摄取指数日行情数据")
_backfill_impl = create_backfill_command(Dataset.INDEX_DAILY.value, "回补指数历史数据")
_basic_impl = create_basic_command(Dataset.INDEX_BASIC.value, "摄取指数基础信息")


@app.command()
def daily(
    ctx: typer.Context,
    date: str = typer.Argument(..., help="交易日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", "-f", help="强制重新摄取"),
) -> None:
    """摄取指数日行情数据."""
    return _daily_impl(ctx, date, force)
```

---

## 6. 验收标准

### 6.1 Phase 1 验收

- [ ] `Dataset.INDEX_BASIC` 和 `Dataset.INDEX_DAILY` 在枚举中定义
- [ ] `DATASET_REGISTRY` 包含 `index_basic` 和 `index_daily` 配置
- [ ] `IngestionCoordinator.ingest_date(Dataset.INDEX_DAILY, ...)` 正常工作
- [ ] DQ 检查 `index_daily` 不再报错
- [ ] 单元测试覆盖指数摄入

### 6.2 Phase 2 验收

- [ ] 所有内部方法签名使用 `Dataset` 枚举
- [ ] 外部入口（CLI）接受字符串并转换为枚举
- [ ] 类型检查通过 (basedpyright strict)

### 6.3 Phase 3 验收

- [ ] 所有 18 种数据集都有 CLI 命令
- [ ] 所有 CLI 命令支持 `daily` 和 `backfill` 模式
- [ ] 命令结构按数据域组织

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 类型签名改动影响面大 | 中 | 分阶段实施，每阶段独立测试 |
| Tushare 指数数据结构不同 | 低 | 参考 ETF 实现适配 |
| CLI 命令过多 | 低 | 按域分组，保持层级清晰 |

---

## 8. 参考

- [Dataset 枚举定义](../packages/data/src/ditto_data/models/common.py)
- [摄取任务注册表](../apps/port/src/ditto_port/models/config.py)
- [MarketService](../packages/data/src/ditto_data/services/market_service.py)
- [IngestionCoordinator](../apps/port/src/ditto_port/services/ingestion/coordinator.py)
