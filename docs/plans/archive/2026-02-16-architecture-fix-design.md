# 架构问题修复设计

> 基于架构审查发现的问题修复，涵盖 P0/P1 优先级问题

## 概述

### 问题背景

| ID | 严重性 | 问题 |
|----|--------|------|
| ARCH-001 | Blocker | SQLite 路径不一致：`metadata/metadata.sqlite` vs `meta/hub.sqlite` |
| ARCH-002 | High | `DatabaseSettings` 被计算但未被运行时消费 |
| ARCH-003 | High | 组合逻辑分散在 CLI/Jobs，非 registry 持有 DataHub 依赖知识 |
| ARCH-004 | Medium | 同一 flow 创建两个容器实例（资源重复初始化）|
| ARCH-005 | Medium | Dataset 枚举重复定义 + 路由映射散落 |
| ENG-004 | High | 测试环境变量 `DB_SQLITE_PATH` 未生效 |
| ENG-005 | High | `test_ingest_market_stock_help` 测试失败 |

### 解决方案概述

| 问题 | 解决方案 |
|------|----------|
| ARCH-001/002/ENG-004/005 | 统一配置到 `DataStoreSettings` |
| ARCH-003/004 | 收敛上下文工厂到 `registry/contexts/` |
| ARCH-005 | 统一 Dataset 枚举 + 增强 `get_asset_class()` 方法 |

---

## 设计详情

### 1. DataStoreSettings 定义

**文件:** `packages/data/src/ditto_data/config/data_store.py`

```python
"""数据存储配置 - 统一管理所有存储路径和引擎配置。"""

from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class SqlEngineConfig(BaseModel):
    """SQL 引擎性能配置。"""

    model_config = ConfigDict(extra="ignore")

    enable_plan_cache: bool = Field(default=True, description="启用查询计划缓存")
    plan_cache_size: int = Field(default=1000, ge=100, description="缓存大小")
    slow_query_threshold: float = Field(default=1.0, ge=0.1, description="慢查询阈值(秒)")


class DataStoreSettings(BaseModel):
    """
    数据存储配置 - 统一配置入口。

    替代原有的 DataRootConfig 和 DatabaseSettings，
    提供所有数据存储相关的配置和路径派生。
    """

    model_config = ConfigDict(extra="ignore")

    # ========== 根配置 ==========
    data_root: Path = Field(default=Path("data"), description="数据根目录")

    # ========== 数据库路径（可选覆盖）==========
    sqlite_path: Path | None = Field(default=None, description="SQLite 路径覆盖")
    duckdb_path: Path | None = Field(default=None, description="DuckDB 路径覆盖")

    # ========== 引擎配置 ==========
    sql_engine: SqlEngineConfig = Field(
        default_factory=SqlEngineConfig,
        description="SQL 引擎配置"
    )

    # ========== 解析后的数据库路径（唯一真源）==========

    @property
    def resolved_sqlite_path(self) -> Path:
        """解析后的 SQLite 路径（唯一真源）。"""
        return self.sqlite_path or self.data_root / "metadata" / "metadata.sqlite"

    @property
    def resolved_duckdb_path(self) -> Path:
        """解析后的 DuckDB 路径。"""
        return self.duckdb_path or self.data_root / "db" / "ditto.duckdb"

    # ========== 元数据路径 ==========

    @property
    def metadata_db_path(self) -> Path:
        """元数据库路径（兼容别名）。"""
        return self.resolved_sqlite_path

    # ========== 市场数据路径 ==========

    @property
    def market_stock_bars_path(self) -> Path:
        return self.data_root / "market" / "stock" / "bars" / "daily"

    @property
    def market_etf_bars_path(self) -> Path:
        return self.data_root / "market" / "etf" / "bars" / "daily"

    @property
    def market_index_bars_path(self) -> Path:
        return self.data_root / "market" / "index" / "bars" / "daily"

    @property
    def market_stock_status_path(self) -> Path:
        return self.data_root / "market" / "stock" / "status"

    @property
    def market_etf_status_path(self) -> Path:
        return self.data_root / "market" / "etf" / "status"

    @property
    def market_stock_adj_path(self) -> Path:
        return self.data_root / "market" / "stock" / "adj"

    @property
    def market_etf_adj_path(self) -> Path:
        return self.data_root / "market" / "etf" / "adj"

    @property
    def market_etf_nav_path(self) -> Path:
        return self.data_root / "market" / "etf" / "nav"

    # ========== 资金流路径 ==========

    @property
    def capital_flow_path(self) -> Path:
        return self.data_root / "capital" / "flow"

    @property
    def capital_margin_path(self) -> Path:
        return self.data_root / "capital" / "margin"

    @property
    def capital_top_board_path(self) -> Path:
        return self.data_root / "capital" / "top_board"

    @property
    def capital_limit_board_path(self) -> Path:
        return self.data_root / "capital" / "limit_board"

    @property
    def capital_chip_path(self) -> Path:
        return self.data_root / "capital" / "chip"

    # ========== 基本面路径 ==========

    @property
    def fundamental_financial_path(self) -> Path:
        return self.data_root / "fundamental" / "financial"

    @property
    def fundamental_indicator_path(self) -> Path:
        return self.data_root / "fundamental" / "indicator"

    @property
    def fundamental_forecast_path(self) -> Path:
        return self.data_root / "fundamental" / "forecast"

    @property
    def fundamental_holding_path(self) -> Path:
        return self.data_root / "fundamental" / "holding"

    # ========== 宏观路径 ==========

    @property
    def macro_indicators_path(self) -> Path:
        return self.data_root / "macro" / "indicators"

    # ========== 特征路径 ==========

    @property
    def features_technical_price_path(self) -> Path:
        return self.data_root / "features" / "technical" / "price"

    @property
    def features_technical_indicators_narrow_path(self) -> Path:
        return self.data_root / "features" / "technical" / "indicators_narrow"

    @property
    def features_technical_indicators_wide_path(self) -> Path:
        return self.data_root / "features" / "technical" / "indicators_wide"

    # ========== 因子路径 ==========

    @property
    def factors_narrow_style_path(self) -> Path:
        return self.data_root / "factors" / "narrow" / "style"

    @property
    def factors_wide_style_path(self) -> Path:
        return self.data_root / "factors" / "wide" / "style"

    @property
    def factors_narrow_path(self) -> Path:
        return self.data_root / "factors" / "factors_narrow"

    @property
    def factors_wide_path(self) -> Path:
        return self.data_root / "factors" / "factors_wide"

    # ========== 通用路径 ==========

    @property
    def logs_path(self) -> Path:
        return self.data_root / "logs"

    @property
    def backups_path(self) -> Path:
        return self.data_root / "backups"

    @property
    def temp_path(self) -> Path:
        return self.data_root / "temp"

    @property
    def db_path(self) -> Path:
        return self.data_root / "db"


__all__ = ["DataStoreSettings", "SqlEngineConfig"]
```

---

### 2. SqlEngine 修改

**文件:** `packages/data/src/ditto_data/runtime/sql_engine.py`

**关键变更:**
- 构造函数接收 `DataStoreSettings` 而非 `data_root: Path`
- SQLite 路径从 `settings.resolved_sqlite_path` 获取（唯一真源）
- 性能参数从 `settings.sql_engine` 获取

```python
from ditto_data.config.data_store import DataStoreSettings

class SqlEngine:
    """DuckDB SQL engine - 统一配置注入。"""

    def __init__(
        self,
        settings: DataStoreSettings,
    ) -> None:
        """
        初始化 SqlEngine。

        Args:
            settings: 数据存储配置（统一配置源）
        """
        self._settings = settings
        self.data_root = settings.data_root
        self._sqlite_path = settings.resolved_sqlite_path  # 唯一真源

        self.con = duckdb.connect(":memory:")
        self._sqlite_attached = False

        # 从配置读取性能参数
        self._enable_plan_cache = settings.sql_engine.enable_plan_cache
        self._plan_cache: dict[str, Any] = {}
        self._plan_cache_size = settings.sql_engine.plan_cache_size
        self._slow_query_threshold = settings.sql_engine.slow_query_threshold

        self._setup()
        # ...

    def _attach_sqlite(self) -> None:
        """Attach SQLite metadata database on demand."""
        if self._sqlite_attached:
            return

        sqlite_path = self._sqlite_path  # 使用注入的路径
        if not sqlite_path.exists():
            return
        # ...
```

---

### 3. RuntimeProvider 修改

**文件:** `apps/port/src/ditto_port/registry/datahub/runtime.py`

**关键变更:**
- `sqlite_pool` 和 `sql_engine` 改为依赖 `DataStoreSettings`
- 删除对 `DataRootConfig` 的依赖

```python
from ditto_data.config.data_store import DataStoreSettings

class RuntimeProvider(Provider):
    """Runtime Layer Provider - 基础设施和运行时服务."""

    scope = Scope.APP

    @provide
    def sqlite_pool(
        self,
        settings: DataStoreSettings,
    ) -> Iterator[SQLitePool]:
        """SQLite 连接池（应用级单例）."""
        db_path = settings.resolved_sqlite_path  # 唯一真源
        db_path.parent.mkdir(parents=True, exist_ok=True)

        schema_traversable = files("ditto_data.scripts") / "schema.sql"
        schema_path = Path(str(schema_traversable))
        pool = SQLitePool(str(db_path), schema_path=schema_path)
        pool.init_schema()
        yield pool
        pool.close()

    @provide
    def sql_engine(
        self,
        settings: DataStoreSettings,
    ) -> SqlEngine:
        """DuckDB SQL 引擎."""
        return SqlEngine(settings=settings)
```

---

### 4. ConfigProvider 修改

**文件:** `apps/port/src/ditto_port/registry/infra/config.py`

**关键变更:**
- 新增 `data_store_settings()` 方法
- 删除 `data_root_config()` 和 `database_settings()` 方法

```python
from ditto_data.config.data_store import DataStoreSettings

class ConfigProvider(Provider):
    """统一配置提供者（仅在 Port 层加载配置）。"""

    scope = Scope.APP

    @provide
    def data_store_settings(
        self,
        config_loader: ConfigLoader,
    ) -> DataStoreSettings:
        """加载数据存储配置。"""
        values = load_env_file(config_loader, "data_store")

        # 支持 CLI 透传的环境变量覆盖
        if override := os.getenv("DITTO_DATA_ROOT"):
            values["data_root"] = override
        if override := os.getenv("SQLITE_PATH"):
            values["sqlite_path"] = override
        if override := os.getenv("DUCKDB_PATH"):
            values["duckdb_path"] = override

        return DataStoreSettings.model_validate(values)
```

---

### 5. 配置文件变更

**删除:**
```
config/{development,testing,production}/database.env
```

**修改:** `config/{development,testing,production}/data_store.env`

```env
# 数据存储配置 - Development

# 根目录
DATA_ROOT=data

# 数据库路径（可选，未设置时自动计算）
# SQLITE_PATH=data/metadata/metadata.sqlite
# DUCKDB_PATH=data/db/ditto.duckdb

# SQL 引擎配置
SQL_ENGINE__ENABLE_PLAN_CACHE=true
SQL_ENGINE__PLAN_CACHE_SIZE=1000
SQL_ENGINE__SLOW_QUERY_THRESHOLD=1.0
```

---

### 6. 测试修复

#### ENG-004: 环境变量统一

**文件:** `apps/port/tests/conftest.py`

```python
# 之前
os.environ["DB_SQLITE_PATH"] = str(test_db_path)

# 之后
os.environ["SQLITE_PATH"] = str(test_db_path)
os.environ["DATA_ROOT"] = str(temp_dir)
```

#### ENG-005: 测试隔离

**文件:** `apps/port/tests/unit/cli/commands/ingest/test_market_unit.py`

```python
def test_ingest_market_stock_help(self, runner: CliRunner, mocker: MockerFixture) -> None:
    """测试 stock 命令帮助."""
    # 隔离 Prefect 客户端初始化
    mocker.patch("prefect.Client")
    mocker.patch("prefect.get_client")

    result = runner.invoke(app, ["ingest", "market", "stock", "--help"])
    assert result.exit_code == 0
    assert "股票日行情" in result.output
```

---

## 删除清单

| 文件/类 | 说明 |
|---------|------|
| `packages/data/src/ditto_data/config/database.py` | `DatabaseSettings` 类 |
| `packages/data/src/ditto_data/config/data_root.py` | `DataRootConfig` 类 |
| `config/{env}/database.env` | 数据库配置文件 |

---

## 导入更新

```python
# 之前
from ditto_data.config import DataRootConfig, DatabaseSettings

# 之后
from ditto_data.config import DataStoreSettings
```

---

## 实施步骤

```
Step 1: 创建 DataStoreSettings + SqlEngineConfig (data_store.py)
Step 2: 更新 config/__init__.py 导出
Step 3: 修改 SqlEngine 接收 DataStoreSettings
Step 4: 修改 RuntimeProvider
Step 5: 修改 ConfigProvider
Step 6: 更新所有导入点 (stores, services, tests)
Step 7: 修改 data_store.env 配置文件
Step 8: 删除 database.env
Step 9: 删除 DatabaseSettings + DataRootConfig
Step 10: 修复测试 fixture (ENG-004)
Step 11: 修复测试隔离 (ENG-005)
Step 12: 运行 pixi run -e dev check 验证
```

---

## 问题解决状态

| ID | 状态 | 解决方式 |
|----|------|----------|
| ARCH-001 | ✅ | `resolved_sqlite_path` 为唯一真源 |
| ARCH-002 | ✅ | Provider 直接依赖 `DataStoreSettings` |
| ENG-004 | ✅ | 统一使用 `SQLITE_PATH` 环境变量 |
| ENG-005 | ✅ | 隔离 Prefect 客户端 |

---

## 风险与回滚

**风险:**
- 大范围导入修改，可能遗漏边缘文件
- 历史数据目录 `meta/hub.sqlite` 需要手动迁移

**回滚策略:**
- 保留 `DataRootConfig` 和 `DatabaseSettings` 一次迭代后删除
- 单 PR 可直接 `git revert`

---

## 参考

- 架构审查报告 (ARCH-001, ARCH-002, ENG-004, ENG-005)
- [data_root.py](../packages/data/src/ditto_data/config/data_root.py)
- [sql_engine.py](../packages/data/src/ditto_data/runtime/sql_engine.py)
- [runtime.py](../apps/port/src/ditto_port/registry/datahub/runtime.py)

---

# Part 2: 组合根收敛 (ARCH-003, ARCH-004)

## 问题分析

### ARCH-003: 组合逻辑分散

**当前状态：**
- `cli/context.py` 和 `jobs/context.py` 都导入 7 个 DataHub 服务
- 新增服务需要多点同步

### ARCH-004: 同一 flow 创建两个容器实例

**当前状态：**
```python
# backfill.py / repair.py
with create_ingestion_context() as (...):
    with create_ingestion_log_context() as (...):  # 第二个容器
        ...
```

---

## 设计详情

### 1. 目录结构

**目标状态：**
```
apps/port/src/ditto_port/registry/
├── container.py        # dishka 容器定义
└── contexts/           # 新增：上下文工厂模块
    ├── __init__.py
    ├── bundle.py       # IngestionBundle 定义
    └── ingestion.py    # create_ingestion_bundle 工厂
```

---

### 2. IngestionBundle 定义

**文件:** `apps/port/src/ditto_port/registry/contexts/bundle.py`

```python
"""上下文组合包定义。"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ditto_data.services import IngestionLogService
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_service import SourceService

if TYPE_CHECKING:
    from ditto_port.services.ingestion import IngestionCoordinator


@dataclass(frozen=True)
class IngestionBundle:
    """
    摄入上下文组合包。

    包含数据摄入所需的所有服务和协调器。
    解决 ARCH-003（组合逻辑分散）和 ARCH-004（重复容器）问题。
    """
    metadata_service: MetadataService
    market_service: MarketService
    fundamental_service: FundamentalService
    capital_service: CapitalService
    macro_service: MacroService
    source_service: SourceService
    ingestion_log_service: IngestionLogService
    coordinator: "IngestionCoordinator"
```

---

### 3. 上下文工厂

**文件:** `apps/port/src/ditto_port/registry/contexts/ingestion.py`

```python
"""摄入上下文工厂。"""

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_data.services import IngestionLogService
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.source_service import SourceService

from ditto_port.registry.container import make_app_container
from ditto_port.registry.contexts.bundle import IngestionBundle
from ditto_port.services.ingestion import create_coordinator


@contextmanager
def create_ingestion_bundle(source: str = "tushare") -> Iterator[IngestionBundle]:
    """
    创建摄入上下文组合包（单容器）。

    解决 ARCH-004：替代嵌套的 create_ingestion_context + create_ingestion_log_context，
    确保单个 flow 只创建一个容器实例。

    Args:
        source: 数据源名称

    Yields:
        IngestionBundle: 包含所有摄入服务和协调器

    Example:
        with create_ingestion_bundle() as bundle:
            result = bundle.coordinator.ingest(...)
            bundle.metadata_service.is_trading_day(...)
    """
    container = make_app_container()
    try:
        # 获取所有服务
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        fundamental_service = container.get(FundamentalService)
        capital_service = container.get(CapitalService)
        macro_service = container.get(MacroService)
        source_service = container.get(SourceService)
        ingestion_log_service = container.get(IngestionLogService)

        # 创建协调器
        with create_coordinator(
            metadata_service=metadata_service,
            market_service=market_service,
            fundamental_service=fundamental_service,
            capital_service=capital_service,
            macro_service=macro_service,
            source_service=source_service,
            ingestion_log_service=ingestion_log_service,
            source_name=source,
        ) as coordinator:
            yield IngestionBundle(
                metadata_service=metadata_service,
                market_service=market_service,
                fundamental_service=fundamental_service,
                capital_service=capital_service,
                macro_service=macro_service,
                source_service=source_service,
                ingestion_log_service=ingestion_log_service,
                coordinator=coordinator,
            )
    finally:
        container.close()
```

---

### 4. 导出

**文件:** `apps/port/src/ditto_port/registry/contexts/__init__.py`

```python
from ditto_port.registry.contexts.bundle import IngestionBundle
from ditto_port.registry.contexts.ingestion import create_ingestion_bundle

__all__ = ["IngestionBundle", "create_ingestion_bundle"]
```

**文件:** `apps/port/src/ditto_port/registry/__init__.py`

```python
from ditto_port.registry.contexts import IngestionBundle, create_ingestion_bundle

__all__ = [..., "IngestionBundle", "create_ingestion_bundle"]
```

---

### 5. 调用点迁移

**backfill.py / repair.py:**

```python
# 之前（两个容器）
with create_ingestion_context() as (metadata_service, coordinator):
    with create_ingestion_log_context() as (metadata_service2, ingestion_log_service):
        ...

# 之后（单容器）
from ditto_port.registry import create_ingestion_bundle

with create_ingestion_bundle() as bundle:
    bundle.coordinator.ingest(...)
    bundle.ingestion_log_service.xxx(...)
    bundle.metadata_service.is_trading_day(...)
```

**CLI context.py:**

```python
# 之前：导入 7 个服务
from ditto_data.services.market_service import MarketService
from ditto_data.services.fundamental_service import FundamentalService
# ...

# 之后：只导入 Bundle
from ditto_port.registry import create_ingestion_bundle, IngestionBundle
```

---

## 删除清单

| 文件/函数 | 说明 |
|-----------|------|
| `jobs/context.py::create_ingestion_context` | 被 `create_ingestion_bundle` 替代 |
| `jobs/context.py::create_ingestion_log_context` | 被 `create_ingestion_bundle` 替代 |

**保留的简化上下文：**
- `create_metadata_context` - 单服务，无需 Bundle
- `create_dq_context` - 单服务，无需 Bundle
- `create_dq_and_metadata_context` - 可选迁移到 Bundle

---

## 问题解决状态

| ID | 状态 | 解决方式 |
|----|------|----------|
| ARCH-003 | ✅ | 服务导入收敛到 `registry/contexts/` |
| ARCH-004 | ✅ | `IngestionBundle` 单容器包含所有服务 |

---

# Part 3: Dataset 枚举统一 (ARCH-005)

## 问题分析

**当前状态：**
- `datahub/models/common.py`: DataHub 层 `Dataset` 枚举
- `port/models/config.py`: Port 层 `Dataset` 枚举（重复）
- 多处字符串映射：`coordinator.py`, `dq_batch.py`

---

## 设计详情

### 1. Dataset 枚举增强

**文件:** `packages/data/src/ditto_data/models/common.py`

```python
class Dataset(str, Enum):
    """支持的数据集类型。"""

    # ... 现有枚举值 ...

    @classmethod
    def is_basic_dataset(cls, dataset: str) -> bool:
        """判断是否为 basic 类数据集。"""
        return dataset in (
            cls.STOCK_BASIC.value,
            cls.ETF_BASIC.value,
            cls.INDEX_BASIC.value,
        )

    @classmethod
    def is_calendar_dataset(cls, dataset: str) -> bool:
        """判断是否为 calendar 数据集。"""
        return dataset == cls.CALENDAR.value

    # 新增：资产类别映射
    @classmethod
    def get_asset_class(cls, dataset: "Dataset | str") -> str:
        """
        获取数据集对应的资产类别。

        Args:
            dataset: 数据集枚举或字符串

        Returns:
            资产类别: "stock" | "etf" | "index" | "other"
        """
        dataset_value = dataset.value if isinstance(dataset, Dataset) else dataset
        mapping = {
            cls.STOCK_DAILY.value: "stock",
            cls.STOCK_STATUS.value: "stock",
            cls.ADJ_FACTOR.value: "stock",
            cls.ETF_DAILY.value: "etf",
            cls.FUND_ADJ.value: "etf",
            cls.INDEX_DAILY.value: "index",
        }
        return mapping.get(dataset_value, "other")
```

---

### 2. Port 层修改

**删除:** `apps/port/src/ditto_port/models/config.py` 中的 `Dataset` 类

**更新导入:** 所有使用 `Dataset` 的地方改为：

```python
# 之前
from ditto_port.models.config import Dataset

# 之后
from ditto_data.models import Dataset
```

**保留:** `TaskTier`, `DatasetSpec` 等配置类仍在 `port/models/config.py`

---

### 3. dq_batch.py 修改

```python
# 之前
dataset_asset_class = {"stock_daily": "stock", "etf_daily": "etf", ...}
asset_class = dataset_asset_class[dataset]

# 之后
from ditto_data.models import Dataset
asset_class = Dataset.get_asset_class(dataset)
```

---

## 问题解决状态

| ID | 状态 | 解决方式 |
|----|------|----------|
| ARCH-005 | ✅ | 统一 `Dataset` 枚举 + `get_asset_class()` 方法 |

---

# 实施计划汇总

## 完整实施步骤

```
=== Part 1: 配置统一 ===
Step 1:  创建 DataStoreSettings + SqlEngineConfig (data_store.py)
Step 2:  更新 config/__init__.py 导出
Step 3:  修改 SqlEngine 接收 DataStoreSettings
Step 4:  修改 RuntimeProvider
Step 5:  修改 ConfigProvider
Step 6:  更新所有导入点 (stores, services, tests)
Step 7:  修改 data_store.env 配置文件
Step 8:  删除 database.env
Step 9:  删除 DatabaseSettings + DataRootConfig
Step 10: 修复测试 fixture (ENG-004)
Step 11: 修复测试隔离 (ENG-005)

=== Part 2: 组合根收敛 ===
Step 12: 创建 registry/contexts/ 目录
Step 13: 创建 bundle.py (IngestionBundle)
Step 14: 创建 ingestion.py (create_ingestion_bundle)
Step 15: 更新 registry/__init__.py 导出
Step 16: 迁移 backfill.py / repair.py 调用点
Step 17: 迁移 CLI context.py 调用点
Step 18: 删除旧的 create_ingestion_context 等函数

=== Part 3: Dataset 统一 ===
Step 19: 在 Dataset 枚举中添加 get_asset_class() 方法
Step 20: 删除 port/models/config.py 中的 Dataset 类
Step 21: 更新所有 Dataset 导入点
Step 22: 修改 dq_batch.py 使用 get_asset_class()

=== Part 4: MacroQuery 类型修复 ===
Step 23: 创建 datahub/models/macro.py (MacroCategory, MacroFrequency)
Step 24: 修改 MacroQuery 接受 StrEnum 类型
Step 25: 更新 CLI macro.py 导入，删除 type: ignore
Step 26: 删除 port/models/macro.py 中的重复枚举

=== 验证 ===
Step 27: 运行 pixi run -e dev check 验证
```

---

## 问题解决状态汇总

| ID | 严重性 | 状态 | 解决方式 |
|----|--------|------|----------|
| ARCH-001 | Blocker | ✅ | `resolved_sqlite_path` 为唯一真源 |
| ARCH-002 | High | ✅ | Provider 直接依赖 `DataStoreSettings` |
| ARCH-003 | High | ✅ | 服务导入收敛到 `registry/contexts/` |
| ARCH-004 | Medium | ✅ | `IngestionBundle` 单容器 |
| ARCH-005 | Medium | ✅ | 统一 `Dataset` + `get_asset_class()` |
| ENG-001 | Medium | ✅ | MacroQuery 接受 StrEnum 枚举 |
| ENG-004 | High | ✅ | 统一使用 `SQLITE_PATH` 环境变量 |
| ENG-005 | High | ✅ | 隔离 Prefect 客户端 |

---

# Part 4: 类型边界修复 (ENG-001 - 部分)

## 问题分析

**macro.py 问题：**
- `MacroQuery.category` 期望 `Literal["economic", ...]`
- CLI 传递的是 `StrEnum`，类型不匹配
- 导致 `# type: ignore[arg-type]`

---

## 设计详情

### 1. 新增枚举定义

**文件:** `packages/data/src/ditto_data/models/macro.py`

```python
from enum import StrEnum


class MacroCategory(StrEnum):
    """宏观指标类别枚举。"""

    ECONOMIC = "economic"
    INTEREST_RATE = "interest_rate"
    EXCHANGE_RATE = "exchange_rate"
    MONEY_SUPPLY = "money_supply"


class MacroFrequency(StrEnum):
    """宏观指标频率枚举。"""

    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
```

---

### 2. 修改 MacroQuery

**文件:** `packages/data/src/ditto_data/services/macro_service.py`

```python
from ditto_data.models.macro import MacroCategory, MacroFrequency


@dataclass(frozen=True)
class MacroQuery:
    """Macro indicator query parameters."""

    indicators: list[int] | list[str] | None = None
    start: str | None = None
    end: str | None = None
    asof: str | None = None

    # 改为接受枚举类型
    category: MacroCategory | None = None
    frequency: MacroFrequency | None = None
```

---

### 3. CLI 修改

**文件:** `apps/port/src/ditto_port/cli/commands/query/macro.py`

```python
# 之前
from ditto_port.models.macro import MacroCategory, MacroFrequency

# 之后
from ditto_data.models.macro import MacroCategory, MacroFrequency

# 删除 # type: ignore[arg-type]
query = MacroQuery(
    start=start_date,
    end=end_date,
    category=cat_value,  # 类型匹配，无需 ignore
    frequency=freq_value,
)
```

---

### 4. 删除 Port 层重复枚举

**文件:** `apps/port/src/ditto_port/models/macro.py`

删除 `MacroCategory` 和 `MacroFrequency` 枚举（保留其他内容如 `to_indicator_list`）

---

## 问题解决状态

| ID | 状态 | 解决方式 |
|----|------|----------|
| ENG-001 (macro) | ✅ | MacroQuery 接受 StrEnum |

---

# 暂不处理的问题

| ID | 严重性 | 原因 |
|----|--------|------|
| ENG-001 (deploy.py) | Medium | TypeGuard 改动较大，优先级低 |
| ENG-001 (daily.py) | Medium | Prefect Future Protocol 需要更多调研 |
| ENG-002 | Low | 死代码，可后续清理 |
| ENG-003 | Low | 空包装，可后续清理 |
| ENG-006 | Medium | Bundle 重构改动大，后续迭代 |

---

# 实施记录

## 实施日期

2026-02-16

## 实施状态

**全部完成 ✅**

所有 27 个步骤已实施完成，验证通过：
- Lint: All checks passed
- Format: 613 files unchanged
- Type: 0 errors, 0 warnings, 0 notes
- Tests: 1689 passed
- Architecture: 6 contracts kept, 0 broken

## 关键变更

### Part 1: 配置统一
- 新增 `DataStoreSettings` 和 `SqlEngineConfig` 类
- 删除 `DatabaseSettings` 和 `DataRootConfig` 类
- `SqlEngine` 接收 `DataStoreSettings` 注入
- 环境变量统一为 `SQLITE_PATH`, `DATA_ROOT`

### Part 2: 组合根收敛
- 新增 `apps/port/src/ditto_port/registry/contexts/` 目录
- 新增 `IngestionBundle` 数据类和 `create_ingestion_bundle` 工厂
- 删除旧的 `create_ingestion_context` 等函数
- 所有 flow 迁移到使用 `IngestionBundle`

### Part 3: Dataset 枚举统一
- 新增 `Dataset.get_asset_class()` 方法
- 删除 Port 层重复的 `Dataset` 枚举
- `dq_batch.py` 使用 `get_asset_class()` 替代硬编码映射

### Part 4: MacroQuery 类型修复
- 新增 `MacroCategory` 和 `MacroFrequency` 枚举
- `MacroQuery` 接受 StrEnum 类型
- 删除 CLI 中的 `# type: ignore[arg-type]` 注释
