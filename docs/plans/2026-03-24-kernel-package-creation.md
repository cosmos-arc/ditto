# ditto_kernel 包创建与类型迁移实施计划

> **Status: COMPLETED** (2026-03-24)
> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建独立的 `ditto_kernel` 共享内核包，将跨层共享的领域原语（枚举、NewType）从 DataHub/Core/Port 迁移到统一位置，建立类型归属治理基座。

**Architecture:** 新建 `packages/kernel/` 作为零逻辑、零外部依赖的纯类型包，位于依赖图最底层。DataHub 和 Core 平等依赖 Kernel，Port 依赖所有层。DataHub 原有导入路径通过 re-export 保持向后兼容。Core 的 `OrderDirection` 统一为 kernel 的 `OrderSide`。Port 的重复 `AssetClass` 定义删除，改为从 kernel 导入。

**Tech Stack:** Python 3.13, StrEnum, NewType, setuptools, pytest, basedpyright, import-linter

**设计文档:** [shared-kernel-and-model-governance-design](2026-03-24-shared-kernel-and-model-governance-design.md)

---

## 关键决策摘要

| 决策 | 结论 | 理由 |
|------|------|------|
| `InstrumentIdRange` | **暂不迁入** kernel | 仅 DataHub 使用，且含业务方法，不满足准入标准 #1 和 #2 |
| `Exchange` (normalization.py) | **保持分离**不重命名 | 与 enums.py 版本职责不同（外部 source 转换 vs 项目数据标准） |
| `AssetClass` 成员数 | **6 成员**（DataHub 完整版） | Port 3 成员子集删除，API 层如需限制在 API 层做 validation |
| Core → DataHub errors | **保留** ignore_imports | Core `engine/errors.py` 从 `ditto_datahub.errors` re-export，本轮不迁移 |
| Core `OrderDirection` | **统一为** kernel `OrderSide` | 值完全一致（BUY/SELL），消除命名歧义 |

## 迁移范围

### 迁入 kernel 的类型（5 个）

| 类型 | 来源 | 格式 |
|------|------|------|
| `InstrumentId` | 新建 | `NewType("InstrumentId", int)` |
| `AssetClass` | `datahub/models/enums.py` | `StrEnum`（6 成员） |
| `Exchange` | `datahub/models/enums.py` | `StrEnum`（XSHE/XSHG/XBSE） |
| `OrderSide` | `datahub/models/trading.py` | `StrEnum`（BUY/SELL） |
| `RunStatus` | `datahub/models/strategy_run.py` | `StrEnum`（PENDING/RUNNING/COMPLETED/FAILED） |

### 不迁入 kernel 的类型

| 类型 | 位置 | 理由 |
|------|------|------|
| `InstrumentIdRange` | DataHub `common.py` | 仅 DataHub 使用 + 含业务方法 |
| `Exchange` (normalization) | DataHub `sources/normalization.py` | DataHub 内部 source 转换，非跨层共享 |
| `OrderDirection` | Core `order_book.py` | 统一为 kernel `OrderSide` 后删除 |
| `AssetClass` (Port 3 成员) | Port `models/metadata.py` | 删除，改为从 kernel 导入 |
| `OrderStatus` | DataHub/Core 各自定义 | 值集不同，不强制统一 |

---

## 任务清单

### Task 1: 创建 kernel 包骨架

**复杂度:** S | **文件数:** 3 (新建)

**Files:**
- Create: `packages/kernel/pyproject.toml`
- Create: `packages/kernel/src/ditto_kernel/__init__.py`
- Create: `packages/kernel/tests/__init__.py`
- Modify: `pixi.toml:52-57`
- Modify: `pyproject.toml:276-281, 292-297, 370-374`

**Step 1: 创建目录结构**

```bash
mkdir -p packages/kernel/src/ditto_kernel
mkdir -p packages/kernel/tests/unit
touch packages/kernel/tests/__init__.py
touch packages/kernel/tests/unit/__init__.py
```

**Step 2: 创建 `packages/kernel/pyproject.toml`**

```toml
[project]
name = "ditto-kernel"
requires-python = ">= 3.13"
version = "0.1.0"

[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-dir]
"" = "src"
```

> 零运行时依赖。仅 stdlib。

**Step 3: 创建 `packages/kernel/src/ditto_kernel/__init__.py`**

```python
"""Ditto 共享内核 — 跨层领域原语.

提供跨层共享的纯类型定义（枚举、NewType、值对象）。
零业务行为、零外部依赖、零 I/O。

准入标准（5 条，全部满足才可进入）：
1. 跨层使用：至少被 2 个业务包直接导入
2. 零业务行为：纯值对象 / 枚举 / NewType
3. 稳定性高：不会随某个子域的迭代频繁变更
4. 无外部依赖：只依赖 Python 标准库
5. 纯值语义：不含序列化、持久化关注点
"""

__all__: list[str] = []
```

**Step 4: 更新 `pixi.toml` — 添加 kernel 到 workspace**

在 `[pypi-dependencies]` 的本地包区块中，`ditto-infra` 行之后添加：

```toml
ditto-kernel = { path = "packages/kernel", editable = true }
```

**Step 5: 更新根 `pyproject.toml` — extraPaths**

在 `[tool.basedpyright]` 的 `extraPaths` 列表中，`packages/infra/src` 之后添加：

```toml
    "packages/kernel/src",
```

**Step 6: 更新根 `pyproject.toml` — pythonpath**

在 `[tool.pytest.ini_options]` 的 `pythonpath` 列表中，`packages/infra/src` 之后添加：

```toml
    "packages/kernel/src",
```

**Step 7: 更新根 `pyproject.toml` — version_files**

在 `[tool.commitizen]` 的 `version_files` 列表中添加：

```toml
    "packages/kernel/src/ditto_kernel/__init__.py:__version__",
```

同时需要在 `packages/kernel/src/ditto_kernel/__init__.py` 中添加版本号（在 `__all__` 之前）：

```python
__version__ = "0.1.0"
```

**Step 8: 验证包可安装**

```bash
pixi run -e dev python -c "import ditto_kernel; print(ditto_kernel.__version__)"
```

Expected: `0.1.0`

**Step 9: Commit**

```bash
git add packages/kernel/ pixi.toml pyproject.toml
git commit -m "feat: 创建 ditto_kernel 共享内核包骨架"
```

---

### Task 2: 定义 kernel 类型 — identity + enums

**复杂度:** M | **文件数:** 4 (新建)

**前置:** Task 1

**Files:**
- Create: `packages/kernel/src/ditto_kernel/identity.py`
- Create: `packages/kernel/src/ditto_kernel/enums.py`
- Create: `packages/kernel/tests/unit/test_identity.py`
- Create: `packages/kernel/tests/unit/test_enums.py`
- Modify: `packages/kernel/src/ditto_kernel/__init__.py`

**Step 1: 写失败测试 — `test_identity.py`**

```python
"""ditto_kernel.identity 单元测试."""

from typing import NewType

from ditto_kernel.identity import InstrumentId


class TestInstrumentId:
    """InstrumentId NewType 测试."""

    def test_is_newtype(self) -> None:
        """InstrumentId 应为 int 上的 NewType."""
        assert InstrumentId.__supertype__ is int  # type: ignore[attr-defined]

    def test_accepts_int(self) -> None:
        """InstrumentId 应接受 int 值."""
        id_: InstrumentId = InstrumentId(1_000_001)
        assert id_ == 1_000_001

    def test_int_operations(self) -> None:
        """InstrumentId 应支持 int 运算（类型擦除后）."""
        id_: InstrumentId = InstrumentId(1_000_001)
        assert id_ + 1 == 1_000_002
        assert id_ > 0

    def test_type_safety_rejects_str(self) -> None:
        """basedpyright 应拒绝 str 赋值给 InstrumentId（编译期检查，运行时不阻断）."""
        # 运行时 NewType 是 no-op，这个测试主要确认类型定义正确
        id_: InstrumentId = InstrumentId(1)  # type: ignore[assignment]
        assert isinstance(id_, int)
```

**Step 2: 写失败测试 — `test_enums.py`**

```python
"""ditto_kernel.enums 单元测试."""

from ditto_kernel.enums import AssetClass, Exchange, OrderSide, RunStatus


class TestAssetClass:
    """AssetClass 枚举测试."""

    def test_members(self) -> None:
        """应包含 6 个成员."""
        assert len(AssetClass) == 6

    def test_values(self) -> None:
        """验证所有成员值."""
        assert AssetClass.STOCK == "stock"
        assert AssetClass.ETF == "etf"
        assert AssetClass.INDEX == "index"
        assert AssetClass.FUTURE == "future"
        assert AssetClass.BOND == "bond"
        assert AssetClass.FUND == "fund"

    def test_is_strenum(self) -> None:
        """应为 StrEnum，支持直接字符串比较."""
        assert AssetClass.STOCK == "stock"


class TestExchange:
    """Exchange 枚举测试（MIC 风格）."""

    def test_members(self) -> None:
        """应包含 3 个 A 股交易所."""
        assert len(Exchange) == 3

    def test_values(self) -> None:
        """验证 MIC 风格值."""
        assert Exchange.XSHE == "XSHE"
        assert Exchange.XSHG == "XSHG"
        assert Exchange.XBSE == "XBSE"


class TestOrderSide:
    """OrderSide 枚举测试."""

    def test_members(self) -> None:
        """应包含 2 个成员."""
        assert len(OrderSide) == 2

    def test_values(self) -> None:
        assert OrderSide.BUY == "buy"
        assert OrderSide.SELL == "sell"


class TestRunStatus:
    """RunStatus 枚举测试."""

    def test_members(self) -> None:
        """应包含 4 个成员."""
        assert len(RunStatus) == 4

    def test_values(self) -> None:
        assert RunStatus.PENDING == "pending"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
```

**Step 3: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/kernel/tests/unit/ -v
```

Expected: FAIL（`ModuleNotFoundError: No module named 'ditto_kernel.identity'`）

**Step 4: 实现 `identity.py`**

```python
"""共享身份类型.

Ditto 内部 canonical 主键的类型安全包装。
"""

from typing import NewType

__all__ = ["InstrumentId"]

InstrumentId = NewType("InstrumentId", int)
```

**Step 5: 实现 `enums.py`**

```python
"""共享枚举类型.

跨层共享的领域枚举，满足 kernel 准入标准：
- 至少被 2 个业务包直接导入
- 纯值语义，不含方法或 I/O
- 稳定性高，不会随子域迭代频繁变更
"""

from enum import StrEnum

__all__ = ["AssetClass", "Exchange", "OrderSide", "RunStatus"]


class AssetClass(StrEnum):
    """
    资产类型枚举.

    Attributes:
        STOCK: 股票
        ETF: 交易所交易基金
        INDEX: 指数
        FUTURE: 期货
        BOND: 债券
        FUND: 基金
    """

    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"
    FUTURE = "future"
    BOND = "bond"
    FUND = "fund"


class Exchange(StrEnum):
    """
    统一交易所枚举（ISO 10383 MIC 简化版）.

    用于跨层标识金融工具的交易场所。

    Members:
        XSHE: 深圳证券交易所
        XSHG: 上海证券交易所
        XBSE: 北京证券交易所
    """

    XSHE = "XSHE"  # 深圳证券交易所
    XSHG = "XSHG"  # 上海证券交易所
    XBSE = "XBSE"  # 北京证券交易所


class OrderSide(StrEnum):
    """
    订单方向枚举.

    统一 DataHub `OrderSide` 和 Core `OrderDirection` 为单一名称。
    """

    BUY = "buy"
    SELL = "sell"


class RunStatus(StrEnum):
    """
    策略运行状态枚举.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

**Step 6: 更新 `__init__.py` — 统一导出**

替换整个 `packages/kernel/src/ditto_kernel/__init__.py`：

```python
"""Ditto 共享内核 — 跨层领域原语.

提供跨层共享的纯类型定义（枚举、NewType、值对象）。
零业务行为、零外部依赖、零 I/O。

准入标准（5 条，全部满足才可进入）：
1. 跨层使用：至少被 2 个业务包直接导入
2. 零业务行为：纯值对象 / 枚举 / NewType
3. 稳定性高：不会随某个子域的迭代频繁变更
4. 无外部依赖：只依赖 Python 标准库
5. 纯值语义：不含序列化、持久化关注点
"""

__version__ = "0.1.0"

from ditto_kernel.enums import AssetClass, Exchange, OrderSide, RunStatus
from ditto_kernel.identity import InstrumentId

__all__ = [
    "AssetClass",
    "Exchange",
    "InstrumentId",
    "OrderSide",
    "RunStatus",
]
```

**Step 7: 运行测试确认通过**

```bash
pixi run -e dev pytest packages/kernel/tests/unit/ -v
```

Expected: 4 passed

**Step 8: Commit**

```bash
git add packages/kernel/
git commit -m "feat(kernel): 定义 InstrumentId, AssetClass, Exchange, OrderSide, RunStatus"
```

---

### Task 3: DataHub 导入迁移 — enums.py + trading.py + strategy_run.py

**复杂度:** M | **文件数:** 5 (修改)

**前置:** Task 2

**策略:** DataHub 原有模块保留类型定义，改为从 `ditto_kernel` 导入再 re-export。这样外部消费者（Port、测试）的 `from ditto_datahub.models.enums import AssetClass` 等导入路径不受影响。

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/models/enums.py`
- Modify: `packages/datahub/src/ditto_datahub/models/trading.py:17-21`
- Modify: `packages/datahub/src/ditto_datahub/models/strategy_run.py:13-19`
- Modify: `packages/datahub/src/ditto_datahub/models/common.py:9`
- Modify: `packages/datahub/pyproject.toml` (添加 ditto-kernel 依赖)

**Step 1: DataHub 添加 kernel 依赖**

在 `packages/datahub/pyproject.toml` 中添加：

```toml
[project]
name = "ditto-datahub"
requires-python = ">= 3.13"
version = "0.1.0"

dependencies = [
    "ditto-kernel",
]
```

**Step 2: 改写 `enums.py` — 从 kernel 导入并 re-export**

替换整个 `packages/datahub/src/ditto_datahub/models/enums.py`：

```python
"""
枚举定义模块.

跨层共享的枚举类型已迁移到 ditto_kernel。
本模块保留 re-export 以维持向后兼容。
"""

from ditto_kernel.enums import AssetClass, Exchange

__all__ = ["AssetClass", "Exchange"]
```

**Step 3: 改写 `trading.py` 中的 OrderSide — 从 kernel 导入**

修改 `packages/datahub/src/ditto_datahub/models/trading.py`，将 `OrderSide` 的定义替换为从 kernel 的 re-export：

在文件头部的导入区域添加：
```python
from ditto_kernel.enums import OrderSide as _KernelOrderSide
```

删除 `OrderSide` 类定义（第 17-21 行），替换为：
```python
# OrderSide 已迁移到 ditto_kernel.enums，此处 re-export 保持向后兼容
OrderSide = _KernelOrderSide
```

> 注意：不要删除 `OrderStatus`，它留在 DataHub（Core 的 `OrderStatus` 值集不同，不统一）。

**Step 4: 改写 `strategy_run.py` 中的 RunStatus — 从 kernel 导入**

修改 `packages/datahub/src/ditto_datahub/models/strategy_run.py`，将 `RunStatus` 的定义替换为从 kernel 的 re-export：

在文件头部的导入区域添加：
```python
from ditto_kernel.enums import RunStatus as _KernelRunStatus
```

删除 `RunStatus` 类定义（第 13-19 行），替换为：
```python
# RunStatus 已迁移到 ditto_kernel.enums，此处 re-export 保持向后兼容
RunStatus = _KernelRunStatus
```

**Step 5: 更新 `common.py` 的 AssetClass 导入**

修改 `packages/datahub/src/ditto_datahub/models/common.py:9`：

```python
# 原: from ditto_datahub.models.enums import AssetClass
# 改为从 kernel 导入（enums.py 已是 kernel 的 re-export）
from ditto_kernel.enums import AssetClass
```

> 或者保持 `from ditto_datahub.models.enums import AssetClass` 也可以（因为 enums.py 现在是从 kernel re-export 的），但直接从 kernel 导入更明确。

**Step 6: 运行 DataHub 测试验证**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/models/ -v
```

Expected: ALL PASSED

**Step 7: Commit**

```bash
git add packages/datahub/
git commit -m "refactor(datahub): 枚举类型改为从 ditto_kernel 导入并 re-export"
```

---

### Task 4: Core `OrderDirection` → `OrderSide` 统一

**复杂度:** M | **文件数:** 18 (7 源码 + 10 测试 + 1 pyproject.toml)

**前置:** Task 2

**策略:** Core 的 `OrderDirection` 与 kernel `OrderSide` 值完全一致（BUY="buy", SELL="sell"）。删除 `OrderDirection` 定义，所有引用改为从 `ditto_kernel` 导入 `OrderSide`。

**Files:**
- Modify: `packages/core/pyproject.toml` (添加 ditto-kernel 依赖)
- Modify: `packages/core/src/ditto_core/accounting/order_book.py:36-40` (删除 OrderDirection)
- Modify: `packages/core/src/ditto_core/accounting/buying_power.py:8`
- Modify: `packages/core/src/ditto_core/execution/trade_builder.py:17`
- Modify: `packages/core/src/ditto_core/execution/reality/slippage.py:13`
- Modify: `packages/core/src/ditto_core/execution/reality/settlement.py:15`
- Modify: `packages/core/src/ditto_core/execution/reality/fill.py:13`
- Modify: `packages/core/src/ditto_core/execution/reality/fee.py:13`
- Modify: `packages/core/src/ditto_core/execution/fills.py:13`
- Modify: 10 test files (import 替换)

**Step 1: Core 添加 kernel 依赖**

在 `packages/core/pyproject.toml` 中添加：

```toml
[project]
name = "ditto-core"
requires-python = ">= 3.13"
version = "0.1.0"

dependencies = [
    "ditto-kernel",
]
```

**Step 2: 修改 `order_book.py` — 删除 OrderDirection，添加 re-export**

在 `packages/core/src/ditto_core/accounting/order_book.py` 中：

1. 在导入区域添加：
```python
from ditto_kernel.enums import OrderSide
```

2. 删除 `OrderDirection` 类定义（第 36-40 行）。

3. 添加向后兼容别名（可选，避免破坏外部测试中的引用）：
```python
# OrderDirection 已统一为 ditto_kernel.OrderSide
OrderDirection = OrderSide
```

4. 更新 `__all__` 列表：
```python
__all__ = [
    "Order",
    "OrderBook",
    "OrderBookReadOnly",
    "OrderDirection",  # 向后兼容别名，实际指向 OrderSide
    "OrderEvent",
    "OrderSide",
    "OrderStatus",
    "OrderTicket",
    "OrderType",
    "StateTransitionError",
]
```

**Step 3: 批量替换 7 个源文件的导入**

每个文件中，将：
```python
from ditto_core.accounting.order_book import OrderDirection
```
替换为：
```python
from ditto_kernel.enums import OrderSide as OrderDirection
```

受影响的文件列表：
- `packages/core/src/ditto_core/accounting/buying_power.py:8`
- `packages/core/src/ditto_core/execution/trade_builder.py:17`
- `packages/core/src/ditto_core/execution/reality/slippage.py:13`
- `packages/core/src/ditto_core/execution/reality/settlement.py:15`
- `packages/core/src/ditto_core/execution/reality/fill.py:13`
- `packages/core/src/ditto_core/execution/reality/fee.py:13`
- `packages/core/src/ditto_core/execution/fills.py:13`

> 使用 `OrderSide as OrderDirection` 避免修改每个文件中的所有使用点，后续可逐步清理别名。

**Step 4: 批量替换 10 个测试文件的导入**

同样使用 `as` 别名，保持测试代码不变：

```python
# 原: from ditto_core.accounting.order_book import OrderDirection
# 改: from ditto_kernel.enums import OrderSide as OrderDirection
```

受影响的测试文件：
- `packages/core/tests/unit/accounting/test_buying_power_unit.py:8`
- `packages/core/tests/unit/accounting/test_account_unit.py:11`
- `packages/core/tests/unit/backtest/test_statistics_helpers_unit.py:16`
- `packages/core/tests/unit/backtest/test_serialization_unit.py:10`
- `packages/core/tests/unit/execution/test_fee_model_unit.py:6`
- `packages/core/tests/unit/execution/test_slippage_unit.py:6`
- `packages/core/tests/unit/execution/test_settlement_unit.py:4`
- `packages/core/tests/unit/execution/test_fills_unit.py:9`
- `packages/core/tests/unit/execution/test_fill_model_unit.py:7`
- `packages/core/tests/unit/execution/test_trade_builder_unit.py:9`

对于同时导入 `Order` 和 `OrderDirection` 的测试文件（如 `test_fee_model_unit.py`），保持 `Order` 从 `ditto_core.accounting.order_book` 导入不变：

```python
from ditto_core.accounting.order_book import Order
from ditto_kernel.enums import OrderSide as OrderDirection
```

**Step 5: 运行 Core 测试验证**

```bash
pixi run -e dev pytest packages/core/tests/unit/accounting/ packages/core/tests/unit/execution/ -v
```

Expected: ALL PASSED

**Step 6: Commit**

```bash
git add packages/core/
git commit -m "refactor(core): OrderDirection 统一为 ditto_kernel.OrderSide"
```

---

### Task 5: Port `AssetClass` 迁移

**复杂度:** S | **文件数:** 3 (修改)

**前置:** Task 2

**策略:** 删除 Port `models/metadata.py` 中的重复 `AssetClass` 定义（3 成员），改为从 `ditto_kernel` 导入（6 成员）。更新 `models/__init__.py` 和 API 路由的导入。

**Files:**
- Modify: `apps/port/src/ditto_port/models/metadata.py:21-34`
- Modify: `apps/port/src/ditto_port/models/__init__.py:90-96`
- Modify: `apps/port/src/ditto_port/api/routes/metadata.py:12-13`

**Step 1: 修改 `metadata.py` — 删除重复 AssetClass 定义**

在 `apps/port/src/ditto_port/models/metadata.py` 中：

1. 删除 `from enum import StrEnum`（不再需要，除非其他地方用到）。
2. 添加 `from ditto_kernel.enums import AssetClass`。
3. 删除 `AssetClass` 类定义（第 21-34 行）。

修改后文件头部的导入区域应为：
```python
from __future__ import annotations

from typing import Any

import polars as pl
from ditto_kernel.enums import AssetClass
from pydantic import BaseModel, ConfigDict, Field
```

**Step 2: 修改 `models/__init__.py` — AssetClass 改从 kernel 导入**

修改 `apps/port/src/ditto_port/models/__init__.py:90-96`：

```python
# 原:
# from ditto_port.models.metadata import (
#     AssetClass,
#     Instrument,
#     InstrumentQuery,
#     to_instrument,
#     to_instrument_list,
# )

# 改为: AssetClass 从 kernel 导入，其余从 metadata 导入
from ditto_kernel.enums import AssetClass
from ditto_port.models.metadata import (
    Instrument,
    InstrumentQuery,
    to_instrument,
    to_instrument_list,
)
```

**Step 3: 修改 `api/routes/metadata.py` — AssetClass 从 kernel 导入**

修改 `apps/port/src/ditto_port/api/routes/metadata.py:12-13`：

```python
# 原:
# from ditto_port.models.metadata import (
#     AssetClass,
#     Instrument,
#     to_instrument,
#     to_instrument_list,
# )

# 改为:
from ditto_kernel.enums import AssetClass
from ditto_port.models.metadata import (
    Instrument,
    to_instrument,
    to_instrument_list,
)
```

**Step 4: 运行 Port 测试验证**

```bash
pixi run -e dev pytest apps/port/tests/unit/models/ -v
```

Expected: ALL PASSED

**Step 5: Commit**

```bash
git add apps/port/
git commit -m "refactor(port): AssetClass 改为从 ditto_kernel 导入，删除重复定义"
```

---

### Task 6: Import Linter 规则更新

**复杂度:** M | **文件数:** 1 (修改)

**前置:** Task 3, Task 4

**Files:**
- Modify: `.importlinter`

**Step 1: 添加 `ditto_kernel` 到 root_packages**

```ini
[importlinter]
root_packages =
    ditto_infra
    ditto_datahub
    ditto_core
    ditto_port
    ditto_kernel
```

**Step 2: 更新 `layered-architecture` 层级**

```ini
[importlinter:contract:layered-architecture]
name = Layered Architecture
type = layers
# 从高层到低层：Port → Core → DataHub → Infra
# Kernel 在最底层，但 layers 检查不包含它（Kernel 无业务依赖，被所有层依赖）
layers =
    ditto_port
    ditto_core
    ditto_datahub
    ditto_infra
```

> Kernel 不加入 layers 检查，因为它不是垂直分层的一部分。它通过 `kernel-isolation` 和 `core-datahub-boundary` 的 `ignore_imports` 单独约束。

**Step 3: 添加 `kernel-isolation` 合约**

在 `datahub-boundary` 合约之前添加：

```ini
# ═══════════════════════════════════════════════════════════════════
# Kernel 层隔离：禁止依赖其他层
# ═══════════════════════════════════════════════════════════════════
[importlinter:contract:kernel-isolation]
name = Kernel must not depend on other layers
type = forbidden
source_modules =
    ditto_kernel.**
forbidden_modules =
    ditto_core.**
    ditto_datahub.**
    ditto_port.**
    ditto_infra.**
```

**Step 4: 重写 `core-datahub-boundary` — 双向禁止 + kernel 例外**

```ini
# ═══════════════════════════════════════════════════════════════════
# Core ↔ DataHub 边界：双向禁止互相依赖
# 两者均可依赖 ditto_kernel
# Core 保留对 ditto_datahub.errors 的 re-export 依赖
# ═══════════════════════════════════════════════════════════════════
[importlinter:contract:core-datahub-boundary]
name = Core and DataHub must not depend on each other
type = forbidden
source_modules =
    ditto_core.**
    ditto_datahub.**
forbidden_modules =
    ditto_core.**
    ditto_datahub.**
ignore_imports =
    ditto_core.** -> ditto_kernel.*
    ditto_datahub.** -> ditto_kernel.*
    ditto_core.** -> ditto_datahub.errors
unmatched_ignore_imports_alerting = none
```

> **关键变更**：原来的 `ignore_imports` 允许 `core → datahub.models.*`，现在移除。Core 只保留对 `datahub.errors` 的依赖（`engine/errors.py` re-export）。DataHub 不再需要 ignore。

**Step 5: 更新 `acyclic-packages` ancestors**

```ini
[importlinter:contract:acyclic-packages]
name = No circular dependencies between packages
type = acyclic_siblings
ancestors =
    ditto_infra
    ditto_datahub
    ditto_core
    ditto_port
    ditto_kernel
depth = 10
```

**Step 6: 运行架构检查**

```bash
pixi run -e dev arch-check
```

Expected: ALL CONTRACTS PASSED

如果 `core-datahub-boundary` 报 Core 仍有对 `datahub.models.*` 的导入（除了 errors），需要先清理。检查：

```bash
grep -r "from ditto_datahub" packages/core/src/ --include="*.py" | grep -v errors
```

根据当前分析，Core 只在 `engine/errors.py` 导入 `ditto_datahub.errors`，不应有其他 `datahub.models` 导入。如果发现，需要在本次清理。

**Step 7: Commit**

```bash
git add .importlinter
git commit -m "refactor(arch): import-linter 添加 kernel 隔离规则，Core↔DataHub 双向禁止"
```

---

### Task 7: DataHub models/__init__.py 更新 — kernel re-export

**复杂度:** S | **文件数:** 1 (修改)

**前置:** Task 3

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/models/__init__.py:25, 109-110`

**Step 1: 更新 enums 导入行**

修改第 25 行：

```python
# 原: from ditto_datahub.models.enums import AssetClass, Exchange
# 改为: 直接从 kernel 导入（enums.py 已是 re-export，但顶层 __init__ 应指向权威来源）
from ditto_kernel.enums import AssetClass, Exchange
```

**Step 2: 更新 RunStatus 导入行**

修改第 109 行：

```python
# 原: from ditto_datahub.models.strategy_run import RunStatus, StrategyRunRecord
# 改为:
from ditto_kernel.enums import RunStatus
from ditto_datahub.models.strategy_run import StrategyRunRecord
```

**Step 3: 更新 OrderSide 导入行**

修改第 110 行：

```python
# 原: from ditto_datahub.models.trading import Order, OrderSide, OrderStatus, Trade
# 改为:
from ditto_kernel.enums import OrderSide
from ditto_datahub.models.trading import Order, OrderStatus, Trade
```

**Step 4: 验证 DataHub 测试通过**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/ -v --fast
```

Expected: ALL PASSED

**Step 5: Commit**

```bash
git add packages/datahub/src/ditto_datahub/models/__init__.py
git commit -m "refactor(datahub): models/__init__ 改为从 ditto_kernel 导入共享类型"
```

---

### Task 8: 全量验证

**复杂度:** S | **文件数:** 0

**前置:** Task 1-7 全部完成

**Step 1: 运行完整检查**

```bash
pixi run -e dev check
```

Expected: lint + fmt + type + test 全部通过

**Step 2: 运行架构检查**

```bash
pixi run -e dev arch-check
```

Expected: ALL CONTRACTS PASSED（6 个合约全部绿）

**Step 3: 验证 kernel 无外部依赖**

```bash
pixi run -e dev python -c "
import ditto_kernel
# 确认可导入所有类型
from ditto_kernel import InstrumentId, AssetClass, Exchange, OrderSide, RunStatus
print(f'InstrumentId: {InstrumentId.__name__}')
print(f'AssetClass members: {len(AssetClass)}')
print(f'Exchange members: {len(Exchange)}')
print(f'OrderSide members: {len(OrderSide)}')
print(f'RunStatus members: {len(RunStatus)}')
"
```

Expected:
```
InstrumentId: InstrumentId
AssetClass members: 6
Exchange members: 3
OrderSide members: 2
RunStatus members: 4
```

**Step 4: 验证向后兼容 — DataHub 消费者不受影响**

```bash
pixi run -e dev python -c "
# 旧路径仍然可用
from ditto_datahub.models.enums import AssetClass, Exchange
from ditto_datahub.models import OrderSide, RunStatus
from ditto_datahub.models.trading import OrderSide as OS2
from ditto_datahub.models.strategy_run import RunStatus as RS2
assert AssetClass.STOCK == 'stock'
assert OrderSide.BUY == 'buy'
assert RunStatus.PENDING == 'pending'
print('DataHub backward compatibility: OK')
"
```

Expected: `DataHub backward compatibility: OK`

**Step 5: 验证 Core 消费者**

```bash
pixi run -e dev python -c "
# Core 通过 kernel 使用 OrderSide
from ditto_kernel.enums import OrderSide
assert OrderSide.BUY == 'buy'
assert OrderSide.SELL == 'sell'
# Core 的向后兼容别名
from ditto_core.accounting.order_book import OrderDirection
assert OrderDirection is OrderSide
print('Core OrderDirection backward compat: OK')
"
```

Expected: `Core OrderDirection backward compat: OK`

**Step 6: 验证 Port 消费者**

```bash
pixi run -e dev python -c "
from ditto_kernel.enums import AssetClass
assert len(AssetClass) == 6
assert AssetClass.FUTURE == 'future'
print('Port AssetClass (6 members from kernel): OK')
"
```

Expected: `Port AssetClass (6 members from kernel): OK`

---

## 依赖图

```
Task 1 (kernel 骨架)
  │
  └── Task 2 (kernel 类型定义)
        │
        ├── Task 3 (DataHub 迁移) ──┐
        ├── Task 4 (Core 迁移) ─────┤
        └── Task 5 (Port 迁移) ─────┤
                                    │
                              Task 7 (DataHub __init__ 更新)
                                    │
                              Task 6 (Import Linter)
                                    │
                              Task 8 (全量验证)
```

> Task 3、4、5 可并行执行（彼此独立）。
> Task 6 依赖 Task 3 和 Task 4 完成（需要 Core↔DataHub 双向禁止规则生效）。
> Task 7 独立于 Task 6，可在 Task 3 之后执行。

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| Core 仍有对 `datahub.models` 的导入导致 arch-check 失败 | Task 6 Step 6 的 grep 检查；如有发现立即清理 |
| Port 测试中 AssetClass 值从 3 扩展到 6 导致断言失败 | Task 5 Step 4 验证；如有失败需更新测试中的硬编码枚举值 |
| `InstrumentIdRange.get_range()` 依赖 `AssetClass`，迁移后 import 路径变化 | Task 3 Step 5 已处理：`common.py` 直接从 kernel 导入 `AssetClass` |
| `normalization.py` 中的 `Exchange` 与 kernel `Exchange` 同名但值不同 | 两者在不同模块，通过导入路径区分。`normalization.Exchange` 仍在 `ditto_datahub.sources` 内部使用 |

---

## 后续演进（不在本次范围）

1. **instrument-id-semantics-unification 计划更新** — Phase 0 中 `InstrumentId` 归属从 `ditto_datahub.models.kernel` 改为 `ditto_kernel.identity`
2. **Port 层业务逻辑下沉到 Core** — `StrategyInputAssembler` 默认信号、`DerivedPublicationFacade` shadow diff、`CS amplification` 等 5 个模块
3. **`InstrumentIdRange` 重新评估** — 当 instrument-id 统一计划让 Core 也使用 IDRange 时，再评估是否迁入 kernel
4. **`OrderDirection` 别名清理** — 后续逐步将 Core 源码中的 `OrderDirection` 使用点改为 `OrderSide`，移除 `as OrderDirection` 别名
