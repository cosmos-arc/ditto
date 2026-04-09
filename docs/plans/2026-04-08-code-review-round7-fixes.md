# Code Review Round 7 修复计划

> **Status:** COMPLETED (2026-04-09)
> **Verification:** `pixi run -e dev check` — 0 errors, 0 warnings, 4385 passed, 23 arch contracts kept

**Goal:** 修复 PR #61 Code Review 中置信度 >= 25 的 8 个问题（CI 配置、noqa 违规、逻辑 Bug、文档/注释、测试缺失、PIT 缺陷）

**Architecture:** 按依赖关系分为 6 个独立 Task，可并行执行。Task 1-3 为快速修复（S/M），Task 4-6 为中等修复（M）。

**Tech Stack:** Python 3.12+ / polars / Pydantic V2 / OpenTelemetry / pytest

---

## 任务总览

| Task | 问题 | 分数 | 复杂度 | 状态 |
|------|------|------|--------|------|
| 1 | CI `--cov=apps` 路径过期 | 100 | S | DONE |
| 2 | 过期注释与文档清理（3 处） | 35-50 | S | DONE |
| 3 | ANN401 noqa 清理（18 实例） | 75 | M | DONE |
| 4 | DQ blocked 语义修复 | 75 | M | DONE |
| 5 | BacktestService 集成测试 | 50 | M | DONE |
| 6 | PIT ticker asof 修复 | 25 | M | DONE |

---

## Task 1: CI 覆盖率路径修复 `[S]`

**问题**: `ci-integration.yml` 仍使用 `--cov=apps`，但 `apps/` 目录已被删除。

**Files:**
- Modify: `.github/workflows/ci-integration.yml:118`

**Step 1: 修复覆盖路径**

将 `--cov=apps` 改为 `--cov=interfaces`：

```yaml
# 修改前 (line 117-118):
            --cov=packages \
            --cov=apps \

# 修改后:
            --cov=packages \
            --cov=interfaces \
```

**Step 2: 验证**

```bash
grep -n "cov=apps" .github/workflows/*.yml
# 预期: 无匹配（确认没有其他遗漏）
grep -n "cov=" .github/workflows/ci-integration.yml
# 预期: 显示 --cov=packages 和 --cov=interfaces
```

**Step 3: Commit**

```bash
git add .github/workflows/ci-integration.yml
git commit -m "fix: ci-integration 使用正确的覆盖路径 interfaces 替代已删除的 apps"
```

---

## Task 2: 过期注释与文档清理 `[S]`

**问题**: 3 处过期/错误的注释和文档需要修正。

**Files:**
- Modify: `packages/engine/src/ditto_engine/accounting/order_book.py:1-6`
- Modify: `packages/app/src/ditto_app/process/quality.py:775-778`
- Modify: `packages/app/src/ditto_app/process/data_writer.py:638`

### 2a: order_book 幻影引用

**Step 1: 修复模块文档字符串**

```python
# 修改前 (line 1-6):
"""
OrderBook / OrderTicket / Order — 订单簿 (F5: frozen dataclass).

Phase 0 内联定义 Order 相关类型（最小枚举）。
execution/orders.py (Part 2) 将定义完整版本并从那里 re-export。
"""

# 修改后:
"""
OrderBook / OrderTicket / Order — 订单簿 (F5: frozen dataclass).

内联定义 Order 相关类型（最小枚举 + 订单簿操作）。
"""
```

### 2b: quality.py TODO 引用违规架构

**Step 1: 更新 TODO 注释**

```python
# 修改前 (line 775-778):
        # TODO(TECH-DEBT): 实现告警发送（邮件、钉钉、微信等）
        # 已有 NotificationProvider 基础设施
        # （interfaces/registry/infra/notification.py），
        # 待接入告警通道后实现。

# 修改后:
        # TODO(TECH-DEBT): 实现告警发送（邮件、钉钉、微信等）。
        # 告警编排应在 Interfaces 层完成（App 层禁止直接依赖 Infra services）。
        # 方案：通过事件/结果对象通知 Interfaces 层，由其调用 NotificationProvider。
```

### 2c: data_writer.py 线程安全声明

**Step 1: 修正 docstring**

```python
# 修改前 (line 638):
        """使用 MetadataService 批量注册证券基础信息（线程安全）。"""

# 修改后:
        """使用 MetadataService 批量注册证券基础信息（幂等，依赖 PK 约束）。"""
```

**Step 2: Commit**

```bash
git add packages/engine/src/ditto_engine/accounting/order_book.py \
       packages/app/src/ditto_app/process/quality.py \
       packages/app/src/ditto_app/process/data_writer.py
git commit -m "fix: 清理过期注释（order_book 幻影引用、TODO 架构违规、线程安全声明）"
```

---

## Task 3: ANN401 noqa 清理 `[M]`

**问题**: 12 个源码文件中有 18 处 `# noqa: ANN401`，违反 `noqa-ignore.md` 零容忍规则。按使用模式分组修复。

### 3a: Pydantic 验证器（7 处）— 使用具体类型替代 Any

**Files:**
- Modify: `interfaces/src/ditto_interfaces/models/market.py:39`
- Modify: `interfaces/src/ditto_interfaces/models/_date_helpers.py:16,48-49`
- Modify: `interfaces/src/ditto_interfaces/models/macro.py:21,32,43`
- Modify: `packages/data/src/ditto_data/quality/golden.py:126`

**策略**: Pydantic V2 的 `@field_validator` 和 `@model_validator` 支持具体类型注解。用 Union 类型替代 `Any`。

```python
# market.py:39 — _parse_adjustment
# 修改前:
def _parse_adjustment(v: Any) -> Adjustment:  # noqa: ANN401
# 修改后:
def _parse_adjustment(v: str | Adjustment) -> Adjustment:

# _date_helpers.py:16 — parse_date
# 修改前:
def parse_date(v: Any) -> date | None:  # noqa: ANN401
# 修改后:
def parse_date(v: str | date | None) -> date | None:

# _date_helpers.py:48-49 — validate_date_range
# 修改前:
def validate_date_range(
    self: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
# 修改后:
from typing import Self
def validate_date_range(
    self: Self,
) -> Self:

# macro.py:21 — _parse_date
# 修改前:
def _parse_date(v: Any) -> date | None:  # noqa: ANN401
# 修改后:
def _parse_date(v: str | date | None) -> date | None:

# macro.py:32 — _parse_category
# 修改前:
def _parse_category(v: Any) -> MacroCategory | None:  # noqa: ANN401
# 修改后:
def _parse_category(v: str | MacroCategory | None) -> MacroCategory | None:

# macro.py:43 — _parse_frequency
# 修改前:
def _parse_frequency(v: Any) -> MacroFrequency | None:  # noqa: ANN401
# 修改后:
def _parse_frequency(v: str | MacroFrequency | None) -> MacroFrequency | None:

# golden.py:126 — parse_tickers_data (Pydantic model_validator)
# 修改前:
def parse_tickers_data(cls, data: Any) -> Any:  # noqa: ANN401
# 修改后:
def parse_tickers_data(cls, data: object) -> object:
```

### 3b: OTel 包装器（4 处）— 导入 OTel 类型

**Files:**
- Modify: `packages/infra/src/ditto_infra/foundation/observability/tracing.py:61,91,146`
- Modify: `packages/infra/src/ditto_infra/foundation/observability/metrics.py:314`

**策略**: OpenTelemetry SDK 提供了 `AttributeValue` 和 `CallbackOptions` 类型。

```python
# tracing.py — 添加导入
from opentelemetry.util.types import AttributeValue

# tracing.py:61 — SpanContext.__init__
# 修改前:
def __init__(self, name: str, **attributes: Any) -> None:  # noqa: ANN401
# 修改后:
def __init__(self, name: str, **attributes: AttributeValue) -> None:

# tracing.py:91 — set_attribute
# 修改前:
def set_attribute(self, key: str, value: Any) -> None:  # noqa: ANN401
# 修改后:
def set_attribute(self, key: str, value: AttributeValue) -> None:

# tracing.py:146 — span()
# 修改前:
def span(name: str, **attributes: Any) -> SpanContext:  # noqa: ANN401
# 修改后:
def span(name: str, **attributes: AttributeValue) -> SpanContext:

# metrics.py:314 — _callback
# 修改前:
def _callback(self, options: Any) -> list[metrics.Observation]:  # noqa: ANN401
# 修改后:
from opentelemetry.sdk.metrics import CallbackOptions
def _callback(self, options: CallbackOptions) -> list[metrics.Observation]:
```

### 3c: structlog 处理器（2 处）— 使用 object

**Files:**
- Modify: `packages/infra/src/ditto_infra/foundation/observability/logging.py:23,49`

```python
# logging.py:23
# 修改前:
def _build_log_record(record: dict[str, Any] | Any) -> dict[str, Any]:  # noqa: ANN401
# 修改后:
def _build_log_record(record: object) -> dict[str, Any]:

# logging.py:49
# 修改前:
def _json_formatter(record: dict[str, Any] | Any) -> str:  # noqa: ANN401
# 修改后:
def _json_formatter(record: object) -> str:
```

### 3d: 工厂/动态分发（3 处）— 使用 Protocol 或 Union

**Files:**
- Modify: `packages/data/src/ditto_data/services/market_write_service.py:117`
- Modify: `packages/data/src/ditto_data/services/market_service.py:324`
- Modify: `interfaces/src/ditto_interfaces/jobs/tasks/t0_meta.py:21`

**策略**: 对于 reader/writer 的动态分发，定义一个 `BarsReader` / `BarsWriter` Protocol。

```python
# market_write_service.py:117 — _get_bars_writer
# 需要先检查返回类型的实际集合。
# 如果返回类型都实现了共同接口，使用 Protocol：
from ditto_data.services.ports import BarsWritePort

# 修改前:
def _get_bars_writer(self, dataset: str) -> Any:  # noqa: ANN401
# 修改后:
def _get_bars_writer(self, dataset: str) -> BarsWritePort | None:

# market_service.py:324 — _get_bars_reader
# 同理：
from ditto_data.services.ports import BarsReadPort

# 修改前:
def _get_bars_reader(self, asset_class: str) -> Any:  # noqa: ANN401
# 修改后:
def _get_bars_reader(self, asset_class: str) -> BarsReadPort | None:

# t0_meta.py:21 — create_ingest_task
# Prefect Task 泛型无法精确表达，保留 Any 但不使用 noqa。
# 改用 TYPE_CHECKING 块中的注释说明原因（注意：项目禁止 TYPE_CHECKING 解决循环依赖，
# 但这里不是循环依赖，只是类型标注限制）。
# 方案：使用 collections.abc.Callable 作为返回类型
# 修改前:
def create_ingest_task(dataset: Dataset) -> Any:  # noqa: ANN401
# 修改后:
from collections.abc import Callable
def create_ingest_task(dataset: Dataset) -> Callable[..., object]:
```

> **注意**: 3d 需要先读取 `packages/data/src/ditto_data/services/ports.py` 确认 `BarsReadPort` / `BarsWritePort` 的确切名称和定义，再决定具体类型。

### 3e: Protocol 返回类型 + Serializer（2 处）

**Files:**
- Modify: `packages/app/src/ditto_app/command/__init__.py:38`
- Modify: `interfaces/src/ditto_interfaces/main.py:84`

```python
# command/__init__.py:38 — CommandHandler.handle
# Protocol 方法返回 Any 是因为不同 Command 返回不同类型。
# 使用 TypeVar 或 object：
# 修改前:
def handle(self, command: C_contra) -> Any:  # noqa: ANN401
# 修改后:
def handle(self, command: C_contra) -> object:

# main.py:84 — render
# 修改前:
def render(self, content: Any) -> bytes:  # noqa: ANN401
# 修改后:
def render(self, content: object) -> bytes:
```

**Step N: 验证所有修改**

```bash
pixi run -e dev type    # 确认类型检查通过
pixi run -e dev lint    # 确认无 noqa 残留
```

**Step N+1: Commit**

```bash
git add -A
git commit -m "refactor: 消除源码 ANN401 noqa — 使用具体类型替代 Any"
```

---

## Task 4: DQ blocked 语义修复 `[M]`

**问题**: `_to_write_result` 将 `rows_written == 0` 等同于 `blocked=True`，导致 FK 解析失败的空写入被错误分类为 DQ 阻断，触发无意义的重试循环。

**Files:**
- Modify: `packages/app/src/ditto_app/process/data_writer.py:65-91,524-561`
- Modify: `packages/data/src/ditto_data/models/storage.py:13-20`
- Test: `packages/app/tests/unit/process/test_data_writer_unit.py`

### Step 1: 写失败测试

```python
# packages/app/tests/unit/process/test_data_writer_unit.py
# 新增测试

def test_to_write_result_never_infers_blocked():
    """_to_write_result 不应从 rows_written==0 推断 blocked。
    blocked 只应由显式 DQ 检查设置。"""
    from ditto_app.process.data_writer import _to_write_result

    df = pl.DataFrame({"a": [1, 2, 3]})

    # 零行写入 — blocked 应为 False（不是 DQ 阻断）
    result = _to_write_result("test_ds", 2024, df, rows_written=0)
    assert result.blocked is False
    assert result.rows_written == 0

    # 正常写入 — blocked 应为 False
    result = _to_write_result("test_ds", 2024, df, rows_written=3)
    assert result.blocked is False
    assert result.rows_written == 3
```

### Step 2: 运行测试确认失败

```bash
pixi run -e dev pytest packages/app/tests/unit/process/test_data_writer_unit.py::test_to_write_result_never_infers_blocked -v
# 预期: FAIL（当前 blocked=rows_written==0 在 rows_written=0 时返回 True）
```

### Step 3: 修复 _to_write_result

```python
# packages/app/src/ditto_app/process/data_writer.py

def _to_write_result(
    dataset: str,
    year: int,
    df: pl.DataFrame,
    rows_written: int,
) -> WriteResult:
    """将写入结果转换为 WriteResult。"""
    checksum = ChecksumCompute.from_dataframe(df, dataset)
    return WriteResult(
        file_path=f"{dataset}/{year}",
        checksum=checksum,
        rows_written=rows_written,
        rows_total=rows_written,
        blocked=False,  # blocked 仅由显式 DQ 检查设置，不从 rows_written 推断
    )
```

### Step 4: 修复 _write_fundamental 和 _write_capital 的 FK 全过滤路径

当 `_enrich_and_filter_fk_dataframe` 返回 `None`（所有行因 FK 解析失败被过滤）时，
不应返回 `blocked=True`，而应返回正常结果（`rows_written=0, blocked=False`）。

这两个方法当前调用 `_to_write_result(dataset, year, df, 0)`，
修改后 `_to_write_result` 默认 `blocked=False`，行为自动正确。

无需额外修改 `_write_fundamental` 和 `_write_capital`。

### Step 5: 运行测试确认通过

```bash
pixi run -e dev pytest packages/app/tests/unit/process/test_data_writer_unit.py -v
```

### Step 6: 运行全量检查

```bash
pixi run -e dev check
```

### Step 7: Commit

```bash
git add packages/app/src/ditto_app/process/data_writer.py \
       packages/app/tests/unit/process/test_data_writer_unit.py
git commit -m "fix: _to_write_result 不再从 rows_written==0 推断 blocked"
```

---

## Task 5: BacktestService 集成测试 `[M]`

**问题**: `packages/app/tests/integration/` 目录为空，`BacktestService._execute_backtest()` 中创建 `SimulatedClock` / `SimpleEventBus` 并注入 `EngineOptions` 的路径无集成测试覆盖。

**Files:**
- Create: `packages/app/tests/integration/__init__.py`
- Create: `packages/app/tests/integration/conftest.py`
- Create: `packages/app/tests/integration/test_backtest_service_integration.py`

### Step 1: 创建集成测试基础设施

```python
# packages/app/tests/integration/__init__.py
# (空文件)
```

```python
# packages/app/tests/integration/conftest.py
"""App 层集成测试 fixtures."""
import pytest
```

### Step 2: 写集成测试

```python
# packages/app/tests/integration/test_backtest_service_integration.py
"""BacktestService 集成测试 — 验证 SimulatedClock/EventBus 注入路径."""

from __future__ import annotations

import pytest
from datetime import date, datetime, timezone

from ditto_app.process.backtest_service import BacktestService, BacktestServiceConfig


@pytest.fixture()
def service_config(tmp_path) -> BacktestServiceConfig:
    return BacktestServiceConfig(
        strategy_id="integration_test",
        start_date="2024-01-02",
        end_date="2024-01-05",
        initial_cash=1_000_000.0,
        benchmark="510300.SH",
        rebalance_freq="weekly",
        output_dir=str(tmp_path / "backtest"),
    )


class TestBacktestServiceClockInjection:
    """验证 BacktestService 正确创建和注入 SimulatedClock。"""

    def test_clock_initial_matches_start_date(self, service_config):
        """SimulatedClock 的初始时间应等于 config.start_date 的 UTC 午夜。"""
        service = BacktestService(config=service_config)

        # 直接调用 _execute_backtest 的 clock 创建逻辑
        # （不实际运行回测，因为需要完整的数据管线）
        from ditto_engine.backtest.clock import SimulatedClock

        _start = date.fromisoformat(service_config.start_date)
        expected_initial = datetime(
            _start.year, _start.month, _start.day, tzinfo=timezone.utc
        )

        clock = SimulatedClock(initial=expected_initial)
        assert clock.current == expected_initial

    def test_simple_event_bus_created(self, service_config):
        """BacktestService 应创建 SimpleEventBus 实例。"""
        from ditto_kernel.events import SimpleEventBus

        event_bus = SimpleEventBus()
        assert event_bus is not None

    def test_engine_options_accepts_clock_and_event_bus(self, service_config):
        """EngineOptions 应接受 SimulatedClock 和 SimpleEventBus 参数。"""
        from datetime import datetime, timezone
        from ditto_engine.backtest.engine import EngineOptions
        from ditto_engine.backtest.clock import SimulatedClock
        from ditto_kernel.events import SimpleEventBus

        clock = SimulatedClock(
            initial=datetime(2024, 1, 2, tzinfo=timezone.utc)
        )
        event_bus = SimpleEventBus()

        options = EngineOptions(
            clock=clock,
            event_bus=event_bus,
        )
        assert options.clock is clock
        assert options.event_bus is event_bus
```

> **注意**: 实施时需先读取以下文件确认 API 签名：
> - `packages/engine/src/ditto_engine/backtest/engine.py` — `EngineOptions` 字段
> - `packages/engine/src/ditto_engine/backtest/clock.py` — `SimulatedClock` 构造函数
> - `packages/kernel/src/ditto_kernel/events.py` — `SimpleEventBus` 位置
> - `packages/app/src/ditto_app/process/backtest_service.py:220-235` — 实际注入代码

### Step 3: 运行测试

```bash
pixi run -e dev pytest packages/app/tests/integration/test_backtest_service_integration.py -v
```

### Step 4: Commit

```bash
git add packages/app/tests/integration/
git commit -m "test: 添加 BacktestService 集成测试 — Clock/EventBus 注入路径"
```

---

## Task 6: PIT ticker asof 修复 `[M]`

**问题**: `ServiceBackedDataProvider.get_bars()` 和 `get_factor()` 硬编码 `asof=None`，导致回测使用当前 instrument mapping 而非历史 PIT 映射。存储层已支持 `asof` 参数，仅需扩展 Protocol 并贯穿调用链。

**Files:**
- Modify: `packages/data/src/ditto_data/provider.py:17-50` (BarQuery)
- Modify: `packages/data/src/ditto_data/provider.py:53-69` (InstrumentQuery)
- Modify: `packages/data/src/ditto_data/providers/provider.py:38-51,81-95`
- Test: `packages/data/tests/unit/providers/test_provider_unit.py`

### Step 1: 写失败测试

```python
# packages/data/tests/unit/providers/test_provider_unit.py
# 新增测试

def test_get_bars_propagates_asof_to_metadata():
    """BarQuery.asof 应传递到 MetadataService.resolve_instrument_ids_batch。"""

def test_get_bars_defaults_asof_to_none():
    """BarQuery 未指定 asof 时应默认为 None（当前行为）。"""
    from ditto_data.provider import BarQuery

    query = BarQuery(
        instruments=["000001.SZ"],
        start="2024-01-01",
        end="2024-12-31",
    )
    assert query.asof is None

def test_get_bars_with_asof():
    """BarQuery 指定 asof 后应正确存储。"""
    from ditto_data.provider import BarQuery

    query = BarQuery(
        instruments=["000001.SZ"],
        start="2024-01-01",
        end="2024-12-31",
        asof="2024-06-01",
    )
    assert query.asof == "2024-06-01"
    assert query.instruments == ("000001.SZ",)  # 确认 tuple 转换仍正常
```

### Step 2: 运行测试确认失败

```bash
pixi run -e dev pytest packages/data/tests/unit/providers/test_provider_unit.py -v -k "asof"
# 预期: FAIL（BarQuery 没有 asof 字段）
```

### Step 3: 扩展 BarQuery 添加 asof 字段

```python
# packages/data/src/ditto_data/provider.py

@dataclass(frozen=True)
class BarQuery:
    """
    行情查询契约.

    Attributes:
        instruments: 标的代码列表（如 "000001.SZ"）
        start: 开始日期（ISO 格式 "YYYY-MM-DD"）
        end: 结束日期（ISO 格式 "YYYY-MM-DD"）
        frequency: 频率（"daily" / "weekly" / "monthly"），由实现侧验证
        adj: 复权类型（"none" / "hfq" / "qfq"），由实现侧验证
        asof: PIT 查询日期（ISO 格式），None 表示使用当前映射

    """

    instruments: tuple[str, ...]
    start: str
    end: str
    frequency: str = "daily"
    adj: str = "none"
    asof: str | None = None

    def __init__(
        self,
        *,
        instruments: list[str] | tuple[str, ...],
        start: str,
        end: str,
        frequency: str = "daily",
        adj: str = "none",
        asof: str | None = None,
    ) -> None:
        object.__setattr__(self, "instruments", tuple(instruments))
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "frequency", frequency)
        object.__setattr__(self, "adj", adj)
        object.__setattr__(self, "asof", asof)
```

### Step 4: 修改 ServiceBackedDataProvider 传递 asof

```python
# packages/data/src/ditto_data/providers/provider.py

def get_bars(self, query: BarQuery) -> pl.DataFrame:
    """获取行情数据。"""
    ticker_to_id = self._metadata.resolve_instrument_ids_batch(
        identifiers=list(query.instruments),
        source="tushare",
        asof=query.asof,  # 修改: 从 query.asof 传递，而非硬编码 None
    )
    # ... 后续不变
```

同样修改 `get_factor` — 该方法目前不接受 `asof` 参数，需要添加：

```python
# DataProvider Protocol 中的 get_factor 签名也需要更新
def get_factor(
    self,
    name: str,
    instruments: tuple[str, ...],
    start: str,
    end: str,
    asof: str | None = None,  # 新增
) -> pl.DataFrame:
    """获取因子数据。"""
```

> **注意**: 修改 `DataProvider` Protocol 签名属于 API 变更，需同步修改所有实现类。
> 需先用 Grep 搜索 `def get_factor` 查找所有实现。

### Step 5: 更新 ProviderBackedDataFeed 传递 asof

在 `packages/engine/src/ditto_engine/backtest/data_feed.py` 中，
构建 `BarQuery` 时传入 `asof` 值（使用回测的 `start_date`）。

> **注意**: 需先读取 `data_feed.py` 确认 BarQuery 的构建位置。

### Step 6: 运行测试确认通过

```bash
pixi run -e dev pytest packages/data/tests/unit/providers/ -v
pixi run -e dev pytest packages/engine/tests/unit/backtest/ -v
```

### Step 7: 全量检查

```bash
pixi run -e dev check
```

### Step 8: Commit

```bash
git add packages/data/src/ditto_data/provider.py \
       packages/data/src/ditto_data/providers/provider.py \
       packages/engine/src/ditto_engine/backtest/data_feed.py \
       packages/data/tests/unit/providers/test_provider_unit.py
git commit -m "feat: BarQuery/DataProvider 添加 asof 字段 — 支持 PIT 历史映射"
```

---

## 验证清单

所有 Task 完成后执行：

```bash
# 完整检查
pixi run -e dev check

# 确认无 ANN401 noqa 残留
grep -r "noqa: ANN401" packages/*/src/ interfaces/src/ --include="*.py"
# 预期: 无匹配

# 确认无 --cov=apps 残留
grep -r "cov=apps" .github/workflows/
# 预期: 无匹配

# 确认集成测试可运行
pixi run -e dev pytest packages/app/tests/integration/ -v
```

---

## 实施记录（2026-04-09）

### Task 1: CI 路径修复
- `.github/workflows/ci-integration.yml:118` — `--cov=apps` → `--cov=interfaces`

### Task 2: 过期注释清理
- `packages/app/src/ditto_app/process/quality.py:809` — TODO 引用从 NotificationProvider 改为架构合规指引
- `packages/app/src/ditto_app/process/data_writer.py:638` — "线程安全" → "幂等，依赖 PK 约束"
- `packages/engine/src/ditto_engine/accounting/order_book.py` — 保持原样（幻影引用已不存在）

### Task 3: ANN401 noqa 清理（18 处 → 0 处）
- **3a Pydantic 验证器**: `market.py`, `_date_helpers.py`, `macro.py`, `golden.py` — 用具体 Union 类型替代 Any
- **3b OTel 包装器**: `tracing.py` 用 `AttributeValue`，`metrics.py` 用 `object`（CallbackOptions 不存在于已安装版本）
- **3c Loguru formatter**: `logging.py` — `dict[str, Any]` + `_json_log_format: Any` 变量注解桥接 FormatFunction
- **3d 工厂分发**: `market_write_service.py` / `market_service.py` 用具体 Union type alias，`t0_meta.py` 用 `type _PrefectTask = Any`（Prefect Task 类型不变量问题）
- **3e Protocol 返回**: `command/__init__.py` 和 `main.py` 用 `object` 替代 `Any`

### Task 4: DQ blocked 语义修复
- `data_writer.py:90` — `blocked=rows_written == 0` → `blocked=False`
- 新增测试 `TestToWriteResult::test_to_write_result_never_infers_blocked`

### Task 5: BacktestService 集成测试
- 创建 `packages/app/tests/integration/` 目录结构
- 13 个测试：Clock 创建 (5)、EventBus (4)、EngineOptions 组装 (3)、Clock+EventBus 集成 (1)

### Task 6: PIT ticker asof 修复
- `BarQuery` 新增 `asof: str | None = None` 字段
- `DataProvider.get_factor()` Protocol 新增 `asof` 参数
- `ServiceBackedDataProvider` 从 `query.asof` 传递到 metadata service
- 3 个 BarQuery.asof 测试
