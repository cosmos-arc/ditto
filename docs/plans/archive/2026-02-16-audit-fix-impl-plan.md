# 架构审计修复实施计划

> 基于审计分析：[2026-02-16-audit-findings-analysis.md](./2026-02-16-audit-findings-analysis.md)
> 生成日期：2026-02-16
> 状态：待实施

---

## Phase 1: 基础修复（无依赖）

### PR-1: DQSeverity 下沉到 Core

**覆盖 ID**: ARCH-001/002
**Effort**: S（约 1-2 小时）
**优先级**: High

#### 改动范围

```
packages/core/src/ditto_core/quality/
  + severity.py          # 新增：DQSeverity 定义
  ~ __init__.py          # 导出 DQSeverity
  ~ spec.py              # 删除 from ditto_infra.foundation import DQSeverity
  ~ engine.py            # 删除 from ditto_infra.foundation import DQSeverity
  ~ checkers/cross_source.py  # 删除 from ditto_infra.foundation import DQSeverity

packages/infra/src/ditto_infra/foundation/
  - quality/             # 删除整个目录
  ~ __init__.py          # 删除 DQSeverity 导出

packages/data/src/ditto_data/models/
  ~ common.py            # 删除 DQSeverity 定义和导出

apps/port/tests/unit/services/ingestion/quality/
  ~ conftest.py          # 改为 from ditto_core.quality import DQSeverity
  ~ test_l3_batch_unit.py  # 改为 from ditto_core.quality import DQSeverity

packages/core/tests/unit/quality/
  ~ test_cross_source_checker.py  # 改为 from ditto_core.quality import DQSeverity
```

#### 实施步骤

**Step 1: 在 Core 创建 DQSeverity**

```python
# packages/core/src/ditto_core/quality/severity.py
"""DQ severity level enumeration."""

from enum import Enum


class DQSeverity(Enum):
    """
    DQ severity level.

    Represents the severity level of a data quality issue.
    Used across all layers for consistent issue classification.
    """

    ERROR = "error"
    WARNING = "warning"
    ALERT = "alert"
```

**Step 2: 更新 Core 导出**

```python
# packages/core/src/ditto_core/quality/__init__.py
from ditto_core.quality.severity import DQSeverity
from ditto_core.quality.spec import (
    BaseRule,
    ColumnRule,
    # ... 其他导出
)

__all__ = [
    "DQSeverity",
    # ... 其他
]
```

**Step 3: 修正导入路径（6 处）**

```python
# Before
from ditto_infra.foundation import DQSeverity

# After
from ditto_core.quality import DQSeverity
```

**Step 4: 删除 Infra quality 模块**

```bash
rm -rf packages/infra/src/ditto_infra/foundation/quality/
```

更新 `packages/infra/src/ditto_infra/foundation/__init__.py`，删除 DQSeverity 相关行。

**Step 5: 删除 DataHub 重复定义**

从 `packages/data/src/ditto_data/models/common.py` 删除 DQSeverity 类定义和 `__all__` 中的导出。

#### 验收标准

- [ ] `pixi run -e dev check` 通过
- [ ] `rg "from ditto_infra.foundation import DQSeverity" --glob "*.py"` 无结果
- [ ] `rg "class DQSeverity" --glob "*.py"` 只有一处（Core）

---

### PR-2: 启动初始化 fail-fast

**覆盖 ID**: ARCH-003
**Effort**: S（约 1-2 小时）
**优先级**: Blocker

#### 改动范围

```
packages/infra/src/ditto_infra/foundation/config/
  + errors.py            # 新增：ConfigInitError
  ~ initializer.py       # 增加 fail-fast 逻辑
  ~ __init__.py          # 导出 ConfigInitError

apps/port/src/ditto_port/
  ~ main.py              # 捕获 ConfigInitError 并退出

packages/infra/tests/unit/config/
  + test_initializer_fail_fast.py  # 新增测试
```

#### 实施步骤

**Step 1: 定义 ConfigInitError**

```python
# packages/infra/src/ditto_infra/foundation/config/errors.py
"""Configuration initialization errors."""

from __future__ import annotations


class ConfigInitError(Exception):
    """Raised when configuration initialization fails during startup."""

    def __init__(self, failed_providers: list[str], details: dict[str, str]) -> None:
        self.failed_providers = failed_providers
        self.details = details
        message = f"Startup initialization failed for: {', '.join(failed_providers)}"
        super().__init__(message)
```

**Step 2: 修改 initializer.py**

```python
# packages/infra/src/ditto_infra/foundation/config/initializer.py

from ditto_infra.foundation.config.errors import ConfigInitError

class ConfigInitCoordinator:
    def initialize(
        self,
        scope: InitScope,
        data_root: Path,
        force: bool = False,
        fail_fast: bool = True,  # 新增参数
    ) -> dict[str, InitResult]:
        """按作用域执行初始化。"""
        results: dict[str, InitResult] = {}
        # ... 现有逻辑 ...

        # 新增：STARTUP 场景 fail-fast
        if fail_fast and scope == InitScope.STARTUP:
            failed = {name: r.message for name, r in results.items() if not r.success}
            if failed:
                raise ConfigInitError(list(failed.keys()), failed)

        return results
```

**Step 3: 更新 main.py 调用**

```python
# apps/port/src/ditto_port/main.py

from ditto_infra.foundation.config import ConfigInitError

# 在 startup 事件中
try:
    coordinator.initialize(scope=InitScope.STARTUP, data_root=settings.data_root)
except ConfigInitError as e:
    logger.error("Startup initialization failed", failed_providers=e.failed_providers)
    raise SystemExit(1)
```

**Step 4: 添加测试**

```python
# packages/infra/tests/unit/config/test_initializer_fail_fast.py

def test_startup_fail_fast_on_provider_failure():
    """STARTUP 场景下 provider 失败应抛出 ConfigInitError"""
    coordinator = ConfigInitCoordinator()
    coordinator.register(FailingProvider())

    with pytest.raises(ConfigInitError) as exc_info:
        coordinator.initialize(scope=InitScope.STARTUP, data_root=Path("/tmp"))

    assert "failing_provider" in exc_info.value.failed_providers


def test_manual_scope_does_not_fail_fast():
    """MANUAL 场景下不应 fail-fast"""
    coordinator = ConfigInitCoordinator()
    coordinator.register(FailingProvider())

    results = coordinator.initialize(scope=InitScope.MANUAL, data_root=Path("/tmp"))

    assert results["failing_provider"].success is False
```

#### 验收标准

- [ ] STARTUP 场景 provider 失败时抛出 ConfigInitError
- [ ] MANUAL/ALWAYS 场景保持原有行为（记录但不抛出）
- [ ] 测试覆盖新增逻辑
- [ ] `pixi run -e dev check` 通过

---

### PR-4: 删除重复的 detect_asset_class

**覆盖 ID**: ENG-002
**Effort**: S（约 30 分钟）
**优先级**: Medium

#### 改动范围

```
packages/data/src/ditto_data/services/
  ~ market_service.py    # 删除 _detect_asset_class_from_instrument_ids

packages/data/tests/unit/services/
  ~ test_market_service_unit.py  # 如有相关测试，更新导入
```

#### 实施步骤

**Step 1: 查找所有调用点**

```bash
rg "_detect_asset_class_from_instrument_ids" packages/data/
```

**Step 2: 替换为 InstrumentIdRange.detect_asset_class**

```python
# Before (in market_service.py)
result = self._detect_asset_class_from_instrument_ids(instrument_ids)

# After
from ditto_data.models.common import InstrumentIdRange
result = InstrumentIdRange.detect_asset_class(instrument_ids)
```

**Step 3: 删除私有方法**

```python
# 删除整个 _detect_asset_class_from_instrument_ids 方法（约 30 行）
```

#### 验收标准

- [ ] `rg "_detect_asset_class_from_instrument_ids" --glob "*.py"` 无结果
- [ ] `pixi run -e dev check` 通过
- [ ] 相关测试仍通过

---

## Phase 2: 架构重构

### PR-3: CLIExecutor 依赖链重构 + 消除 os.environ 副作用

**覆盖 ID**: ARCH-004 + ENG-004
**Effort**: M（约 4-6 小时）
**优先级**: Medium

#### 目标

```
Before:
CLIExecutor(metadata, market, fundamental, capital, macro, source, log, source_name)
  └─> 透传 6 个服务给 create_coordinator

After:
CLIExecutor(coordinator, backfill_manager)
  └─> 直接使用，不关心内部依赖
```

#### 改动范围

```
apps/port/src/ditto_port/cli/
  ~ executor.py          # 简化为只接收 coordinator + backfill_manager
  ~ context.py           # 提供 create_cli_executor 上下文管理器
  ~ main.py              # 删除 os.environ["DITTO_DATA_ROOT"] 设置

apps/port/src/ditto_port/registry/
  ~ contexts/ingestion.py  # 新增 create_ingestion_bundle_for_cli
  ~ infra/config.py      # data_root 通过显式参数传递

apps/port/tests/unit/cli/
  ~ test_executor_unit.py  # 更新测试
```

#### 实施步骤

**Step 1: 简化 CLIExecutor**

```python
# apps/port/src/ditto_port/cli/executor.py

class CLIExecutor:
    """CLI 本地执行器，封装 IngestionCoordinator 和 BackfillManager."""

    def __init__(
        self,
        coordinator: IngestionCoordinator,
        backfill_manager: BackfillManager,
    ) -> None:
        self._coordinator = coordinator
        self._backfill_manager = backfill_manager

    @property
    def coordinator(self) -> IngestionCoordinator:
        return self._coordinator

    @property
    def backfill_manager(self) -> BackfillManager:
        return self._backfill_manager

    # ingest_daily, backfill_range 方法保持不变
```

**Step 2: 创建 CLI 上下文管理器**

```python
# apps/port/src/ditto_port/cli/context.py

from contextlib import contextmanager
from typing import Iterator

from ditto_port.services.ingestion import create_coordinator_with_bundle
from ditto_port.services.ingestion.backfill import BackfillManager


@contextmanager
def create_cli_executor(
    source_name: str | Source = Source.TUSHARE,
    data_root: Path | None = None,  # 显式参数，不再用 os.environ
) -> Iterator[CLIExecutor]:
    """创建 CLIExecutor，由 DI 容器组装依赖。"""
    with create_ingestion_bundle(source_name, data_root) as bundle:
        coordinator = bundle.coordinator
        backfill_manager = BackfillManager(
            coordinator=coordinator,
            metadata_service=bundle.metadata_service,
            ingestion_log_service=bundle.ingestion_log_service,
        )
        yield CLIExecutor(coordinator, backfill_manager)
```

**Step 3: 创建 IngestionBundle**

```python
# apps/port/src/ditto_port/registry/contexts/ingestion.py

@dataclass
class IngestionBundle:
    """聚合 ingestion 相关依赖。"""
    coordinator: IngestionCoordinator
    metadata_service: MetadataService
    ingestion_log_service: IngestionLogService


@contextmanager
def create_ingestion_bundle(
    source_name: str | Source,
    data_root: Path | None = None,
) -> Iterator[IngestionBundle]:
    """创建完整的 ingestion 依赖包。"""
    with create_cli_host(data_root) as container:
        # 从容器获取所有依赖
        metadata_service = container.get(MetadataService)
        ingestion_log_service = container.get(IngestionLogService)
        # ...

        with create_coordinator(...) as coordinator:
            yield IngestionBundle(
                coordinator=coordinator,
                metadata_service=metadata_service,
                ingestion_log_service=ingestion_log_service,
            )
```

**Step 4: 更新 main.py**

```python
# apps/port/src/ditto_port/cli/main.py

# 删除这段代码：
# if data_root:
#     os.environ["DITTO_DATA_ROOT"] = data_root

# 改为通过 ctx.obj 传递，供后续 create_cli_executor 使用
ctx.obj["data_root"] = data_root
```

**Step 5: 更新 ConfigProvider**

```python
# apps/port/src/ditto_port/registry/infra/config.py

def provide_data_root_config(
    config_loader: ConfigLoader,
    data_root_override: str | None = None,  # 新增显式参数
) -> DataRootConfig:
    values: dict[str, Any] = load_env_file(config_loader, "data_store")

    # 显式参数优先
    if data_root_override:
        values["data_root"] = data_root_override
    # 环境变量作为 fallback
    elif override := os.getenv("DITTO_DATA_ROOT"):
        values["data_root"] = override

    return DataRootConfig.model_validate(values)
```

#### 验收标准

- [ ] CLIExecutor 不再直接依赖 DataHub 服务
- [ ] `rg "os.environ\[.DITTO_DATA_ROOT" apps/port/src` 无结果
- [ ] `pixi run -e dev check` 通过
- [ ] CLI 命令 `ditto ingest --data-root=/path` 正常工作

---

## Phase 3: 清理完善

### PR-5: SQLitePool close_all

**覆盖 ID**: ENG-003
**Effort**: M（约 2-3 小时）
**优先级**: High

#### 改动范围

```
packages/infra/src/ditto_infra/foundation/db/
  ~ sqlite_pool.py       # 增加 close_all()

packages/infra/tests/unit/db/
  + test_sqlite_pool_multithread.py  # 新增多线程测试
```

#### 实施步骤

**Step 1: 增加连接追踪**

```python
# packages/infra/src/ditto_infra/foundation/db/sqlite_pool.py

class SQLitePool:
    def __init__(self, db_path: str, schema_path: Path | None = None) -> None:
        # ... 现有代码 ...
        self._all_connections: list[sqlite3.Connection] = []
        self._all_connections_lock = threading.Lock()

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(...)
            self._local.conn = conn

            # 追踪所有连接
            with self._all_connections_lock:
                self._all_connections.append(conn)
            # ...
        return cast(sqlite3.Connection, self._local.conn)
```

**Step 2: 增加 close_all 方法**

```python
def close_all(self) -> None:
    """关闭所有线程的连接（用于应用 shutdown）。"""
    with self._all_connections_lock:
        for conn in self._all_connections:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Failed to close connection: {e}")
        self._all_connections.clear()

    logger.info(
        "All SQLite connections closed",
        event="all_connections_closed",
    )
```

**Step 3: 添加多线程测试**

```python
# packages/infra/tests/unit/db/test_sqlite_pool_multithread.py

def test_close_all_closes_all_thread_connections():
    """close_all 应关闭所有线程的连接。"""
    pool = SQLitePool(":memory:")

    def get_conn_in_thread():
        pool.get_connection()

    threads = [threading.Thread(target=get_conn_in_thread) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 主线程也获取一个
    pool.get_connection()

    # 关闭所有
    pool.close_all()

    # 验证：尝试使用连接应失败
    with pytest.raises(sqlite3.ProgrammingError):
        pool.execute("SELECT 1")
```

#### 验收标准

- [ ] `close_all()` 关闭所有线程连接
- [ ] 多线程测试通过
- [ ] `pixi run -e dev check` 通过

---

### PR-6: 清理遗留代码

**覆盖 ID**: ENG-006
**Effort**: S（约 30 分钟）
**优先级**: Low

#### 改动范围

```
apps/port/src/ditto_port/jobs/
  ~ context.py           # 删除 create_metadata_context, create_dq_context

scripts/archive/
  - *.deprecated         # 删除所有 .deprecated 文件
```

#### 实施步骤

**Step 1: 确认无引用**

```bash
rg "create_metadata_context|create_dq_context" apps/port/src
rg "from.*jobs.context" apps/port/src
```

**Step 2: 删除废弃函数**

```python
# apps/port/src/ditto_port/jobs/context.py
# 删除 create_metadata_context() 和 create_dq_context()
# 保留 create_ingestion_bundle（如果还在使用）
```

**Step 3: 删除归档脚本**

```bash
rm scripts/archive/*.deprecated
```

#### 验收标准

- [ ] `rg "create_metadata_context|create_dq_context" apps/port/src` 无结果
- [ ] `pixi run -e dev check` 通过

---

### PR-7: 日志测试端点（可选）

**覆盖 ID**: ENG-005
**Effort**: S（约 30 分钟）
**优先级**: Low

#### 当前状态

已有运行时检查，路由仍注册在 OpenAPI 中。

#### 可选修复

```python
# apps/port/src/ditto_port/main.py

# 方案 A：按环境条件注册
if not get_environment().is_production:
    @app.get("/api/v1/logs/test", include_in_schema=False)
    async def generate_test_logs() -> dict[str, str]:
        ...

# 方案 B：使用 APIRouter 动态挂载
dev_router = APIRouter()

@dev_router.get("/logs/test")
async def generate_test_logs() -> dict[str, str]:
    ...

if not get_environment().is_production:
    app.include_router(dev_router, prefix="/api/v1")
```

---

## 执行检查清单

### Phase 1 完成标准

- [x] PR-1: DQSeverity 下沉完成 (commit: 09d801c)
- [x] PR-2: 启动 fail-fast 完成并测试 (commit: c473905)
- [x] PR-4: 删除重复方法完成 (commit: 77fdad9)
- [x] `pixi run -e dev check` 全部通过

### Phase 2 完成标准

- [x] PR-3: CLIExecutor 重构完成 (commit: aa5a615)
- [x] CLI 命令正常工作
- [x] 无 os.environ 全局副作用
- [x] `pixi run -e dev check` 全部通过

### Phase 3 完成标准

- [x] PR-5: SQLitePool close_all 完成 (commit: 518cbb9)
- [x] PR-6: 遗留代码清理完成 (commit: 07b500c)
- [x] PR-7: 日志端点（可选 - 跳过，已有运行时 404 检查）
- [x] `pixi run -e dev check` 全部通过 (1706 tests, 6 arch contracts)

---

## 变更记录

- 2026-02-16：初始版本
- 2026-02-16：全部实施完成
