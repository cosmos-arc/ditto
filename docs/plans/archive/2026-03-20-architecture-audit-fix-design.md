# 架构审计全量修复设计

**日期**: 2026-03-20
**基于**: `docs/reviews/2026-03-20-architecture-audit.md`
**范围**: P0/P1/P2 全部 30 项发现
**状态**: P0 完成 / P1 完成（P1-2/P1-4/P1-5/P1-6 已在先前的提交中完成）/ P2 待排期

---

## 总体策略

采用**增量分层修复**策略，按依赖关系排序，确保每一步都通过 `pixi run -e dev check` 验证。

**核心原则**：
- 每个修复独立可合入，不制造临时的架构退步
- 修复顺序遵循依赖链：先修底层（异常类位置），再修上层（导入引用）
- 优先修复有实际业务影响的 Bug（vol/volume、测试收集失败）
- 上帝类拆分采用"提取接口 → 逐步迁移 → 删除原类"三阶段，每个阶段可独立合入

---

## Phase 0: 立即修复（阻塞发布）

### P0-1: [TST-001] 修复 14 个 ingestion 测试收集失败 ✅

**根因**: `apps/port/tests/unit/services/ingestion/__init__.py` 存在且含 docstring，pytest 将 `ingestion` 视为 Python 包，导致 `from ingestion.test_xxx_unit` 导入失败。

**方案**: 删除测试目录下的 `__init__.py` 文件（与 `quality/` 子目录保持一致）。

**变更文件**:
- `apps/port/tests/unit/services/ingestion/__init__.py` — 删除
- `apps/port/tests/unit/services/ingestion/flows/__init__.py` — 删除
- `apps/port/tests/unit/services/ingestion/tasks/__init__.py` — 删除

**结果**: 收集错误从 14 降至 1（剩余 1 个为 pre-existing `test_config_unit.py` 文件名冲突，属不同问题）

**验证**: `pixi run -e dev test --unit` 收集错误从 14 降至 1（pre-existing）

---

### P0-2: [NAM-001] `vol` → `volume` 全局统一 ✅

**根因**: TDX reader 输出 `"vol"` 列名，Tushare 通过 ColumnMapping 已将 `"vol"` 重命名为 `"volume"`，导致下游跨源对比和 critical_fields 引用失效。

**变更清单**（源码 5 个文件）:

| 文件 | 变更 |
|------|------|
| `packages/data/src/ditto_data/sources/tdx/reader.py` | dict key/schema/docstring: `"vol"` → `"volume"` |
| `packages/data/src/ditto_data/sources/tdx/source.py` | docstring: `"vol"` → `"volume"` |
| `packages/core/src/ditto_core/quality/checkers/cross_source.py` | default rules key: `"vol"` → `"volume"` |
| `packages/core/src/ditto_core/quality/spec.py` | 注释示例: `"vol"` → `"volume"` |
| `apps/port/src/ditto_port/models/config.py` | ETF_DAILY/INDEX_DAILY/STOCK_DAILY critical_fields: `"vol"` → `"volume"` |

**测试文件同步更新**（约 8 个）:
- `packages/core/tests/unit/quality/test_cross_source_checker.py`
- `apps/port/tests/unit/services/ingestion/quality/conftest.py`
- `apps/port/tests/unit/services/ingestion/test_datasets_unit.py`
- `packages/data/tests/unit/sources/tdx/test_reader_unit.py`
- `packages/data/tests/unit/sources/tdx/test_source_unit.py`
- `packages/data/tests/unit/sources/tushare/test_transformer_unit.py`
- `packages/data/tests/unit/sources/tushare/test_source_unit.py`
- `packages/data/tests/unit/sources/tushare/adapters/test_stock_adapter_unit.py`

**不动的文件**: Tushare adapter 中的 API 请求字段 `"vol"` 是 Tushare 的原始字段名，不需要改。`common.py` 的 `rename={"vol": "volume"}` 保持不变（Tushare 数据源仍需此映射）。

**验证**: `pixi run -e dev check` 通过 + grep 确认 src 中仅 README 保留 "vol"（Tushare API 示例）

---

## Phase 1: 架构健康修复

### P1-1: [ARCH-001] 异常类下移 — 消除 core → datahub 反向依赖 ✅

**根因**: `DerivedNotImplementedError`、`DerivedValidationError`、`DerivedNotFoundError` 及其基类 `DerivedError` 全部定义在 `ditto_data.errors`，但被 `ditto_core.engine` 运行时导入。

**方案**: 将整个 `Derived*` 异常族下移到 `ditto_core.engine.errors`，因为 "Derived"（因子衍生）是 core 引擎层的核心概念。

**依赖分析**:

| 异常类 | core 使用 | datahub 使用 | port 使用 |
|--------|-----------|-------------|-----------|
| `DerivedError` | 测试间接 | 无 | 无 |
| `DerivedNotFoundError` | 测试 | query_service, artifact_reader | research, publication |
| `DerivedVersionError` | 无 | artifact_reader | 无 |
| `DerivedMaterializationError` | 无 | 无 | 无 |
| `DerivedDependencyError` | 无 | 无 | 无 |
| `DerivedNotImplementedError` | research.py, specs.py | 无 | 无 |
| `DerivedValidationError` | research.py | query_service | research, publication |

**变更步骤**:

1. **创建** `packages/core/src/ditto_core/engine/errors.py`，将 `DerivedError` 及其 6 个子类完整复制过去
2. **修改** `packages/data/src/ditto_data/errors.py` — 将 `Derived*` 类改为从 core re-export：
   ```python
   # ditto_data/errors.py — 保持向后兼容
   from ditto_core.engine.errors import (  # noqa: F401
       DerivedError,
       DerivedNotFoundError,
       DerivedNotImplementedError,
       DerivedValidationError,
       DerivedVersionError,
       DerivedMaterializationError,
       DerivedDependencyError,
   )
   ```
3. **修改** core 的导入：
   - `core/engine/research.py`: `from ditto_data.errors import ...` → `from ditto_core.engine.errors import ...`
   - `core/engine/specs.py`: 同上
4. **不修改** datahub 和 port 的导入（它们通过 re-export 兼容路径继续工作）
5. **后续可选**: 逐步将 datahub/port 的直接导入从 `ditto_data.errors` 改为 `ditto_core.engine.errors`，最终移除 datahub 的 re-export

**向后兼容**: datahub re-export 保证零破坏性，port 和 datahub 的现有代码无需立即修改。

**验证**: `pixi run -e dev check` + `pixi run -e dev arch-check`

---

### P1-2: [ARCH-002] 消除 datahub → core 反向依赖 ✅（先前提交已完成）

**根因**: `derived_artifact_writer.py`（stores 层）运行时导入了 `ditto_core.engine.materialization.Analysis, CompileIdentity` 和 `ditto_core.engine.specs.DerivedSpec`。`artifact_persistence_service.py`（service 层）使用 TYPE_CHECKING 导入同类。

**前置依赖**: P1-1 完成后，`DerivedSpec` 仍在 core（属于 core 领域模型），`Analysis`/`CompileIdentity` 同属 core 物化模型。

**方案**: 提取 Protocol 接口到 datahub，解耦运行时依赖。

**具体做法**:

1. **在 datahub 定义 Protocol**（`packages/data/src/ditto_data/services/derived/persistence_protocols.py`）:
   ```python
   from typing import Protocol
   from dataclasses import dataclass

   @dataclass(frozen=True)
   class CompileKey:
       """Minimal compile identity for persistence — mirrors core's CompileIdentity."""
       expression_hash: str
       dataset_id: str

   @dataclass(frozen=True)
   class MaterializationResult:
       """Minimal materialization result for persistence — mirrors core's Analysis."""
       derived_id: str
       version: str
       records: int

   class DerivedSpecLike(Protocol):
       """Protocol for DerivedSpec used by persistence layer."""
       @property
       def expression(self) -> str: ...
       @property
       def derived_id(self) -> str: ...
   ```

2. **修改 `derived_artifact_writer.py`**: 将 `from ditto_core.engine...` 替换为 Protocol 引用。Writer 只需要 `CompileKey` 和 `MaterializationResult` 的数据字段来序列化。

3. **修改 `artifact_persistence_service.py`**: 移除 TYPE_CHECKING 块，使用 Protocol 类型。

4. **修改 port 层的 Orchestrator/Service**: 在组装时将 core 的 `Analysis`/`CompileIdentity` 转换为 Protocol 数据类。

**验证**: `pixi run -e dev check` + 确认 datahub/src 无 `from ditto_core` 导入

---

### P1-3: [ENG-001] 消除 6 处 TYPE_CHECKING 违规 ✅

**分析结果**:

| 文件 | 性质 | 处理方式 |
|------|------|----------|
| `datahub/sources/fred/adapters/base.py` | **空块（死代码）** | 直接删除 TYPE_CHECKING 块 |
| `port/errors.py` | **空块（死代码）** | 直接删除 TYPE_CHECKING 块 |
| `port/services/ingestion/index_config.py` | polars 延迟导入（性能优化） | 保留 — polars 是重库，延迟合理 |
| `datahub/services/derived/artifact_persistence_service.py` | **循环依赖掩盖** | 由 P1-2 解决 |
| `port/services/ingestion/list_date_inference.py` | 允许方向的非必要延迟 | 改为顶层导入（port→datahub 是合法方向） |

**变更**:
- `fred/adapters/base.py`: 删除 `from typing import TYPE_CHECKING` 和 `if TYPE_CHECKING: pass`
- `port/errors.py`: 从 `from typing import TYPE_CHECKING, Any` 改为 `from typing import Any`，删除空块
- `port/services/ingestion/list_date_inference.py`: 将 TYPE_CHECKING 块内的导入移到文件顶部
- `index_config.py`: 保留不动（polars 延迟导入合理）
- `artifact_persistence_service.py`: 由 P1-2 解决

**实际 TYPE_CHECKING 清零**: P1-2 完成后，src 中仅剩 `index_config.py` 的 polars 延迟（合理保留）。

---

### P1-4: [DESIGN-001] MetadataService 上帝类拆分 ✅（先前提交已完成）

**现状**: 1,316 行 / 41 个方法 / 覆盖 metadata、instrument、calendar、industry、universe 五个领域。

**方案**: 采用"外观模式 + 委托"三阶段拆分，保持 MetadataService 作为外观类存在，将实现逐步下沉到专用 Service。

#### 阶段 1: 提取子领域 Service（不破坏现有调用方）

创建 4 个新 Service，从 MetadataService 中迁移方法实现：

| 新 Service | 来源方法 | 职责 |
|-----------|---------|------|
| `InstrumentService` | `get_instrument*`, `find_instrument*`, `resolve_*`, `update_list_date` | 证券基本信息 CRUD |
| `CalendarService` | `is_trading_day*`, `list_trading_days*`, `get_*_date` | 交易日历查询 |
| `IndustryService` | `get_industry*`, `list_industries*` | 行业分类查询 |
| `UniverseService` | `get_universe*`, `list_constituents*` | 股票池管理 |

每个子 Service 通过构造函数接收 `SQLiteClient` 和必要的 Reader/Writer。

#### 阶段 2: MetadataService 委托

```python
class MetadataService:
    """Facade — delegates to domain-specific services."""

    def __init__(self, ...):
        self._instrument = InstrumentService(...)
        self._calendar = CalendarService(...)
        self._industry = IndustryService(...)
        self._universe = UniverseService(...)

    # 委托方法 — 保持公共 API 不变
    def get_instrument(self, ...):  # noqa: D401
        return self._instrument.get_instrument(...)

    def is_trading_day(self, ...):
        return self._calendar.is_trading_day(...)
```

此阶段 MetadataService 变为纯委托层，所有现有调用方无需修改。

#### 阶段 3（后续）: 调用方逐步迁移

Port 层的 DI 容器（`registry/datahub/metadata.py`）逐步将子 Service 注册为独立依赖，调用方从 `metadata_service.get_instrument()` 改为 `instrument_service.get_instrument()`。最终 MetadataService 可删除。

**每个阶段独立可合入**，阶段 1 和 2 在一次 PR 中完成即可。

---

### P1-5: [ARCH-003] port 层 runtime/sources 导入清理 ✅（先前提交已完成）

**违规清单**（非 registry 模块）:

| 文件 | 违规导入 | 性质 |
|------|---------|------|
| `services/ingestion/factory.py:12` | `FreezeManager` (runtime) | 运行时导入 |
| `services/ingestion/coordinator.py:27,34` | `FreezeManager` (runtime), `DataSource` (sources) | 运行时导入 |
| `services/ingestion/list_date_inference.py:24` | `DataSource` (sources) | TYPE_CHECKING → 顶层 |
| `registry/contexts/ingestion.py:6,14` | `FreezeManager` (runtime), `ExchangeTransformers` (sources) | 运行时导入 |
| `registry/contexts/bundle.py:12` | `ExchangeTransformers` (sources) | 运行时导入 |

**分析**: `registry/contexts/` 虽然在 registry 目录下，但它不是 DI 装配代码（那是 `registry/datahub/`），而是 DI context 定义。严格来说，context 模块应只引用 Service 层类型。

**方案**: 在 DataHub Service 层暴露所需的抽象。

1. **FreeManager**: 在 `ditto_data.services` 中暴露。创建 `FreezeService` 或将 `FreezeManager` 从 `runtime` 提升到 `services` 层。
   - 如果 `FreezeManager` 本身就是 Service 性质（有状态管理），直接移动到 services 包
   - 如果它是纯基础设施组件，在 services 层提供 facade 方法

2. **DataSource**: `coordinator.py` 和 `list_date_inference.py` 使用 `DataSource` Protocol。将其从 `sources.base` 移到 `ditto_data.services.ports`（port 接口定义层），与 `MarketReadPorts` 等并列。

3. **ExchangeTransformers**: 在 `ditto_data.services.source_service` 中提供 `get_exchange_transformers()` 方法，context 模块通过 Service 访问。

**验证**: 确认 `apps/port/src/ditto_port/services/` 和 `apps/port/src/ditto_port/registry/contexts/` 无 `from ditto_data.runtime` 或 `from ditto_data.sources` 直接导入。

---

### P1-6: [ARCH-004] datahub 测试导入 port 层类 ✅（先前提交已完成）

**文件**: `packages/data/tests/unit/services/test_derived_materialization_orchestrator_unit.py:48-54`

导入了 `DerivedMaterializationOrchestrator`、`InMemoryDerivedInputProvider`、`RuntimeDerivedInputProvider`、`SQLiteCompileCache`。

**方案**: 使用 mock 替代真实 port 类。

测试的核心目的是验证 datahub 层的 `DerivedCatalogService` 和 `ArtifactPersistenceService` 在编排器下的协作行为。Orchestrator 本身是 port 层组件，不应出现在 datahub 测试中。

**变更**:
- 在测试中使用 `mocker.MagicMock(spec=...)` 模拟 Orchestrator 的接口
- 如果测试确实需要验证编排逻辑，应将测试文件迁移到 `apps/port/tests/unit/` 下

**验证**: `pixi run -e dev test --unit` + 确认 datahub/tests 无 `from ditto_port` 导入

---

## Phase 2: 持续改进

### P2-1: [DESIGN-002] 拆分其他过大类

| 类 | 方法数 | 拆分策略 |
|----|--------|---------|
| `RuntimeProvider` (37) | 按领域拆分: `MarketProvider`, `DerivedProvider`, `IngestionProvider` | 每个领域 <15 方法 |
| `DerivedCatalogService` (32) | 读写拆分: `DerivedCatalogReader` + `DerivedCatalogWriter` | 核心 Domain Service 模式 |
| `TushareSource` (29) | 按数据域拆分: 已有 adapters 模式，进一步将 source 逻辑按 market/capital/macro 分离 | 每个 <10 方法 |
| `IngestionCoordinator` (21) | 提取子协调器: `QualityCoordinator`（DQ 阻塞/重试）、`WriteCoordinator`（写入编排） | 核心 <10 方法 |
| `MarketService` (23) | 按市场类型拆分: `StockMarketService`, `EtfMarketService`, `FxMarketService` + `MarketService` facade | 每个 <10 方法 |

**原则**: 均采用 P1-4 的"外观 + 委托"模式，保证向后兼容。

---

### P2-2: [ENG-002] 收敛 Any 类型（63 处）

**优先处理**（有实际类型安全影响）:

| 文件 | 问题 | 修复 |
|------|------|------|
| `datahub/stores/base/parquet_store.py:43` | `_client: Any` | 定义 `SQLiteClient` Protocol 或使用具体类型 |
| `datahub/stores/base/sqlite_store.py:46` | `_client: Any` | 同上 |
| `port/services/ingestion/quality/service.py:95` | `result: Any` (注释标注 DQResult) | 使用 `DQResult` 具体类型 |
| `port/services/ingestion/quality/reconciliation_service.py:61` | `engine: Any` (注释标注 QualityEngine) | 定义 `QualityEngine` Protocol |
| `datahub/services/metadata_service.py:149-150` | `rebalance_reader/writer: Any` | 使用 Protocol 或拆分后使用具体 Service 类型 |

**策略**: 对 Store 层的 `_client` 统一定义 Protocol；对 Service 层依赖使用具体类型或 Protocol。

---

### P2-3: [NAM-002] 整理 ticker 术语体系

**当前状态**: `source_ticker`（77 文件/948 处）、`ticker`、`standard_ticker` 三种表述。

**方案**: 建立领域术语表，明确语义：

| 术语 | 含义 | 使用场景 |
|------|------|---------|
| `source_ticker` | 数据源原始代码（如 `000001.SZ`） | 数据摄入层、raw 数据 |
| `instrument_id` | 内部整数 ID | 存储层、核心引擎层 |
| `ticker` | 人类可读代码（如 `000001.SZ`） | API 层、CLI 输出 |

**注意**: `source_ticker` 使用过于广泛，全局重命名为 `ticker` 的成本极高（948 处）。建议：
- 保持 `source_ticker` 不变（已成既定约定）
- `standard_ticker` 如果使用量小可合并到 `ticker`
- 在 CLAUDE.md 中记录术语表作为规范

---

### P2-4: [DESIGN-003] CompileCache 实现下沉

**现状**: `SQLiteCompileCache` 在 core 层（`packages/core/src/ditto_core/engine/compile_cache.py`），core 不应包含 SQLite 实现细节。

**方案**:

1. 在 `ditto_core.engine` 定义 `CompileCacheBackend` Protocol:
   ```python
   class CompileCacheBackend(Protocol):
       def get(self, key: str) -> bytes | None: ...
       def put(self, key: str, value: bytes) -> None: ...
       def delete(self, key: str) -> None: ...
   ```

2. 将 `SQLiteCompileCache` 实现移到 `ditto_data.stores.runtime` 或 `ditto_infra.foundation`

3. Core 层只依赖 Protocol，不依赖具体实现

**验证**: 确认 core/src 无 `import sqlite3` 或 `SQLite` 相关引用

---

### P2-5: [DESIGN-004] Writer 基类抽取公共逻辑

**现状**: 11 个 fundamental/capital Writer 文件有相同的 depth=5 嵌套模式（context manager + records 遍历）。

**方案**: 在 Writer 基类中实现模板方法模式：

```python
class BaseWriter(ABC):
    @contextmanager
    def batch_write(self, df: pl.DataFrame):
        with self._connect() as conn:
            for record in df.iter_rows(named=True):
                self._write_record(conn, record)
            self._flush(conn)

    @abstractmethod
    def _write_record(self, conn, record: dict) -> None: ...
```

**收益**: 消除 11 个文件的重复嵌套，新增 Writer 只需实现 `_write_record`。

---

### P2-6: [ENG-006] models 包分域子包化

**现状**: `ditto_data.models` 导出 85 个符号，`ditto_core.engine` 导出 43 个符号。

**方案**: 逐步从 `from ditto_data.models import X` 迁移为 `from ditto_data.models.market import X`。保持 `__init__.py` 的 re-export 一段时间以向后兼容，然后在后续版本中移除。

**不在此阶段实施**: 成本高但收益低，可作为技术债务的长期清理项。

---

## Low 级别修复（快速清理）

### L1-L8 批量处理

| ID | 问题 | 修复 | 工作量 |
|----|------|------|--------|
| [NAM-004] | `adj="qfq"` 参数名 | 重命名为 `adjustment_type="qfq"` | 小（20+处） |
| [NAM-005] | `PitHelper` 命名过宽 | 重命名为 `PitQueryBuilder` | 小 |
| [NAM-006] | `DatabaseManager` 测试辅助类 | 重命名为 `TestDatabaseHelper` | 小 |
| [NAM-007] | OHLCV 作为标识符 | 保持不变（金融标准术语） | 无 |
| [ENG-004] | 73 处 noqa | C901/PLR091x 的 11 处需通过重构消除；其余合法 | 中 |
| [ENG-005] | 4 处 type:ignore | 审查 core/engine/compile_cache.py 和 evaluator.py 的 2 处 | 小 |
| [NAM-003] | MetadataManager vs MetadataService | Port 层 `MetadataManager` 重命名为 `IngestionMetadataCoordinator` | 小 |
| [ENG-003] | 2 处行内导入缺 noqa | port/main.py:201,310 添加 `# noqa: PLC0415` 或重构 | 小 |

---

## 实施顺序总览

```
Week 1: P0 修复
  ├── P0-1: 测试收集失败修复          (30min)
  └── P0-2: vol → volume 统一        (1h)

Week 2: P1 架构修复（核心）
  ├── P1-1: 异常类下移 core           (1h)
  ├── P1-3: TYPE_CHECKING 清理       (30min) ← 依赖 P1-1 间接
  └── P1-5: port runtime/sources 清理 (2h)

Week 3: P1 架构修复（深入）
  ├── P1-2: datahub → core Protocol 解耦 (2h) ← 依赖 P1-1
  ├── P1-4: MetadataService 拆分阶段1+2  (3h)
  └── P1-6: datahub 测试修复          (30min)

Week 4: Low 级别批量清理
  └── L1-L8: 全部 Low 级修复          (2h)

后续迭代: P2 持续改进
  └── P2-1 ~ P2-6: 按需排入各迭代
```

---

## 每步验证命令

```bash
pixi run -e dev check              # lint + fmt + type + test --fast
pixi run -e dev test --unit        # 完整单元测试
pixi run -e dev arch-check         # 边界检查（如果可用）

# 检查反向依赖是否已消除
grep -r "from ditto_data" packages/core/src/ | grep -v README
grep -r "from ditto_core" packages/data/src/ | grep -v README
grep -r "from ditto_port" packages/data/tests/

# 检查 TYPE_CHECKING 是否已清理
grep -r "TYPE_CHECKING" packages/*/src apps/*/src | grep -v "__pycache__"

# 检查 vol/volume 一致性
grep -r '"vol"' packages/*/src apps/*/src | grep -v "__pycache__" | grep -v "volume"
```
