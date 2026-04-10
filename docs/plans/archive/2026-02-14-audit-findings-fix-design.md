# 审计问题修复设计

> 基于 2026-02-14 架构审计报告的修复计划

## 问题清单

| ID | 严重度 | 问题 | 决策 |
|----|--------|------|------|
| SEC-002 | High | 日志泄露敏感信息 | 删除敏感字段 |
| SEC-004 | High | 测试日志端点生产可访问 | 环境判断 |
| ARCH-003 | High | 环境变量不一致 | 使用 ENVIRONMENT，DITTO_ENV 弃用 |
| ARCH-005 | Medium | DataSources 重复提供 | 删除 DataHubProvider.sources() |
| ARCH-001 | High | ConfigInitProvider 空实现 | 添加空检查告警 |
| ENG-007 | Medium | capital else 静默吞掉 | 改为 raise |
| ENG-006 | Medium | TushareClient 生命周期 | 添加 close() + context manager |
| ENG-008 | Medium | 对账返回 dict | 改为强类型 ReconciliationResult |
| ENG-009 | Low | 容器模板重复 | 抽取工厂函数 |

---

## PR-1: 安全修复（SEC-002 + SEC-004）

### 1.1 SEC-002: 删除日志中的敏感字段

**文件**：
- `packages/infra/src/ditto_infra/services/notification/channels/webhook.py`
- `packages/infra/src/ditto_infra/services/notification/channels/telegram.py`

**修改**：

```python
# webhook.py:69-73 (修改前)
logger.info(
    "Webhook sent successfully",
    event="webhook_sent",
    url=self._settings.webhook_url,  # 删除此行
)

# 修改后
logger.info("Webhook sent successfully", event="webhook_sent")
```

```python
# telegram.py:65-69 (修改前)
logger.info(
    "Telegram message sent successfully",
    event="telegram_sent",
    chat_id=self._settings.telegram_chat_id,  # 删除此行
)

# 修改后
logger.info("Telegram message sent successfully", event="telegram_sent")
```

### 1.2 SEC-004: 测试日志端点环境判断

**文件**：`apps/port/src/ditto_port/main.py`

**修改**：

```python
# main.py:283-289 (修改前)
@app.get("/api/v1/logs/test")
async def generate_test_logs() -> dict[str, str]:
    """测试日志记录功能."""
    logger.info("Test info log", test_data="example")
    logger.warning("Test warning log", test_data="example")
    logger.error("Test error log", test_data="example")
    return {"message": "Test logs generated"}

# 修改后
from ditto_infra.foundation.config import get_environment

@app.get("/api/v1/logs/test")
async def generate_test_logs() -> dict[str, str]:
    """测试日志记录功能（仅开发/测试环境可用）."""
    env = get_environment()
    if env.is_production:
        raise HTTPException(status_code=404, detail="Not found")

    logger.info("Test info log", test_data="example")
    logger.warning("Test warning log", test_data="example")
    logger.error("Test error log", test_data="example")
    return {"message": "Test logs generated"}
```

**测试**：
- 添加单元测试验证 production 环境返回 404
- 添加单元测试验证 development 环境正常工作

---

## PR-2: 环境变量统一（ARCH-003）

### 2.1 统一使用 ENVIRONMENT

**决策**：保留 `ENVIRONMENT`，标记 `DITTO_ENV` 为弃用

**修改文件**：

1. **`apps/port/src/ditto_port/cli/commands/init.py:23`**

```python
# 修改前
env_str = os.getenv("DITTO_ENV", "development")

# 修改后
from ditto_infra.foundation.config import get_environment

def _load_data_root() -> Path:
    environment = get_environment()  # 使用统一入口
    loader = ConfigLoader(environment)
    ...
```

2. **`apps/port/tests/integration/conftest.py:28`**

```python
# 修改前
os.environ["ENVIRONMENT"] = "testing"

# 保持不变（正确使用 ENVIRONMENT）
```

3. **更新 `.claude/CLAUDE.md`**

```markdown
# 修改前
| 运行时环境 | `DITTO_ENV` | `development`, `testing`, `production` |

# 修改后
| 运行时环境 | `ENVIRONMENT` | `development`, `testing`, `production` |
```

**测试**：
- 更新相关单元测试使用 ENVIRONMENT
- 添加兼容性测试确保 DITTO_ENV 仍可工作（带弃用警告）

---

## PR-3: DI 清理（ARCH-005）

### 3.1 删除重复的 DataSources provider

**文件**：`apps/port/src/ditto_port/registry/datahub.py`

**修改**：删除 `sources()` 方法（line 1002-1011）

```python
# 删除以下代码
@provide
def sources(self, tushare_source: TushareSource) -> DataSources:
    """外部数据源组合器."""
    return DataSources(tushare=tushare_source)
```

**验证**：
- 确保 `DataSourcesProvider.data_sources()` 被正确注入
- 运行 `pixi run -e dev check` 确保无破坏性变更

---

## PR-4: 初始化框架落地（ARCH-001）

### 4.1 设计分析

**当前状态**：
- `ConfigInitCoordinator` 是预留框架，没有任何 `ConfigInitProvider` 实现
- 数据库初始化在 `DataHubProvider.sqlite_pool()` 中自动完成（DI 容器创建时）
- 配置目录由各服务按需创建

**目标**：
- 将初始化逻辑从 DI 容器抽取到 `ConfigInitProvider`
- 支持显式 `ditto init` 命令触发
- 支持 Server 启动时自动检查

### 4.2 实现 DataRootInitProvider

**新文件**：`packages/infra/src/ditto_infra/foundation/config/providers/data_root.py`

```python
"""数据根目录初始化提供者."""

from __future__ import annotations

from pathlib import Path

from ditto_infra.foundation.config.initializer import (
    ConfigInitProvider,
    InitResult,
    InitScope,
)
from loguru import logger


class DataRootInitProvider(ConfigInitProvider):
    """
    数据根目录初始化.

    职责：创建 DataRootConfig 中定义的所有目录结构。
    """

    def __init__(self, directories: list[str] | None = None) -> None:
        """
        初始化.

        Args:
            directories: 需要创建的目录列表（相对于 data_root）。
                         None 表示使用默认列表。

        """
        self._directories = directories or self._default_directories()

    @property
    def name(self) -> str:
        return "data_root"

    @property
    def scope(self) -> InitScope:
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查 data_root 是否存在."""
        return not data_root.exists()

    def initialize(self, data_root: Path) -> InitResult:
        """创建目录结构."""
        try:
            created: list[str] = []
            for dir_path in self._directories:
                full_path = data_root / dir_path
                if not full_path.exists():
                    full_path.mkdir(parents=True, exist_ok=True)
                    created.append(dir_path)

            logger.info(
                "DataRoot directories created",
                event="dataroot_init",
                count=len(created),
            )

            return InitResult(
                provider=self.name,
                success=True,
                message=f"Created {len(created)} directories",
            )

        except Exception as e:
            logger.exception("Failed to create DataRoot directories")
            return InitResult(
                provider=self.name,
                success=False,
                message=f"Failed: {e}",
            )

    @staticmethod
    def _default_directories() -> list[str]:
        """默认目录列表（与 DataRootConfig 属性对应）."""
        return [
            # 市场数据
            "market/stock/bars/daily",
            "market/etf/bars/daily",
            "market/index/bars/daily",
            "market/stock/status",
            "market/etf/status",
            "market/stock/adj",
            "market/etf/adj",
            "market/etf/nav",
            # 元数据
            "metadata",
            # 资金流
            "capital/flow",
            "capital/margin",
            "capital/top_board",
            "capital/limit_board",
            "capital/chip",
            # 基本面
            "fundamental/financial",
            "fundamental/indicator",
            "fundamental/forecast",
            "fundamental/holding",
            # 特征
            "features/technical/price",
            "features/technical/indicators_narrow",
            "features/technical/indicators_wide",
            # 因子
            "factors/narrow/style",
            "factors/wide/style",
            "factors/factors_narrow",
            "factors/factors_wide",
            # 宏观
            "macro/indicators",
            # 通用
            "logs",
            "backups",
            "temp",
            "db",
            "locks",
        ]
```

### 4.3 实现 MetadataDbInitProvider

**新文件**：`packages/infra/src/ditto_infra/foundation/config/providers/metadata_db.py`

```python
"""元数据库初始化提供者."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from ditto_infra.foundation.config.initializer import (
    ConfigInitProvider,
    InitResult,
    InitScope,
)
from ditto_infra.foundation.db.sqlite_pool import SQLitePool
from loguru import logger


class MetadataDbInitProvider(ConfigInitProvider):
    """
    元数据库 Schema 初始化.

    职责：创建 metadata.sqlite 并初始化 schema。
    注意：如果数据库已存在且 schema 匹配，则跳过。
    """

    @property
    def name(self) -> str:
        return "metadata_db"

    @property
    def scope(self) -> InitScope:
        return InitScope.STARTUP

    def check(self, data_root: Path) -> bool:
        """检查数据库是否需要初始化."""
        db_path = data_root / "metadata" / "metadata.sqlite"
        return not db_path.exists()

    def initialize(self, data_root: Path) -> InitResult:
        """初始化数据库 schema."""
        try:
            db_path = data_root / "metadata" / "metadata.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # 获取 schema.sql 路径
            schema_traversable = files("ditto_data.scripts") / "schema.sql"
            schema_path = Path(str(schema_traversable))

            pool = SQLitePool(str(db_path), schema_path=schema_path)
            pool.init_schema()
            pool.close()

            logger.info(
                "Metadata database initialized",
                event="metadata_db_init",
                db_path=str(db_path),
            )

            return InitResult(
                provider=self.name,
                success=True,
                message=f"Database initialized at {db_path}",
            )

        except Exception as e:
            logger.exception("Failed to initialize metadata database")
            return InitResult(
                provider=self.name,
                success=False,
                message=f"Failed: {e}",
            )
```

### 4.4 注册 Providers

**修改文件**：`apps/port/src/ditto_port/registry/config.py`

```python
# 添加导入
from ditto_infra.foundation.config.providers import (
    DataRootInitProvider,
    MetadataDbInitProvider,
)

# 修改 init_coordinator 方法
@provide
def init_coordinator(self) -> ConfigInitCoordinator:
    """配置初始化协调器（注册所有 providers）."""
    coordinator = ConfigInitCoordinator()
    coordinator.register(DataRootInitProvider())
    coordinator.register(MetadataDbInitProvider())
    return coordinator
```

### 4.5 更新 sqlite_pool Provider

**修改文件**：`apps/port/src/ditto_port/registry/datahub.py`

```python
# 移除自动 init_schema 调用（已由 ConfigInitCoordinator 处理）
@provide
def sqlite_pool(
    self,
    config: DataRootConfig,
) -> Iterator[SQLitePool]:
    """SQLite 连接池（应用级单例）."""
    db_path = config.metadata_db_path
    # 确保父目录存在（兼容性保留，但主要由 DataRootInitProvider 处理）
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_traversable = files("ditto_data.scripts") / "schema.sql"
    schema_path = Path(str(schema_traversable))

    # 创建 pool，但不再自动调用 init_schema()
    # init_schema 由 MetadataDbInitProvider 在启动时执行
    pool = SQLitePool(str(db_path), schema_path=schema_path)
    yield pool
    pool.close()
```

### 4.6 文件结构

```
packages/infra/src/ditto_infra/foundation/config/
├── __init__.py
├── environment.py
├── initializer.py
└── providers/
    ├── __init__.py
    ├── data_root.py      # 新增
    └── metadata_db.py    # 新增
```

### 4.7 测试

```python
# test_init_providers_unit.py

class TestDataRootInitProvider:
    def test_check_returns_true_when_not_exists(self, tmp_path: Path) -> None:
        provider = DataRootInitProvider()
        assert provider.check(tmp_path) is True

    def test_check_returns_false_when_exists(self, tmp_path: Path) -> None:
        provider = DataRootInitProvider()
        provider.initialize(tmp_path)
        assert provider.check(tmp_path) is False

    def test_initialize_creates_directories(self, tmp_path: Path) -> None:
        provider = DataRootInitProvider()
        result = provider.initialize(tmp_path)

        assert result.success is True
        assert (tmp_path / "metadata").exists()
        assert (tmp_path / "logs").exists()


class TestMetadataDbInitProvider:
    def test_initialize_creates_database(self, tmp_path: Path) -> None:
        provider = MetadataDbInitProvider()
        result = provider.initialize(tmp_path)

        assert result.success is True
        db_path = tmp_path / "metadata" / "metadata.sqlite"
        assert db_path.exists()
```

---

## PR-5: Fail-Fast 加固（ENG-007）

### 5.1 capital 写入未知分支显式失败

**文件**：`apps/port/src/ditto_port/services/ingestion/data_writer.py`

**修改**：

```python
# data_writer.py:480-483 (修改前)
elif capital_dataset == "futures_position":
    records_written = self._capital_service.save_futures(df)
else:
    records_written = 0

# 修改后
elif capital_dataset == "futures_position":
    records_written = self._capital_service.save_futures(df)
else:
    raise ValueError(
        f"Unknown capital_dataset: {capital_dataset}. "
        f"Expected one of: valuation_metrics, margin_trading, pledge_ratio, futures_position"
    )
```

**测试**：
- 添加单元测试验证未知 dataset 抛出 ValueError

---

## PR-6: 资源生命周期（ENG-006）

### 6.1 TushareSource 添加 close()

**文件**：`packages/data/src/ditto_data/sources/tushare/tushare_source.py`

**修改**：

```python
# 添加 close 方法
def close(self) -> None:
    """释放 HTTP 连接资源."""
    if hasattr(self, "_client") and self._client:
        self._client.close()
```

**文件**：`apps/port/src/ditto_port/registry/sources.py`

**修改**：改为上下文管理器模式

```python
# 修改前
@provide
def tushare_source(
    self,
    data_source_settings: DataSourceSettings,
) -> TushareSource:
    return TushareSource(
        settings=data_source_settings,
        token=data_source_settings.tushare_token,
    )

# 修改后（使用 yield 语法，dishka 会自动处理清理）
@provide
def tushare_source(
    self,
    data_source_settings: DataSourceSettings,
) -> Iterator[TushareSource]:
    source = TushareSource(
        settings=data_source_settings,
        token=data_source_settings.tushare_token,
    )
    yield source
    source.close()
```

**测试**：
- 添加单元测试验证 close() 被调用

---

## PR-7: 强类型返回值（ENG-008）

### 7.1 创建 ReconciliationResult

**新文件**：`apps/port/src/ditto_port/services/ingestion/quality/models.py`

```python
"""质量对账领域模型."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReconciliationResult:
    """对账结果（强类型）."""

    trade_date: str
    dataset: str
    passed: bool
    issue_count: int
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None

    @property
    def has_error(self) -> bool:
        """是否存在异常."""
        return self.error is not None

    def to_dict(self) -> dict[str, object]:
        """转换为字典（兼容旧代码）."""
        result: dict[str, object] = {
            "trade_date": self.trade_date,
            "dataset": self.dataset,
            "passed": self.passed,
            "issue_count": self.issue_count,
        }
        if self.skipped:
            result["skipped"] = self.skip_reason
        if self.error:
            result["error"] = self.error
        return result
```

**修改文件**：`apps/port/src/ditto_port/services/ingestion/quality/reconciliation_service.py`

```python
# 修改返回类型和实现
from .models import ReconciliationResult

async def daily_reconciliation(
    self,
    primary_df: pl.DataFrame,
    trade_date: str,
    dataset: str = "stock_daily",
) -> ReconciliationResult:  # 强类型返回
    ...
    # 成功时
    return ReconciliationResult(
        trade_date=trade_date,
        dataset=dataset,
        passed=result.passed,
        issue_count=len(result.issues),
    )

    # 跳过时
    return ReconciliationResult(
        trade_date=trade_date,
        dataset=dataset,
        passed=True,
        issue_count=0,
        skipped=True,
        skip_reason="no_secondary_data",
    )

    # 异常时
    return ReconciliationResult(
        trade_date=trade_date,
        dataset=dataset,
        passed=False,
        issue_count=0,
        error=f"{type(e).__name__}: {e!s}",
    )
```

**测试**：
- 更新所有单元测试使用 ReconciliationResult

---

## PR-8: 容器工厂（ENG-009）

### 8.1 抽取统一容器工厂

**新文件**：`apps/port/src/ditto_port/registry/container.py`

```python
"""DI 容器工厂."""

from dishka import make_async_container, make_container

from .config import ConfigProvider
from .core import CoreProvider
from .datahub import DataHubProvider
from .sources import DataSourcesProvider

__all__ = ["make_app_container", "make_async_app_container"]


def _get_base_providers() -> tuple[object, ...]:
    """获取基础 Provider 列表."""
    return (
        ConfigProvider(),
        CoreProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )


def make_app_container() -> object:
    """创建同步容器."""
    return make_container(*_get_base_providers())


def make_async_app_container() -> object:
    """创建异步容器."""
    return make_async_container(*_get_base_providers())
```

**修改文件**：
- `apps/port/src/ditto_port/main.py`
- `apps/port/src/ditto_port/cli/context.py`
- `apps/port/src/ditto_port/jobs/context.py`

```python
# 修改前
container = make_async_container(
    ConfigProvider(), CoreProvider(), DataHubProvider(), DataSourcesProvider()
)

# 修改后
from ditto_port.registry.container import make_async_app_container

container = make_async_app_container()
```

---

## 实施顺序

```
Week 1:
├── PR-1: 安全修复（SEC-002 + SEC-004）[0.5h]
├── PR-2: 环境变量统一（ARCH-003）[0.5h]
└── PR-3: DI 清理（ARCH-005）[0.25h]

Week 2:
├── PR-4: 初始化框架告警（ARCH-001）[0.25h]
├── PR-5: Fail-Fast 加固（ENG-007）[0.25h]
├── PR-6: 资源生命周期（ENG-006）[0.5h]
└── PR-7: 强类型返回值（ENG-008）[1h]

Week 3:
└── PR-8: 容器工厂（ENG-009）[0.5h]
```

**总预估工作量**：约 4 小时

---

## 验证清单

每个 PR 完成后必须通过：

- [x] `pixi run -e dev check`（lint + fmt + type + test --fast）
- [x] `pixi run -e dev arch-check`（架构约束检查）
- [x] 相关单元测试通过
- [x] 分支覆盖率 ≥ 80%

---

## 实施状态

| PR | 问题 ID | 状态 | 提交 |
|----|---------|------|------|
| PR-1 | SEC-002 + SEC-004 | ✅ 完成 | 525dbb3 |
| PR-2 | ARCH-003 | ✅ 完成 | 7f74d81, 867719b, 728db17 |
| PR-3 | ARCH-005 | ✅ 完成 | cdb9d23 |
| PR-4 | ARCH-001 | ✅ 完成 | 80e5333 |
| PR-5 | ENG-007 | ✅ 完成 | 7fcdd9a |
| PR-6 | ENG-006 | ✅ 完成 | 7fcdd9a |
| PR-7 | ENG-008 | ✅ 完成 | 9191eee |
| PR-8 | ENG-009 | ✅ 完成 | 9191eee |

**实施日期**：2026-02-14
**实际工作量**：约 2 小时
**验证结果**：All checks passed!
