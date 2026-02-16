# Registry 目录重构设计

> 基于 2026-02-14 代码审查的架构改进设计

## 背景

代码审查发现以下架构问题：

| Finding | 问题 | 优先级 |
|---------|------|--------|
| ENG-101 | 测试稳定性 - `reset_observability` fixture 与 CliRunner I/O 冲突 | P0 |
| ARCH-202 | `datahub.py` 过大（1042 行），组合根职责过重 | P1 |
| ARCH-201 | 路由层需知道 DataHub 类型（`AdjType`, `MarketBarsQuery`） | P2 |

本文档重点解决 **ARCH-202**（Registry 目录重构），同时记录 ENG-101 和 ARCH-201 的修复方案。

---

## 1. Registry 目录重构

### 1.1 设计原则

1. **按架构层组织**：infra / core / datahub，与 packages 分层对应
2. **大模块统一导出**：每个大模块 `__init__.py` 导出 `get_xxx_providers()` 工厂函数
3. **子域拆分 Provider**：大模块内部按子域拆分独立 Provider

### 1.2 目录结构

```
ditto_port/registry/
├── __init__.py              # 顶层导出（聚合 infra/core/datahub）
├── container.py             # 容器工厂（组装所有 Provider）
├── init_providers.py        # 初始化 Provider（保持独立）
│
├── infra/                   # Infrastructure 层
│   ├── __init__.py          # 导出 get_infra_providers()
│   ├── config.py            # 配置相关 Provider
│   ├── observability.py     # 观测相关 Provider
│   └── notification.py      # 通知 Provider
│
├── core/                    # Core 层
│   ├── __init__.py          # 导出 get_core_providers()
│   └── quality.py           # DQ 引擎 Provider
│
└── datahub/                 # DataHub 层
    ├── __init__.py          # 导出 get_datahub_providers()
    ├── sources.py           # 数据源 Provider（Tushare 等）
    ├── runtime.py           # Runtime Layer + Services
    ├── metadata.py          # Metadata Domain
    ├── market.py            # Market Domain
    ├── fundamental.py       # Fundamental Domain
    ├── capital.py           # Capital Domain
    ├── macro.py             # Macro Domain
    └── features.py          # Features + Factors Domain
```

### 1.3 层级对应关系

| Registry 模块 | 对应 Package | 内容 |
|--------------|-------------|------|
| **infra/** | `packages/infra` | 配置、观测、通知 |
| **core/** | `packages/core` | DQ 引擎 |
| **datahub/** | `packages/datahub` | 数据源、Store、Service |

### 1.4 各模块 `__init__.py` 导出模式

#### infra/__init__.py

```python
from .config import ConfigProvider
from .observability import ObservabilityProvider
from .notification import NotificationProvider

__all__ = [
    "ConfigProvider",
    "ObservabilityProvider",
    "NotificationProvider",
    "get_infra_providers",
]

def get_infra_providers():
    """返回 Infrastructure 层的所有 Provider."""
    return [
        ConfigProvider(),
        ObservabilityProvider(),
        NotificationProvider(),
    ]
```

#### core/__init__.py

```python
from .quality import QualityProvider

__all__ = ["QualityProvider", "get_core_providers"]

def get_core_providers():
    """返回 Core 层的所有 Provider."""
    return [QualityProvider()]
```

#### datahub/__init__.py

```python
from .sources import SourcesProvider
from .runtime import RuntimeProvider
from .metadata import MetadataProvider
from .market import MarketProvider
from .fundamental import FundamentalProvider
from .capital import CapitalProvider
from .macro import MacroProvider
from .features import FeaturesProvider

__all__ = [
    "SourcesProvider",
    "RuntimeProvider",
    "MetadataProvider",
    "MarketProvider",
    "FundamentalProvider",
    "CapitalProvider",
    "MacroProvider",
    "FeaturesProvider",
    "get_datahub_providers",
]

def get_datahub_providers():
    """返回 DataHub 层的所有 Provider."""
    return [
        SourcesProvider(),
        RuntimeProvider(),
        MetadataProvider(),
        MarketProvider(),
        FundamentalProvider(),
        CapitalProvider(),
        MacroProvider(),
        FeaturesProvider(),
    ]
```

### 1.5 container.py 使用方式

```python
# ditto_port/registry/container.py
from dishka import make_container, make_async_container

from .infra import get_infra_providers
from .core import get_core_providers
from .datahub import get_datahub_providers

__all__ = ["make_app_container", "make_async_app_container"]

def _get_base_providers():
    """获取所有 Provider（按层级组装）."""
    return (
        *get_infra_providers(),   # Infrastructure 层
        *get_core_providers(),    # Core 层
        *get_datahub_providers(), # DataHub 层
    )

def make_app_container():
    return make_container(*_get_base_providers())

def make_async_app_container():
    return make_async_container(*_get_base_providers())
```

### 1.6 顶层 `__init__.py`

```python
# ditto_port/registry/__init__.py
from .infra import ConfigProvider, ObservabilityProvider, NotificationProvider
from .core import QualityProvider
from .datahub import (
    SourcesProvider,
    RuntimeProvider,
    MetadataProvider,
    MarketProvider,
    FundamentalProvider,
    CapitalProvider,
    MacroProvider,
    FeaturesProvider,
)

__all__ = [
    # Infrastructure 层
    "ConfigProvider",
    "ObservabilityProvider",
    "NotificationProvider",
    # Core 层
    "QualityProvider",
    # DataHub 层
    "SourcesProvider",
    "RuntimeProvider",
    "MetadataProvider",
    "MarketProvider",
    "FundamentalProvider",
    "CapitalProvider",
    "MacroProvider",
    "FeaturesProvider",
]
```

### 1.7 拆分前后对照

| 原文件 | 行数 | 拆分后 |
|--------|------|--------|
| `config.py` | 218 | `infra/config.py` + `infra/observability.py` |
| `core.py` | 116 | `core/quality.py` |
| `datahub.py` | 1042 | `datahub/` 下 8 个文件 |
| `sources.py` | 50 | `datahub/sources.py` |
| `notification.py` | ~150 | `infra/notification.py` |
| `init_providers.py` | - | 保持不变 |

### 1.8 DataHub 各 Provider 职责

| Provider | 内容 | 预估行数 |
|----------|------|----------|
| `SourcesProvider` | TushareSource, DataSources | ~50 |
| `RuntimeProvider` | SQLitePool, SQLiteClient, InstrumentIdAllocator, FreezeManager, FileLock, IngestionLogService, QualityRecordService, SourceService, SqlEngine | ~120 |
| `MetadataProvider` | InstrumentReader/Writer, CalendarReader/Writer, IndustryReader/Writer, IndustryMappingReader/Writer, UniverseReader/Writer, MetadataService | ~90 |
| `MarketProvider` | Stock/ETF/Index Bars, Status, Adj, Constituent, MarketService | ~140 |
| `FundamentalProvider` | Financial (Balance/Income/CashFlow), Dividend, CorporateActions, Forecast, Express, FundamentalService | ~150 |
| `CapitalProvider` | Margin, Pledge, Valuation, Futures, IndexComposition, CapitalService | ~120 |
| `MacroProvider` | Indicator, IndicatorMetadata, MacroService | ~60 |
| `FeaturesProvider` | TechnicalIndicator, Factor, FeatureService, FactorService | ~100 |

---

## 2. ENG-101: 测试稳定性修复

### 2.1 问题分析

```python
# 当前实现
@pytest.fixture(autouse=True)
def reset_observability() -> Generator[None, None, None]:
    from ditto_infra.foundation import reset_for_testing
    reset_for_testing()  # setup
    yield
    reset_for_testing()  # teardown - 与 CliRunner I/O 冲突
```

**问题链条**：
1. `reset_for_testing()` 调用 `shutdown()` 清理全局资源
2. teardown 时关闭 I/O 流
3. `CliRunner.invoke()` 使用捕获的 I/O 流
4. 导致 `ValueError: I/O operation on closed file`

### 2.2 修复方案

**方案 B+C：移除 autouse + CLI 目录空 override**

#### Step 1: 移除 autouse

```python
# apps/port/tests/conftest.py
@pytest.fixture  # 移除 autouse=True
def reset_observability() -> Generator[None, None, None]:
    """仅在显式请求时重置可观测性状态."""
    from ditto_infra.foundation import reset_for_testing
    reset_for_testing()
    yield
    reset_for_testing()
```

#### Step 2: CLI 测试目录添加空 override

```python
# apps/port/tests/unit/cli/conftest.py
import pytest
from collections.abc import Generator

@pytest.fixture(autouse=True)
def reset_observability() -> Generator[None, None, None]:
    """CLI 测试不重置 observability，避免 I/O 冲突."""
    yield  # 空操作
```

#### Step 3: 需要的测试显式使用

```python
def test_something(reset_observability):  # 显式请求
    ...
```

---

## 3. ARCH-201: 跨层依赖优化（P2 可选）

### 3.1 当前状态

```python
# market.py (Port 层路由)
from ditto_datahub.services.market_service import (
    AdjType,           # ← DataHub 层类型
    MarketBarsQuery,   # ← DataHub 层类型
    MarketService,     # ← DataHub 层 Service
)

# 转换逻辑在路由层
def _map_adjustment(adj: Adjustment) -> AdjType:
    mapping = {
        Adjustment.NONE: AdjType.NONE,
        Adjustment.QFQ: AdjType.QFQ,
        Adjustment.HFQ: AdjType.HFQ,
    }
    return mapping[adj]
```

### 3.2 优化方案

**结论**：Port 层依赖 DataHub Service 是合理的，只需封装转换逻辑。

**改进**：把转换逻辑封装到 Request 模型中

```python
# ditto_port/models/market.py
from ditto_datahub.services.market_service import AdjType, MarketBarsQuery

class BarsRequest(BaseModel):  # 原 BarsQuery
    """K 线查询请求."""

    def to_service_query(self) -> MarketBarsQuery:
        """转换为 DataHub 层查询对象."""
        return MarketBarsQuery(
            instrument_ids=self.instrument_ids,
            start=self.start_date.isoformat() if self.start_date else None,
            end=self.end_date.isoformat() if self.end_date else None,
            adj=self._map_adjustment(),
        )

    def _map_adjustment(self) -> AdjType:
        mapping = {
            Adjustment.NONE: AdjType.NONE,
            Adjustment.QFQ: AdjType.QFQ,
            Adjustment.HFQ: AdjType.HFQ,
        }
        return mapping[self.adjustment]
```

路由层简化为：

```python
@router.post("/bars")
async def post_bars(
    request: BarsRequest,
    service: Annotated[MarketService, FromComponent()],
):
    df = await asyncio.to_thread(service.find_bars, request.to_service_query())
    ...
```

---

## 4. 实施计划

| PR | 内容 | 优先级 | 工作量 | 状态 |
|----|------|--------|--------|------|
| PR-1 | ENG-101: 修复测试稳定性 | P0 | S | ✅ 完成 |
| PR-2 | ARCH-202: Registry 目录重构 | P1 | M | ✅ 完成 |
| PR-3 | ARCH-201: 封装转换逻辑到 Request 模型 | P2 | S | 待实施 |

### PR-2 实施步骤

1. 创建目录结构 `infra/`, `core/`, `datahub/`
2. 拆分 `config.py` → `infra/config.py` + `infra/observability.py`
3. 移动 `notification.py` → `infra/notification.py`
4. 移动 `core.py` → `core/quality.py`
5. 拆分 `datahub.py` → `datahub/` 下 8 个文件
6. 移动 `sources.py` → `datahub/sources.py`
7. 更新 `container.py` 使用 `get_xxx_providers()`
8. 更新顶层 `__init__.py`
9. 删除原文件
10. 运行测试验证

---

## 5. 参考

- 代码审查报告 (2026-02-14)
- [CLAUDE.md](/.claude/CLAUDE.md) - 项目规范
