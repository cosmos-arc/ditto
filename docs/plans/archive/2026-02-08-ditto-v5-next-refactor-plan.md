# Ditto v5 下一阶段重构执行计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**目标**: 基于 v5 架构目标与 datahub-v2 已完成进度，完成下一阶段结构收口与功能闭环重构

**架构**: 先结构后功能，分阶段收敛（目录重组 → 模型子目录化 → 功能接入 → 运维闭环）

**Tech Stack**: polars, duckdb, fastapi, prefect, loguru, opentelemetry, cachebox, httpx, orjson

---

## 一、背景与现状

### 1.1 已完成（datahub-v2）

- ✅ `instrument_id/source_ticker` 语义统一，门禁 `ARCH500/ARCH510` 已落地
- ✅ 16 个数据集已接入 Port ingestion 主链路（market/metadata/fundamental/capital/macro）
- ✅ DataHub 域服务 `query()/write()` 契约统一（Market/Metadata/Fundamental/Capital/Macro）
- ✅ Port 架构边界门禁完成（非 registry 禁止依赖 Store/Source/Runtime）
- ✅ CI 门禁全绿：`2243 passed, 20 skipped`, coverage `92.63%`

### 1.2 待收口缺口（本计划范围）

| 类别 | 缺口项 | 复杂度 | 依赖 |
|------|--------|--------|------|
| **结构** | Core 目录为骨架，缺少 `engine/strategy/portfolio` 实现模块 | L | 无 |
| **结构** | Port API 未按 `routes/` 分层，路由集中在 `main.py` | M | 无 |
| **结构** | DataHub `models/` 未子目录化（`market/trading/portfolio/strategy`） | M | 无 |
| **结构** | `futures/corporate_actions` 在 DataHub 域服务存在实现，但未暴露到 Port 主链路 | M | 无 |
| **功能** | DQ 告警与 quarantine 落库仍是 TODO（仅日志告警） | L | 无 |
| **配置** | PIT 策略隐式固化，未显式化为可配置策略 | M | 无 |

---

## 二、分阶段执行计划

**阶段优先级（按用户确认）**：结构收口优先 → 功能闭环优先 → 运维闭环优先

---

### 阶段 1：Port API 分层重构

**目标**：将 `apps/port/src/ditto_port/main.py` 中集中路由按 v5 目录目标拆分到 `api/routes/`

#### 1.1 创建 `api/routes/` 目录结构

**Files**:
- `apps/port/src/ditto_port/api/routes/__init__.py`
- `apps/port/src/ditto_port/api/routes/market.py`
- `apps/port/src/ditto_port/api/routes/metadata.py`
- `apps/port/src/ditto_port/api/routes/ingestion.py`
- `apps/port/src/ditto_port/api/routes/portfolio.py`（占位，待 Core 实现）

**Step 1**: 创建 `api/routes/__init__.py`
```python
"""API routes package."""

from ditto_port.api.routes import ingestion, market, metadata, portfolio

__all__ = ["ingestion", "market", "metadata", "portfolio"]
```

**Step 2**: 提取 `main.py` 中 `market` 相关路由到 `routes/market.py`
```python
"""Market data API routes."""

from fastapi import APIRouter, Depends
from ditto_port.api.models import BarsQuery, BarResponse

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/bars", response_model=list[BarResponse])
async def get_bars(query: BarsQuery = Depends()) -> list[BarResponse]:
    # 实现逻辑从 main.py 移入
    ...
```

**Step 3**: 同理拆分 `metadata/ingestion/portfolio` 路由

**Step 4**: 更新 `main.py` 使用路由挂载
```python
from ditto_port.api.routes import market, metadata, ingestion, portfolio

app.include_router(market.router)
app.include_router(metadata.router)
app.include_router(ingestion.router)
app.include_router(portfolio.router)
```

**验收**：
- [ ] `main.py` 仅保留 `app` 创建与中间件配置
- [ ] 路由按功能域拆分到独立模块
- [ ] `pixi run -e dev test --unit` 通过

**Commit**: `refactor(port): split API routes into domain modules`

---

### 阶段 2：DataHub 模型子目录化

**目标**：将 `packages/datahub/src/ditto_datahub/models/` 按 v5 目标拆分 `market/trading/portfolio/strategy`

#### 2.1 创建子目录结构

**Files**:
- `packages/datahub/src/ditto_datahub/models/market/__init__.py`
- `packages/datahub/src/ditto_datahub/models/market/bar.py`
- `packages/datahub/src/ditto_datahub/models/market/quote.py`
- `packages/datahub/src/ditto_datahub/models/trading/__init__.py`
- `packages/datahub/src/ditto_datahub/models/trading/order.py`
- `packages/datahub/src/ditto_datahub/models/trading/position.py`
- `packages/datahub/src/ditto_datahub/models/portfolio/__init__.py`
- `packages/datahub/src/ditto_datahub/models/portfolio/portfolio.py`
- `packages/datahub/src/ditto_datahub/models/strategy/__init__.py`
- `packages/datahub/src/ditto_datahub/models/strategy/signal.py`

**Step 1**: 提取 `BAR_SCHEMA/QUOTE_SCHEMA` 到 `market/bar.py`
```python
"""Market data schemas."""

from polars import Schema

BAR_SCHEMA = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}

QUOTE_SCHEMA = {...}
```

**Step 2**: 创建 `trading/order.py` 数据类
```python
"""Trading data models."""

from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Order:
    """Order model."""
    instrument_id: int
    quantity: int
    price: float | None
    order_type: str  # "market" | "limit"
    side: str  # "buy" | "sell"
    trade_date: date
```

**Step 3**: 更新 `models/__init__.py` 导出
```python
from ditto_datahub.models.market import BAR_SCHEMA, QUOTE_SCHEMA
from ditto_datahub.models.trading import Order, Position
from ditto_datahub.models.portfolio import Portfolio
from ditto_datahub.models.strategy import Signal
```

**验收**：
- [ ] `common.py` 仅保留枚举（`Dataset/Domain/Source/OnDuplicate`）
- [ ] 所有 Schema/dataclass 按域分类到子目录
- [ ] `pixi run -e dev type --all` 通过

**Commit**: `refactor(datahub): split models into domain subdirectories`

---

### 阶段 3：接入 `futures/corporate_actions` 到 Port ingestion 主链路

**目标**：将 DataHub 已实现的 `futures/corporate_actions` 能力接入 Port 主摄取链路

#### 3.1 扩展 Dataset enum 与 registry

**Files**:
- `apps/port/src/ditto_port/models/config.py`
- `packages/datahub/src/ditto_datahub/models/common.py`

**Step 1**: 在 `Dataset` 枚举中新增
```python
class Dataset(str, Enum):
    # ... 现有 16 个数据集
    FUTURES = "futures"
    CORPORATE_ACTIONS = "corporate_actions"
```

**Step 2**: 在 `DATASET_REGISTRY` 中注册配置
```python
DATASET_REGISTRY[Dataset.FUTURES] = create_t1_config(
    dataset=Dataset.FUTURES,
    description="期货数据",
    typical_available_time=time(21, 0),
    depends_on=[Dataset.CALENDAR],
    critical_fields=["instrument_id", "trade_date", "knowledge_date"],
    task_name="ingest_futures",
    priority=60,
)

DATASET_REGISTRY[Dataset.CORPORATE_ACTIONS] = create_t1_config(
    dataset=Dataset.CORPORATE_ACTIONS,
    description="公司行为",
    typical_available_time=time(20, 0),
    depends_on=[Dataset.STOCK_BASIC],
    critical_fields=["instrument_id", "action_type", "effective_date"],
    task_name="ingest_corporate_actions",
    priority=65,
)
```

#### 3.2 扩展 DataSource ABC 与 TushareSource

**Files**:
- `packages/datahub/src/ditto_datahub/sources/base.py`
- `packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py`

**Step 1**: 在 `DataSource` ABC 新增方法
```python
@abstractmethod
def fetch_futures(self, trade_date: str) -> pl.DataFrame:
    """Fetch futures data."""
    pass

@abstractmethod
def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
    """Fetch corporate actions data."""
    pass
```

**Step 2**: 在 `TushareSource` 委托给 `CapitalTushareAdapter`
```python
def fetch_futures(self, trade_date: str) -> pl.DataFrame:
    """Fetch futures data."""
    compact_date = self._to_compact_date(trade_date)
    return self._capital.fetch_futures(
        ts_code=None,
        start_date=compact_date,
        end_date=compact_date,
    )

def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
    """Fetch corporate actions data."""
    compact_date = self._to_compact_date(trade_date)
    return self._capital.fetch_corporate_actions(
        ann_date=compact_date,
    )
```

#### 3.3 扩展 IngestionDataSource protocol

**Files**:
- `apps/port/src/ditto_port/services/ingestion/protocols.py`

**Step 1**: 在 `IngestionDataSource` Protocol 新增方法
```python
class IngestionDataSource(Protocol):
    # ... 现有方法
    def fetch_futures(self, trade_date: str) -> pl.DataFrame:
        """Fetch futures data."""
        ...

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """Fetch corporate actions data."""
        ...
```

#### 3.4 扩展 IngestionCoordinator 与 IngestionDataWriter

**Files**:
- `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- `apps/port/src/ditto_port/services/ingestion/data_writer.py`

**Step 1**: 在 `coordinator._fetch_data` handlers 字典新增映射
```python
handlers: dict[Dataset, Callable[[], pl.DataFrame]] = {
    # ... 现有映射
    Dataset.FUTURES: lambda: self._source.fetch_futures(trade_date),
    Dataset.CORPORATE_ACTIONS: lambda: self._source.fetch_corporate_actions(trade_date),
}
```

**Step 2**: 在 `data_writer.write_data` handlers 字典新增映射
```python
handlers: dict[Dataset, Callable[[], WriteResult]] = {
    # ... 现有映射
    Dataset.FUTURES: lambda: self._write_capital(
        dataset, dataset_enum, df, year
    ),
    Dataset.CORPORATE_ACTIONS: lambda: self._write_fundamental(
        dataset, dataset_enum, df, year
    ),
}
```

**验收**：
- [ ] `Dataset` 枚举包含 18 个数据集
- [ ] `DATASET_REGISTRY` 包含 futures/corporate_actions 配置
- [ ] DataSource/Coordinator/Writer 全链路支持新数据集
- [ ] 单测覆盖（`test_datasets_unit.py` + `test_coordinator_unit.py`）

**Commit**: `feat(ingestion): add futures and corporate_actions to main ingestion chain`

---

### 阶段 4：PIT 策略显式化与配置开关

**目标**：引入 `PIT_ENABLED/PIT_DEFAULT_KNOWLEDGE_DELAY` 环境变量与数据集级 `PITPolicy` 策略

#### 4.1 创建 PIT 配置模块

**Files**:
- `packages/datahub/src/ditto_datahub/config/pit.py`
- `config/development/data_store.env`
- `config/testing/data_store.env`
- `config/production/data_store.env`

**Step 1**: 定义 `PITPolicy` 数据类
```python
"""PIT (Point-in-Time) policy configuration."""

from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class PITPolicy:
    """Point-in-Time policy for a dataset."""
    primary_key: tuple[str, ...]
    version_column: str  # "knowledge_date" or "effective_from"
    interval_type: Literal["point", "interval"]
    interval_end: str | None = None  # "effective_to"
    dedup_strategy: Literal["keep_last", "interval_check"] = "keep_last"
    knowledge_delay_days: int = 1  # T+N 发布延迟
```

**Step 2**: 定义数据集级策略映射
```python
# packages/datahub/src/ditto_datahub/config/pit.py

PIT_POLICIES: dict[str, PITPolicy] = {
    "stock_daily": PITPolicy(
        primary_key=("instrument_id", "trade_date"),
        version_column="knowledge_date",
        interval_type="point",
        knowledge_delay_days=1,
    ),
    "adj_factor": PITPolicy(
        primary_key=("instrument_id", "trade_date"),
        version_column="knowledge_date",
        interval_type="point",
        knowledge_delay_days=1,
    ),
    "balance_sheet": PITPolicy(
        primary_key=("instrument_id", "report_date", "effective_from"),
        version_column="effective_from",
        interval_type="interval",
        interval_end="effective_to",
        dedup_strategy="interval_check",
        knowledge_delay_days=1,
    ),
    "valuation_metrics": PITPolicy(
        primary_key=("instrument_id", "trade_date", "effective_from"),
        version_column="effective_from",
        interval_type="interval",
        interval_end="effective_to",
        dedup_strategy="interval_check",
        knowledge_delay_days=1,
    ),
    "futures": PITPolicy(
        primary_key=("instrument_id", "trade_date", "effective_from"),
        version_column="effective_from",
        interval_type="interval",
        interval_end="effective_to",
        dedup_strategy="interval_check",
        knowledge_delay_days=1,
    ),
    "index_member": PITPolicy(
        primary_key=("index_id", "instrument_id", "effective_from"),
        version_column="effective_from",
        interval_type="interval",
        interval_end="effective_to",
        dedup_strategy="interval_check",
        knowledge_delay_days=0,  # 当日生效
    ),
    # ... 其他数据集策略
}
```

**Step 3**: 环境变量配置
```bash
# config/development/data_store.env
PIT_ENABLED=true
PIT_DEFAULT_KNOWLEDGE_DELAY=1

# config/testing/data_store.env
PIT_ENABLED=true
PIT_DEFAULT_KNOWLEDGE_DELAY=0  # 测试环境无延迟

# config/production/data_store.env
PIT_ENABLED=true
PIT_DEFAULT_KNOWLEDGE_DELAY=1
```

**Step 4**: 适配器读取策略
```python
# packages/datahub/src/ditto_datahub/sources/tushare/adapters/capital.py

from ditto_datahub.config.pit import PIT_POLICIES

def fetch_futures(self, ...) -> pl.DataFrame:
    policy = PIT_POLICIES["futures"]
    # 根据 policy.knowledge_delay_days 计算 knowledge_date
    computed_columns = {
        "knowledge_date": pl.col("trade_date") + pl.duration(days=policy.knowledge_delay_days)
    }
    ...
```

**验收**：
- [ ] `PITPolicy` 数据类定义完整
- [ ] `PIT_POLICIES` 覆盖所有 PIT 数据集
- [ ] 环境变量正确加载
- [ ] 适配器按策略计算 `knowledge_date`

**Commit**: `feat(pit): add explicit PIT policy configuration`

---

### 阶段 5：DQ 告警与 quarantine 落库闭环

**目标**：实现 `_send_alert` 与 `_quarantine_data` TODO，完成运维闭环

#### 5.1 实现 quarantine 落库

**Files**:
- `apps/port/src/ditto_port/services/ingestion/quality/service.py`
- `packages/datahub/src/ditto_datahub/runtime/quality/quarantine_store.py`（已存在）

**Step 1**: 实现 `QualityService._quarantine_data`
```python
def _quarantine_data(
    self,
    df: pl.DataFrame,
    result: DQResult,
    dataset: str,
) -> None:
    """Quarantine data with quality issues."""
    # 提取有问题样本的行
    bad_rows = []
    for issue in result.issues:
        for sample in issue.sample_data:
            bad_rows.append({
                "dataset": dataset,
                "trade_date": sample.get("trade_date"),
                "instrument_id": sample.get("instrument_id"),
                "field": sample.get("field"),
                "bad_value": sample.get("value"),
                "severity": issue.severity.value,
                "rule": issue.rule_name,
                "message": issue.message,
            })

    if bad_rows:
        bad_df = pl.DataFrame(bad_rows)
        # 使用注入的 quarantine_store 写入
        self._quarantine_store.write(bad_df)
        logger.info(
            "Quarantined bad data",
            event="dq_quarantine",
            dataset=dataset,
            count=len(bad_rows),
        )
```

**Step 2**: 在 DI 容器中注入 `quarantine_store`
```python
# apps/port/src/ditto_port/registry/core.py

from ditto_datahub.runtime.quality.quarantine_store import QuarantineStore

@provide
def quality_service(
    engine: QualityEngine,
    quarantine_store: QuarantineStore,
) -> QualityService:
    """Quality service with quarantine support."""
    return QualityService(
        engine=engine,
        quarantine_store=quarantine_store,
    )
```

**Step 3**: 更新 `QualityService.__init__`
```python
def __init__(
    self,
    engine: QualityEngine,
    quarantine_store: QuarantineStore | None = None,
) -> None:
    self._engine = engine
    self._quarantine_store = quarantine_store
```

#### 5.2 实现告警发送

**Files**:
- `apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py`
- `apps/port/src/ditto_port/services/ingestion/quality/reconciliation_service.py`
- `apps/port/src/ditto_port/jobs/tasks/dq_batch.py`

**Step 1**: 创建告警发送接口（Protocol）
```python
# apps/port/src/ditto_port/services/ingestion/quality/alerting.py

from typing import Protocol

class AlertChannel(Protocol):
    """Alert channel protocol."""

    def send_alert(
        self,
        title: str,
        message: str,
        severity: str,
        metadata: dict[str, object],
    ) -> None:
        """Send alert notification."""
        ...
```

**Step 2**: 实现日志告警通道（默认实现）
```python
class LogAlertChannel:
    """Log-based alert channel (fallback)."""

    def send_alert(
        self,
        title: str,
        message: str,
        severity: str,
        metadata: dict[str, object],
    ) -> None:
        logger.warning(
            "DQ alert notification",
            event="dq_alert",
            title=title,
            message=message,
            severity=severity,
            **metadata,
        )
```

**Step 3**: 注入告警通道
```python
# apps/port/src/ditto_port/registry/core.py

@provide
def alert_channel() -> AlertChannel:
    """Alert channel (currently log-based, can be swapped)."""
    return LogAlertChannel()

@provide
def l3_batch_service(
    engine: QualityEngine,
    hub: DataHub,
    alert_channel: AlertChannel,
) -> L3BatchService:
    """L3 batch check service with alert support."""
    return L3BatchService(
        engine=engine,
        hub=hub,
        alert_channel=alert_channel,
    )
```

**Step 4**: 更新 `_send_alert` 实现
```python
# apps/port/src/ditto_port/services/ingestion/quality/l3_batch_service.py

def __init__(
    self,
    engine: QualityEngine,
    hub: Any,
    alert_channel: AlertChannel,
) -> None:
    self._engine = engine
    self._hub = hub
    self._alert_channel = alert_channel

def _send_alert(
    self,
    trade_date: str,
    dataset: str,
    issues: list[Any],
) -> None:
    """Send DQ alert notification."""
    alert_issues = [
        {
            "severity": i.severity.value,
            "rule": i.rule_name,
            "message": i.message,
        }
        for i in issues
        if i.severity.value in ("alert", "error")
    ]

    if alert_issues:
        self._alert_channel.send_alert(
            title=f"DQ Alert: {dataset}",
            message=f"{len(alert_issues)} issues found on {trade_date}",
            severity="alert" if any(i["severity"] == "alert" for i in alert_issues) else "warning",
            metadata={
                "trade_date": trade_date,
                "dataset": dataset,
                "issues": alert_issues,
            },
        )
```

**验收**：
- [ ] `quarantine_store.write` 被正确调用
- [ ] `_send_alert` 使用注入的 `AlertChannel`
- [ ] 单测覆盖 quarantine 落库与告警发送
- [ ] `pixi run -e dev test --unit` 全绿

**Commit**: `feat(dq): implement quarantine storage and alert sending`

---

## 三、验收标准与测试策略

### 3.1 门禁命令

每个阶段完成后必须通过：

```bash
pixi run -e dev lint
pixi run -e dev fmt-check
pixi run -e dev type --all
pixi run -e dev test --unit
pixi run -e dev arch-check
pixi run -e dev ci
```

### 3.2 覆盖率要求

- 分支覆盖率 ≥ 80%
- 新增代码必须有对应单元测试

### 3.3 架构门禁

- `ARCH500/ARCH510`：`instrument_id/source_ticker` 语义
- `ARCH520`：禁止 legacy 别名
- `ARCH530~ARCH533`：禁止旧表名/语义

---

## 四、风险与注意事项

1. **PIT 策略变更**：引入显式策略后需验证现有 `knowledge_date` 计算逻辑兼容性
2. **告警通道扩展**：当前仅实现日志告警，未来扩展钉钉/邮件需确保 `AlertChannel` 接口稳定
3. **futures/corporate_actions**：需验证 DataHub Store 表结构已创建（`schema.sql` 包含对应表定义）

---

## 五、下一步

**执行方式**：Subagent-Driven（当前会话，逐任务派发子 Agent，快速迭代）

**后续行动**：
1. 开始执行阶段 1（Port API 分层重构）
2. 每完成一个阶段更新本文档状态
3. 全部阶段完成后合并到 `feature/v5-architecture-refactor`

---

**最后更新**: 2026-02-08
**分支**: `feature/v5-architecture-refactor`
