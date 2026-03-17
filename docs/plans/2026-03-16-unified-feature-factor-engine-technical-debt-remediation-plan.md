# Unified Feature/Factor Engine 技术债务整改计划

**创建日期**: 2026-03-16
**状态**: Phase 1 已完成 ✅
**目标**: 所有维度评分提升至 **10/10**

---

## 整改目标

| 维度 | 当前评分 | 目标评分 | 关键提升点 |
|------|----------|----------|------------|
| **语义正确性** | 5/10 | **10/10** | 状态分裂、事务边界、静默降级 |
| **设计实现一致性** | 5/10 | **10/10** | 类型退化、cascade protocol、时间语义 |
| **工程质量** | 6/10 | **10/10** | 分层边界、文件职责、异常体系 |
| **可维护性** | 7/10 | **10/10** | ADR 整理、命名一致性 |
| **设计完整度** | 8/10 | **10/10** | 热层接口定义、迁移计划明确 |

---

## 核心约束

| 约束项 | 内容 |
|--------|------|
| 时间 | 4 周（2026-03-18 ~ 2026-04-14） |
| 新功能 | **完全冻结**，不接受任何新需求 |
| 验证策略 | **严格 TDD**：先补测试，再改实现 |
| 每周节奏 | 周一启动 → 周三代码审查 → 周五验收 |

### 全局重构原则

> **所有修改不需要考虑向后兼容。直接迁移重构，不留别名、不保留旧接口。**

---

## Phase 总览

| Phase | 名称 | 问题数 | 周次 | 核心目标 | 状态 |
|-------|------|--------|------|----------|------|
| **Phase 1** | 核心语义修复 | 9 | Week 1 | 状态统一、事务边界、类型恢复 | ✅ 已完成 |
| **Phase 2** | 结构重构 | 8 | Week 2 | Port 层职责下沉、接口重构 | 待开始 |
| **Phase 3** | 语义补全 | 10 | Week 3 | Cascade protocol、时间语义 | 待开始 |
| **Phase 4** | 架构完善 | 11 | Week 4 | 热层接口、ADR 整理、工程标准 | 待开始 |

---

## Phase 1: 核心语义修复（Week 1）

### 问题清单

| ID | 问题 | 类型 | 严重程度 | 状态 |
|----|------|------|----------|------|
| **C-LC-01** | `DerivedVersionStatus` 与 `"PUBLISHED"` 字符串分裂 | 核心 | 高 | ✅ 已完成 |
| **C-LC-02** | SQLite 查询需兼容两套口径 | 核心 | 高 | ✅ 已完成 |
| **C-TX-01** | 每个 `write_*()` 立即 `commit()`，无事务包装 | 核心 | 高 | ✅ 已完成 |
| **C-TX-02** | materialization 多步骤无原子性 | 核心 | 高 | ✅ 已完成 |
| **C-CC-01** | `get_or_compile()` 先编译再查缓存 | 核心 | 高 | ✅ 已完成 |
| **C-CC-02** | 没有 L2 read path（SQLite 查询） | 核心 | 中 | ✅ 已完成 |
| **C-FA-01** | fallback alias 静默降级 | 核心 | 高 | ✅ 已完成 |
| **D-SPEC-01** | `CalendarId` 退化为 `str` | 设计 | 中 | ✅ 已完成 |
| **D-SPEC-02** | `GrainId` 退化为 `str` | 设计 | 中 | ✅ 已完成 |

### 1.1 C-LC-01/02: 生命周期状态统一

**问题分析**：

```python
# 当前 models.py - DerivedVersionStatus
class DerivedVersionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"

# 当前 publication.py - 直接使用字符串（第 235 行）
target_status="PUBLISHED"  # 与枚举不一致！

# 当前 publication.py - 第 298 行
status="DEPRECATED"  # 与枚举值 "deprecated" 大小写不一致！
```

**修复方案**：扩展 `DerivedVersionStatus` 枚举

```python
# packages/core/src/ditto_core/engine/materialization/models.py
class DerivedVersionStatus(StrEnum):
    """Catalog lifecycle status for a derived version."""

    DRAFT = "draft"                 # 草稿，未物化
    MATERIALIZED = "materialized"   # 已物化，未发布
    PUBLISHED = "published"         # 已发布，可在线查询
    DEPRECATED = "deprecated"       # 已废弃，不推荐使用
    ARCHIVED = "archived"           # 已归档，只读历史
```

**代码修改点**：

| 文件 | 修改内容 |
|------|----------|
| `packages/core/src/ditto_core/engine/materialization/models.py` | 扩展枚举定义 |
| `apps/port/src/ditto_port/services/derived/publication.py:235` | `target_status=DerivedVersionStatus.PUBLISHED` |
| `apps/port/src/ditto_port/services/derived/publication.py:255` | `status=DerivedVersionStatus.PUBLISHED` |
| `apps/port/src/ditto_port/services/derived/publication.py:298` | `status=DerivedVersionStatus.DEPRECATED` |
| `packages/datahub/src/ditto_datahub/stores/runtime/derived_catalog/*.py` | 更新查询条件 |

**数据清理**：

直接清理历史数据中的旧状态值（无需兼容迁移）：
- `active` → `published`
- `draft`（已物化）→ `materialized`
- `draft`（未物化）→ `draft`

**测试用例**：

```python
# packages/core/tests/unit/engine/test_materialization_models_unit.py
def test_status_enum_values():
    assert DerivedVersionStatus.DRAFT.value == "draft"
    assert DerivedVersionStatus.PUBLISHED.value == "published"
    assert DerivedVersionStatus.DEPRECATED.value == "deprecated"

def test_status_string_comparison():
    assert DerivedVersionStatus.PUBLISHED == "published"
    assert DerivedVersionStatus.PUBLISHED != "PUBLISHED"  # 大小写敏感
```

---

### 1.2 C-TX-01/02: 事务边界

**问题分析**：

```python
# 当前 derived_catalog_writer.py - 每个方法立即写文件
def write_spec(self, record: DerivedSpecRecord) -> None:
    write_json_file(...)  # 立即写入，无法回滚

def write_version(self, record: DerivedVersionRecord) -> None:
    write_json_file(...)  # 立即写入，无法回滚
```

**修复方案**：引入 `UnitOfWork` 模式

```python
# packages/datahub/src/ditto_datahub/stores/runtime/unit_of_work.py

class AtomicWriter(Protocol):
    """原子写入器协议"""
    def begin(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class UnitOfWork:
    """工作单元，管理事务边界"""

    def __init__(self, writer: AtomicWriter) -> None:
        self._writer = writer
        self._operations: list[Callable[[], None]] = []
        self._committed = False

    def enqueue(self, operation: Callable[[], None]) -> None:
        """将写操作加入队列"""
        if self._committed:
            raise RuntimeError("Cannot enqueue after commit")
        self._operations.append(operation)

    def commit(self) -> None:
        """原子提交所有操作"""
        self._writer.begin()
        try:
            for op in self._operations:
                op()
            self._writer.commit()
            self._committed = True
        except Exception:
            self._writer.rollback()
            raise

    @property
    def is_committed(self) -> bool:
        return self._committed
```

**实现 - 文件系统原子写入器**：

```python
# packages/datahub/src/ditto_datahub/stores/runtime/file_atomic_writer.py

class FileAtomicWriter:
    """基于文件系统的原子写入器"""

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path
        self._temp_dir: Path | None = None
        self._pending_writes: list[tuple[Path, dict]] = []

    def begin(self) -> None:
        self._temp_dir = Path(tempfile.mkdtemp(dir=self._base_path))

    def enqueue_write(self, relative_path: str, data: dict) -> None:
        """将写入操作加入队列"""
        self._pending_writes.append((relative_path, data))

    def commit(self) -> None:
        """原子提交：先写临时文件，再批量重命名"""
        for relative_path, data in self._pending_writes:
            temp_file = self._temp_dir / relative_path
            temp_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file.write_text(orjson.dumps(data))

            # 原子移动到目标位置
            target = self._base_path / relative_path
            shutil.move(str(temp_file), str(target))

        self._cleanup()

    def rollback(self) -> None:
        """回滚：清理临时文件"""
        self._cleanup()

    def _cleanup(self) -> None:
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
        self._pending_writes.clear()
```

**测试用例**：

```python
# packages/datahub/tests/unit/stores/runtime/test_unit_of_work_unit.py

def test_commit_persists_all_operations():
    writer = MockAtomicWriter()
    uow = UnitOfWork(writer)

    uow.enqueue(lambda: writer.write("a", {"x": 1}))
    uow.enqueue(lambda: writer.write("b", {"y": 2}))
    uow.commit()

    assert writer.writes == [("a", {"x": 1}), ("b", {"y": 2})]

def test_rollback_on_failure():
    writer = MockAtomicWriter(fail_on="b")
    uow = UnitOfWork(writer)

    uow.enqueue(lambda: writer.write("a", {"x": 1}))
    uow.enqueue(lambda: writer.write("b", {"y": 2}))  # 这里会失败

    with pytest.raises(RuntimeError):
        uow.commit()

    assert writer.rolled_back
```

---

### 1.3 C-CC-01/02: Compile Cache 修复

**问题分析**：

```python
# 当前 compile_cache.py:56-59
compiled = self._compiler.compile(spec)  # 先编译！浪费资源
cache_key = compiled.compile_identity.cache_key
if not force_recompile and cache_key in self._memory_cache:  # 再查缓存
    return self._memory_cache[cache_key]
```

**修复方案**：三级缓存查询

```python
# apps/port/src/ditto_port/services/derived/compile_cache.py

class SQLiteCompileCacheService:
    """Persist compile metadata while keeping an in-process L1 cache."""

    def __init__(self, sqlite_client: SQLiteCompileCacheBackend) -> None:
        self._sqlite_client = sqlite_client
        self._memory_cache: dict[str, CompiledDerivedExpression] = {}
        self._compiler = ExpressionCompiler()

    def get_or_compile(
        self,
        spec: DerivedSpec,
        *,
        force_recompile: bool = False,
    ) -> CompiledDerivedExpression:
        """Return a compiled expression with proper cache hierarchy."""

        # L1: 基于 spec 计算 cache key（不需要编译）
        cache_key = self._compute_cache_key(spec)

        # L2: 内存缓存
        if not force_recompile and cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        # L3: SQLite 持久化缓存
        if not force_recompile:
            cached = self._query_sqlite_cache(cache_key)
            if cached is not None:
                self._memory_cache[cache_key] = cached
                return cached

        # L4: 编译并缓存
        compiled = self._compiler.compile(spec)
        self._memory_cache[cache_key] = compiled
        self._persist_to_sqlite(cache_key, compiled)
        return compiled

    def _compute_cache_key(self, spec: DerivedSpec) -> str:
        """基于 spec 计算 cache key，无需编译。"""
        # 使用 spec 的不可变属性 + operator_versions 计算 hash
        spec_dict = {
            "id": spec.id,
            "version": spec.version,
            "expression": spec.expression,
            "operator_versions": spec.operator_versions,
        }
        return hashlib.sha256(
            orjson.dumps(spec_dict, option=orjson.OPT_SORT_KEYS)
        ).hexdigest()[:32]

    def _query_sqlite_cache(
        self, cache_key: str
    ) -> CompiledDerivedExpression | None:
        """从 SQLite 查询缓存。"""
        row = self._sqlite_client.execute(
            """
            SELECT analysis_json, compile_identity_json, expression_repr
            FROM compiled_expression_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        # 反序列化并返回
        return self._deserialize_compiled(row)

    def _persist_to_sqlite(
        self, cache_key: str, compiled: CompiledDerivedExpression
    ) -> None:
        """持久化到 SQLite。"""
        # 现有的持久化逻辑...
```

**测试用例**：

```python
# apps/port/tests/unit/services/derived/test_compile_cache_unit.py

def test_l1_memory_cache_hit():
    service = SQLiteCompileCacheService(mock_sqlite)
    spec = DerivedSpec(...)

    # 第一次编译
    result1 = service.get_or_compile(spec)
    assert result1.from_cache is False

    # 第二次应该命中内存缓存
    result2 = service.get_or_compile(spec)
    assert result2.from_cache is True
    assert result2 is result1  # 同一对象

def test_l2_sqlite_cache_hit():
    service = SQLiteCompileCacheService(sqlite_with_cached_spec)
    spec = DerivedSpec(...)

    # 新实例应该命中 SQLite 缓存
    result = service.get_or_compile(spec)
    assert result.from_cache is True
    assert service._compiler.compile_count == 0  # 没有触发编译

def test_no_unnecessary_compile_on_cache_hit():
    service = SQLiteCompileCacheService(mock_sqlite)
    service._memory_cache["known_key"] = mock_compiled

    # 即使 force_recompile=False，也应该先查缓存
    result = service.get_or_compile(spec)
    assert service._compiler.compile_count == 0
```

---

### 1.4 C-FA-01: Fallback Alias 移除

**问题分析**：

```python
# 当前 materialization.py:736-744
fallback_column = value_candidates[0] if value_candidates else None
for dependency in dependencies:
    if (
        dependency in prepared.columns
        or _dependency_input_column(dependency) in prepared.columns
        or fallback_column is None
    ):
        continue
    # 静默用任意列填充！危险！
    prepared = prepared.with_columns(pl.col(fallback_column).alias(dependency))
```

**修复方案**：缺失依赖抛显式异常

```python
# apps/port/src/ditto_port/services/derived/materialization.py

class MissingDependencyError(Exception):
    """依赖列缺失异常"""
    def __init__(self, missing: list[str], available: list[str]) -> None:
        self.missing = missing
        self.available = available
        super().__init__(
            f"Missing required dependency columns: {missing}. "
            f"Available columns: {available}"
        )


def _prepare_input_frame(
    *,
    frame: pl.DataFrame,
    spec: DerivedSpec,
    dependencies: tuple[str, ...],
) -> pl.DataFrame:
    """准备输入数据框，验证所有依赖存在。"""
    sort_columns = [*spec.entity_keys, *spec.effective_time_keys]
    prepared = frame.sort(sort_columns)

    # 检查所有依赖是否存在
    missing = []
    for dependency in dependencies:
        if dependency not in prepared.columns:
            input_col = _dependency_input_column(dependency)
            if input_col not in prepared.columns:
                missing.append(dependency)

    if missing:
        raise MissingDependencyError(
            missing=missing,
            available=list(prepared.columns),
        )

    return prepared
```

**测试用例**：

```python
# apps/port/tests/unit/services/derived/test_materialization_unit.py

def test_missing_dependency_raises_error():
    frame = pl.DataFrame({
        "instrument_id": [1, 2],
        "trade_date": ["2024-01-01", "2024-01-02"],
        # 缺少 "close" 列
    })
    spec = DerivedSpec(id="test", ...)
    dependencies = ("close",)

    with pytest.raises(MissingDependencyError) as exc_info:
        _prepare_input_frame(frame=frame, spec=spec, dependencies=dependencies)

    assert "close" in str(exc_info.value)
    assert exc_info.value.missing == ["close"]

def test_all_dependencies_present_succeeds():
    frame = pl.DataFrame({
        "instrument_id": [1, 2],
        "trade_date": ["2024-01-01", "2024-01-02"],
        "close": [10.0, 11.0],
    })
    spec = DerivedSpec(id="test", ...)
    dependencies = ("close",)

    result = _prepare_input_frame(frame=frame, spec=spec, dependencies=dependencies)
    assert "close" in result.columns
```

---

### 1.5 D-SPEC-01/02: 类型安全恢复

**问题分析**：

```python
# 当前 specs.py:8-9
type CalendarId = str  # ADR-032 定义应该是 Literal["cn_stock"]
type GrainId = str     # ADR-032 定义应该是 Literal["1d", "1m"]
```

**修复方案**：恢复 `Literal` 类型

```python
# packages/core/src/ditto_core/engine/specs.py

from typing import Literal

type CalendarId = Literal["cn_stock"]
type GrainId = Literal["1d", "1m"]
```

**影响范围分析**：

| 文件 | 影响 |
|------|------|
| `specs.py` | 类型定义恢复 |
| `planner.py` | 使用 `GrainId` 参数的函数 |
| `query_facade.py` | 使用 `CalendarId` 参数的函数 |
| 测试文件 | 可能需要调整 mock 数据 |

**测试用例**：

```python
# packages/core/tests/unit/engine/test_specs_unit.py

def test_calendar_id_literal():
    spec = DerivedSpec(
        id="test",
        calendar="cn_stock",  # OK
        ...
    )
    assert spec.calendar == "cn_stock"

def test_calendar_id_invalid():
    with pytest.raises(TypeError):  # 类型检查应该失败
        DerivedSpec(
            id="test",
            calendar="us_stock",  # 不在 Literal 中
            ...
        )

def test_grain_id_literal():
    spec = DerivedSpec(
        id="test",
        grain="1d",  # OK
        ...
    )
    assert spec.grain == "1d"
```

---

### Phase 1 修复顺序

```
Day 1-2: 类型安全基础
├── D-SPEC-01/02: 恢复 Literal 类型
└── 影响分析 + 测试更新

Day 2-3: 生命周期状态统一
├── C-LC-01: 扩展 DerivedVersionStatus
├── 清理历史数据中的旧状态值
└── C-LC-02: 自动解决（状态统一后）

Day 3-4: 事务边界
├── C-TX-01: 引入 UnitOfWork
└── C-TX-02: 应用到 materialization

Day 4-5: Cache 修复
├── C-CC-01: 修复查询顺序
└── C-CC-02: 添加 L2 查询

Day 5: Fallback 移除
└── C-FA-01: 抛显式异常
```

---

### Phase 1 验收标准

| 检查项 | 标准 |
|--------|------|
| 类型检查 | `basedpyright` 无错误 |
| 单元测试 | 所有新增/修改代码覆盖率 ≥ 80% |
| 集成测试 | 旧状态值清理验证通过 |
| Lint | `ruff` 无错误 |
| 文档 | 更新相关 ADR |

### Phase 1 完成摘要（2026-03-16）

**全部 9 个问题已修复，测试 2109 passed，覆盖率 80.31%。**

| 任务组 | 修复内容 | 关键文件 |
|--------|----------|----------|
| D-SPEC-01/02 | 恢复 `CalendarId`/`GrainId` 为 Literal 类型 | `specs.py`, `research.py`, `materialization.py` |
| C-LC-01/02 | 扩展 `DerivedVersionStatus` 为 5 个枚举值，消除字符串分裂 | `models.py`, `publication.py`, `reader.py` |
| C-TX-01/02 | 引入 `UnitOfWork` 模式，`atomic_bytes_write()` 原子写入 | `unit_of_work.py`, `io.py`, `_json_records.py` |
| C-CC-01/02 | 重构缓存为 L1→L2→compile 三级检查，显式 `compute_compile_cache_key()` | `compile_cache.py`, `compiler.py` |
| C-FA-01 | `MissingDependencyError` 替代静默 fallback | `materialization.py` |

---

## Phase 2: 结构重构（Week 2）

### 问题清单

| ID | 问题 | 类型 | 严重程度 |
|----|------|------|----------|
| **Q-RESP-01** | `DerivedMaterializationService` 880+ 行，职责过重 | 工程 | 高 |
| **Q-RESP-02** | Port 层直接操作文件系统 | 工程 | 中 |
| **Q-RESP-03** | `compile_cache.py` 位置存疑（应在 DataHub） | 工程 | 低 |
| **C-CW-01** | `compute_start/end` 被 `request_start/end` 覆盖 | 核心 | 中 |
| **C-RV-01** | `resolve_serving_version()` 静默回退 | 核心 | 高 |
| **C-RV-02** | research 版本解析可能绑定未发布版本 | 核心 | 高 |
| **Q-ABS-01** | `DerivedInputProvider` 参数过多（4 个） | 工程 | 低 |
| **Q-ABS-02** | `InMemoryDerivedInputProvider` 忽略 3/4 参数 | 工程 | 低 |

---

### 2.1 Q-RESP-01/02/03: 职责拆分与下沉

**当前问题**：

```python
# materialization.py - 880+ 行，职责过多
class DerivedMaterializationService:
    def materialize(self, request) -> Result:
        # 1. 编译（compile）
        # 2. 执行（execute）
        # 3. 写入 artifact（_write_durable_artifacts）  ← 应下沉到 DataHub
        # 4. 保存 metadata（_finalize_durable_run）
        # 5. 注册依赖（_persist_dependencies）
```

**修复方案**：拆分为 4 个协作对象

```
当前架构:
┌─────────────────────────────────────────────┐
│  DerivedMaterializationService (880+ 行)   │
│  - 编译 + 执行 + 写文件 + 元数据 + 依赖     │
└─────────────────────────────────────────────┘

目标架构:
┌─────────────────────────────────────────────┐
│  Port 层（编排）                            │
│  ┌─────────────────────────────────────────┐│
│  │ DerivedMaterializationOrchestrator      ││
│  │ - 协调各组件                            ││
│  │ - 管理事务边界                          ││
│  └─────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
┌─────────┐   ┌─────────┐   ┌─────────────┐
│ DataHub │   │ DataHub │   │ DataHub     │
│ Service │   │ Service │   │ Store       │
├─────────┤   ├─────────┤   ├─────────────┤
│Compile  │   │Catalog  │   │Artifact     │
│Cache    │   │Service  │   │Writer       │
└─────────┘   └─────────┘   └─────────────┘
```

**新增组件**：

```python
# 1. DataHub 层 - ArtifactWriter
# packages/datahub/src/ditto_datahub/stores/runtime/derived_artifact_writer.py

@dataclass(frozen=True)
class PartitionInfo:
    """分区写入结果"""
    partition_key: str
    partition_path: str
    row_count: int
    checksum: str | None


class DerivedArtifactWriter:
    """Artifact 持久化写入器（下沉到 DataHub）"""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    def write_partitions(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        frame: pl.DataFrame,
    ) -> tuple[PartitionInfo, ...]:
        """写入分区文件，返回分区信息"""
        ...

    def write_metadata(
        self,
        *,
        spec: DerivedSpec,
        run_id: str,
        compile_identity: CompileIdentity,
        analysis: Analysis,
        partitions: tuple[PartitionInfo, ...],
    ) -> None:
        """写入运行元数据"""
        ...


# 2. Port 层 - Orchestrator（精简版）
# apps/port/src/ditto_port/services/derived/materialization_orchestrator.py

class DerivedMaterializationOrchestrator:
    """物化编排器（只做协调，不直接操作文件）"""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        compile_cache_service: CompileCacheService,  # 移到 DataHub
        artifact_writer: DerivedArtifactWriter,       # 新增
        input_provider: DerivedInputProvider,
    ) -> None:
        ...

    def materialize(
        self,
        request: DerivedMaterializationRequest,
    ) -> DerivedMaterializationResult:
        """编排物化流程"""
        # 1. 获取 spec
        # 2. 编译（调用 compile_cache_service）
        # 3. 加载输入（调用 input_provider）
        # 4. 执行计算
        # 5. 写入 artifact（调用 artifact_writer）
        # 6. 更新元数据（调用 catalog_service）
```

**迁移步骤**：

1. 新增 `DerivedArtifactWriter`（DataHub 层）
2. 新增 `DerivedMaterializationOrchestrator`（Port 层）
3. 直接替换所有调用点
4. 删除旧 `DerivedMaterializationService`

---

### 2.2 C-CW-01: Compute Window 修复

**当前问题**：

```python
# materialization.py:357-358
compute_start=request.request_start,
compute_end=request.request_end,
```

问题：`request_start/end` 是用户请求范围，不包含 lookback。实际计算窗口应该使用 `plan.compute_start/end`。

**修复方案**：

```python
# 修复后
compute_start=plan.compute_start,  # 包含 lookback 回退
compute_end=plan.compute_end,
```

**代码修改点**：

| 文件 | 行号 | 修改 |
|------|------|------|
| `materialization.py` | 357-358 | 使用 `plan.compute_start/end` |
| `materialization.py` | 453-454 | 同上（durable 路径） |

**测试用例**：

```python
def test_compute_window_includes_lookback():
    request = DerivedMaterializationRequest(
        derived_id="test",
        version=1,
        request_start="2024-01-20",
        request_end="2024-01-31",
        ...
    )
    result = orchestrator.materialize(request)

    # compute_start 应该早于 request_start（包含 lookback）
    assert result.compute_start < request.request_start
    # compute_end 应该等于 request_end
    assert result.compute_end == request.request_end
```

---

### 2.3 C-RV-01/02: 版本解析显式校验

**当前问题**：

```python
# artifact_reader.py:48
version = primary_online or self._resolve_active_version(derived_id)
```

问题：无 primary online 时静默回退到 `active_version`，可能绑定未发布版本。

**修复方案**：引入显式版本解析策略

```python
# packages/datahub/src/ditto_datahub/services/derived/artifact_reader.py

class VersionResolutionStrategy(StrEnum):
    """版本解析策略"""
    PRIMARY_ONLINE_ONLY = "primary_online_only"  # 只使用 primary online
    FALLBACK_TO_ACTIVE = "fallback_to_active"    # 回退到 active（需显式声明）
    EXPLICIT_VERSION = "explicit_version"        # 显式指定版本


class VersionResolutionError(Exception):
    """版本解析失败异常"""
    pass


class DerivedArtifactReader:
    def resolve_serving_version(
        self,
        derived_id: str,
        *,
        strategy: VersionResolutionStrategy = VersionResolutionStrategy.PRIMARY_ONLINE_ONLY,
        explicit_version: int | None = None,
    ) -> int:
        """解析服务版本，使用显式策略"""

        if strategy == VersionResolutionStrategy.EXPLICIT_VERSION:
            if explicit_version is None:
                raise VersionResolutionError(
                    f"explicit_version required for strategy={strategy}"
                )
            self._require_catalog_entry(derived_id, explicit_version)
            return explicit_version

        if strategy == VersionResolutionStrategy.PRIMARY_ONLINE_ONLY:
            primary_online = self._find_primary_online_version(derived_id)
            if primary_online is None:
                raise VersionResolutionError(
                    f"No primary online version found for derived_id={derived_id}. "
                    f"Use FALLBACK_TO_ACTIVE strategy or specify explicit version."
                )
            return primary_online

        if strategy == VersionResolutionStrategy.FALLBACK_TO_ACTIVE:
            primary_online = self._find_primary_online_version(derived_id)
            if primary_online is not None:
                return primary_online
            # 显式回退到 active
            return self._resolve_active_version(derived_id)

        raise ValueError(f"Unknown strategy: {strategy}")
```

**调用点修改**：

```python
# research.py - 构建研究快照时必须显式指定版本
version = self._artifact_reader.resolve_serving_version(
    derived_id,
    strategy=VersionResolutionStrategy.EXPLICIT_VERSION,
    explicit_version=requested_version,
)

# query_facade.py - 在线查询默认 primary online
version = self._artifact_reader.resolve_serving_version(
    derived_id,
    strategy=VersionResolutionStrategy.PRIMARY_ONLINE_ONLY,
)
```

---

### 2.4 Q-ABS-01/02: Input Provider 重构

**当前问题**：

```python
# 4 个参数，调用者负担重
class DerivedInputProvider(Protocol):
    def load_input(
        self,
        *,
        spec: DerivedSpec,
        request: DerivedMaterializationRequest,
        plan: DerivedExecutionPlan,
        dependencies: tuple[str, ...],
    ) -> pl.DataFrame: ...

# InMemory 实现忽略 3/4 参数
class InMemoryDerivedInputProvider:
    def load_input(self, *, spec, request, plan, dependencies):
        del request  # 忽略
        del plan     # 忽略
        del dependencies  # 忽略
        return self._frames[spec.id]
```

**修复方案**：封装为参数对象

```python
# apps/port/src/ditto_port/services/derived/input_provider.py

@dataclass(frozen=True)
class InputContext:
    """输入加载上下文"""
    spec: DerivedSpec
    request: DerivedMaterializationRequest
    plan: DerivedExecutionPlan
    dependencies: tuple[str, ...]


class DerivedInputProvider(Protocol):
    """Input seam used by the materialization service."""

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load the raw input frame for one derived request."""
        ...


class InMemoryDerivedInputProvider:
    """Test input provider backed by an in-memory frame mapping."""

    def __init__(self, frames: dict[str, pl.DataFrame]) -> None:
        self._frames = frames

    def load_input(self, context: InputContext) -> pl.DataFrame:
        """Load one in-memory input frame."""
        frame = self._frames.get(context.spec.id)
        if frame is None:
            raise KeyError(f"missing input frame for derived_id={context.spec.id}")
        return frame
```

---

### 2.5 Q-RESP-03: compile_cache 下沉

**当前位置**：`apps/port/src/ditto_port/services/derived/compile_cache.py`

**目标位置**：`packages/datahub/src/ditto_datahub/services/derived/compile_cache_service.py`

**理由**：
- 编译缓存是持久化能力，属于 DataHub 层
- Port 层只应该调用 Service，不应直接管理缓存

**迁移步骤**：
1. 将 `SQLiteCompileCacheService` 移到 DataHub
2. 更新 Port 层导入
3. 更新 DI 容器配置

---

### Phase 2 修复顺序

```
Day 1-2: 职责拆分
├── 新增 DerivedArtifactWriter（DataHub）
├── 重构 DerivedMaterializationOrchestrator（Port）
└── 直接替换，删除旧实现

Day 2-3: Compute Window + 版本解析
├── C-CW-01: 修复 compute_start/end
├── C-RV-01/02: 引入版本解析策略
└── 更新调用点

Day 3-4: Input Provider 重构
├── Q-ABS-01/02: 封装 InputContext
└── 更新所有实现

Day 4-5: compile_cache 下沉
├── Q-RESP-03: 移动文件
├── 更新导入
└── 更新 DI 容器
```

---

### Phase 2 验收标准

| 检查项 | 标准 |
|--------|------|
| 类型检查 | `basedpyright` 无错误 |
| 分层边界 | `arch-check` 通过（Port 层无直接文件操作） |
| 单元测试 | 所有新增/修改代码覆盖率 ≥ 80% |
| 集成测试 | 版本解析策略验证通过 |
| Lint | `ruff` 无错误 |

---

## Phase 3: 语义补全（Week 3）

### 问题清单

| ID | 问题 | 类型 | 严重程度 |
|----|------|------|----------|
| **I-CASC-01** | 当前只是一跳 repair 队列，非 cascade protocol | 实现 | 中 |
| **I-CASC-02** | 无 stale/recomputing 状态机 | 实现 | 中 |
| **I-CASC-03** | 无 cycle guard、无微批合并 | 实现 | 低 |
| **I-RES-01** | `dataset_spec_version` 硬编码为 `1` | 实现 | 中 |
| **I-RES-02** | `SpineSpec`/`ResearchDatasetSpec` 无 `version` 字段 | 实现 | 中 |
| **I-RES-03** | `DatasetSnapshot` 不是严格的 spec-versioned contract | 实现 | 中 |
| **D-SPEC-03** | `DerivedSpec` 职责边界模糊 | 设计 | 中 |
| **D-SPEC-04** | `availability_time` 缺席核心模型 | 设计 | 中 |
| **I-INCR-01** | `requires_full_day=True` 未完整消费 | 实现 | 中 |
| **I-INCR-02** | CS 因子全截面放大逻辑未实现 | 实现 | 中 |

---

### 3.1 I-CASC-01/02/03: Invalidation Cascade Protocol

**当前问题**：

```python
# invalidation.py - 只遍历直接依赖，无级联传播
def enqueue(self, event: DerivedInvalidationEvent) -> str:
    for dependency in self._catalog_service.list_dependencies_by_ref(...):
        # 只是一跳，没有 BFS 分层传播
        records.append(...)

def repair_pending(self, limit: int):
    # 没有状态机，只有 pending/processed
    # 没有 cycle guard
    # 没有微批合并
```

**ADR-035 承诺的 Cascade Protocol**：

1. BFS 分层传播（depth=0 → depth=1 → depth=2...）
2. 状态机：fresh → stale → recomputing → healed
3. Cycle guard：visited 去重 + max_depth 保护
4. 微批合并：同目标事件合并

**修复方案**：实现完整 Cascade Protocol

```python
# apps/port/src/ditto_port/services/derived/cascade_protocol.py

from collections import deque
from enum import StrEnum

class CascadeStatus(StrEnum):
    """Cascade 传播状态"""
    FRESH = "fresh"
    STALE = "stale"
    RECOMPUTING = "recomputing"
    HEALED = "healed"


class CascadeDepthExceededError(Exception):
    """级联深度超限异常"""
    pass


class CycleDetectedError(Exception):
    """循环依赖检测异常"""
    pass


REALTIME_CASCADE_MAX_DEPTH = 5


class InvalidationCascadeService:
    """Invalidation 级联传播服务"""

    def __init__(
        self,
        *,
        catalog_service: DerivedCatalogService,
        materialization_service: DerivedMaterializationService,
        max_depth: int = REALTIME_CASCADE_MAX_DEPTH,
    ) -> None:
        self._catalog_service = catalog_service
        self._materialization_service = materialization_service
        self._max_depth = max_depth

    def propagate(
        self,
        event: DerivedInvalidationEvent,
    ) -> tuple[str, ...]:
        """BFS 分层传播失效事件"""
        created_at = datetime.now(UTC).isoformat()
        all_records: list[DerivedInvalidationRecord] = []
        visited: set[str] = set()

        # BFS 队列：(derived_id, version, depth)
        queue = deque([(event.root_dependency_ref, 0, 0)])

        while queue:
            current_id, current_version, depth = queue.popleft()

            # Cycle guard
            if current_id in visited:
                self._emit_cycle_alert(current_id)
                continue
            visited.add(current_id)

            # Depth guard
            if depth > self._max_depth:
                self._emit_depth_alert(current_id, depth)
                continue

            # 标记当前节点为 stale
            self._mark_stale(current_id, current_version)

            # 创建 invalidation 记录
            record = self._create_invalidation_record(
                event, current_id, current_version, depth, created_at
            )
            all_records.append(record)

            # 查找下游依赖并加入队列
            for dep in self._catalog_service.list_downstream_dependencies(current_id):
                queue.append((dep.derived_id, dep.version, depth + 1))

        # 微批合并：同 derived_id 的多个事件合并
        merged = self._merge_batch_events(all_records)
        self._catalog_service.save_invalidations(tuple(merged))

        return tuple(r.invalidation_id for r in merged)

    def repair_batch(
        self,
        batch_size: int = 10,
    ) -> tuple[DerivedMaterializationResult, ...]:
        """批量修复 stale 状态的 invalidation"""
        results: list[DerivedMaterializationResult] = []

        # 按深度排序处理
        pending = sorted(
            self._catalog_service.list_pending_invalidations(),
            key=lambda r: r.depth,
        )

        for invalidation in pending[:batch_size]:
            # 状态转换：stale → recomputing
            self._mark_recomputing(invalidation.derived_id)

            try:
                result = self._materialization_service.materialize(...)
                # 状态转换：recomputing → healed
                self._mark_healed(invalidation.derived_id)
                results.append(result)
            except Exception as e:
                # 失败时保持 stale 状态
                self._mark_stale(invalidation.derived_id, invalidation.version)
                raise

        return tuple(results)

    def _merge_batch_events(
        self,
        records: list[DerivedInvalidationRecord],
    ) -> list[DerivedInvalidationRecord]:
        """微批合并同目标事件"""
        merged: dict[str, DerivedInvalidationRecord] = {}
        for record in records:
            key = f"{record.derived_id}:{record.version}"
            if key not in merged:
                merged[key] = record
            else:
                # 合并 affected 范围
                existing = merged[key]
                merged[key] = DerivedInvalidationRecord(
                    ...,
                    affected_start=min(existing.affected_start, record.affected_start),
                    affected_end=max(existing.affected_end, record.affected_end),
                )
        return list(merged.values())
```

---

### 3.2 I-RES-01/02/03: Research Spec Versioning

**当前问题**：

```python
# research.py
_DATASET_SPEC_VERSION = 1  # 硬编码

# SpineSpec / ResearchDatasetSpec 没有 version 字段
@dataclass(frozen=True)
class SpineSpec:
    spine_id: str
    universe_id: str
    # 缺少 version 字段！
```

**修复方案**：添加版本字段

```python
# packages/core/src/ditto_core/engine/research.py

@dataclass(frozen=True)
class SpineSpec:
    """Frozen definition of a research spine."""

    spine_id: str
    universe_id: str
    version: int = 1  # 新增版本字段
    calendar: str = "cn_stock"
    grain: str = "1d"
    entity_key: str = "instrument_id"
    description: str | None = None


@dataclass(frozen=True)
class ResearchDatasetSpec:
    """Frozen definition of a research dataset build."""

    dataset_id: str
    version: int = 1  # 新增版本字段
    spine_id: str
    derived_ids: tuple[str, ...]
    join_policy: str = "left_preserving_pit"
    known_at_policy: KnownAtPolicy = KnownAtPolicy.SAMPLE_TIME
    late_arrival_policy: LateArrivalPolicy = LateArrivalPolicy.REQUIRE_REBUILD
    description: str | None = None


@dataclass(frozen=True)
class DatasetSnapshot:
    """Immutable frozen dataset snapshot."""

    snapshot_id: str
    dataset_id: str
    dataset_spec_version: int  # 从 ResearchDatasetSpec.version 获取
    spine_spec_version: int    # 新增：记录 spine 版本
    spine_snapshot_id: str
    ...
    resolved_versions: dict[str, int]  # 每个 derived_id 的精确版本
    resolved_inputs: tuple[dict[str, str | int], ...]  # 精确输入快照
    spec_hash: str  # spec 内容 hash，用于验证契约
```

---

### 3.3 D-SPEC-03/04: DerivedSpec 语义补全

**当前问题**：

```python
# DerivedSpec 既承载计算语义又隐含执行策略
@dataclass(frozen=True)
class DerivedSpec:
    ...
    pit_required: bool | None = None  # 执行策略，应该在 planner 层
    normalization_preset: str | None = None  # 执行策略

# availability_time 缺席
# ADR-041 定义了 availability_time 语义，但 DerivedSpec 没有
```

**修复方案**：分离语义与策略，添加时间语义

```python
# packages/core/src/ditto_core/engine/specs.py

@dataclass(frozen=True)
class TimeSpec:
    """时间语义规范"""
    event_time_key: str  # 业务事件时间键
    availability_time_key: str | None = None  # 数据可用时间键
    # 如果 availability_time_key 为 None，则 availability_time == event_time


@dataclass(frozen=True)
class DerivedSpec:
    """Unified derived semantic contract."""

    # 核心语义（不变）
    id: str
    version: int
    role: DerivedRole
    materialization_profile: MaterializationProfile
    expression: str
    entity_keys: tuple[str, ...] = field(default_factory=lambda: ("instrument_id",))
    grain: GrainId = "1d"
    time_keys: tuple[str, ...] | None = None
    calendar: CalendarId = "cn_stock"

    # 新增：时间语义
    time_spec: TimeSpec | None = None

    # 描述
    description: str | None = None

    # 操作符版本
    operator_versions: dict[str, str] = field(default_factory=dict)

    # 移除执行策略字段（pit_required, normalization_preset）
    # 这些应该在 MaterializationProfile 或 planner 层处理


# 执行策略移到独立配置
@dataclass(frozen=True)
class ExecutionPolicy:
    """执行策略配置"""
    pit_required: bool = True
    normalization_preset: str = "default"
```

---

### 3.4 I-INCR-01/02: 增量计算补全

**I-INCR-01: requires_full_day 消费**

```python
# planner.py - 消费 requires_full_day

class DerivedExecutionPlanner:
    def plan(self, spec: DerivedSpec, request: DerivedMaterializationRequest) -> DerivedExecutionPlan:
        analysis = self._analyzer.analyze(spec.expression)

        # 检查是否需要整日重算
        requires_full_day = any(
            op.requires_full_day for op in analysis.required_operators
        )

        if requires_full_day and request.mode == DerivedRunMode.INCREMENTAL:
            # 调整计算窗口为完整交易日
            request_start = self._adjust_to_trading_day_start(request.request_start)
            request_end = self._adjust_to_trading_day_end(request.request_end)

        return DerivedExecutionPlan(
            ...,
            requires_full_day=requires_full_day,
        )
```

**I-INCR-02: CS 因子全截面放大**

```python
# executor.py - CS 因子全截面放大

def _apply_cs_amplification(
    frame: pl.DataFrame,
    spec: DerivedSpec,
    analysis: Analysis,
) -> pl.DataFrame:
    """CS 因子全截面放大"""
    if not analysis.is_cross_sectional:
        return frame

    # 获取所有需要的 instruments
    required_instruments = spec.required_instruments

    # 确保每个 trade_date 都有所有 instruments
    all_dates = frame.select(pl.col("trade_date").unique()).to_series()
    cross_product = all_dates.to_frame().join(
        pl.DataFrame({"instrument_id": required_instruments}),
        how="cross",
    )

    # Left join 填充缺失值
    result = cross_product.join(
        frame,
        on=["trade_date", "instrument_id"],
        how="left",
    )

    return result
```

---

### Phase 3 修复顺序

```
Day 1-2: Cascade Protocol
├── I-CASC-01: 实现 BFS 分层传播
├── I-CASC-02: 实现状态机（fresh → stale → recomputing → healed）
└── I-CASC-03: Cycle guard + 微批合并

Day 2-3: Research Versioning
├── I-RES-01/02: 添加 version 字段
├── I-RES-03: 完善契约
└── 更新构建逻辑

Day 3-4: 时间语义 + DerivedSpec 重构
├── D-SPEC-03: 分离语义与执行策略
├── D-SPEC-04: 添加 TimeSpec
└── 迁移现有代码

Day 4-5: 增量计算补全
├── I-INCR-01: requires_full_day 消费
└── I-INCR-02: CS 因子全截面放大
```

---

### Phase 3 验收标准

| 检查项 | 标准 |
|--------|------|
| Cascade 测试 | BFS 分层、状态机、cycle guard 均有单元测试 |
| Versioning 测试 | Spec 版本变更触发重建 |
| 增量计算测试 | requires_full_day 和 CS 放大正确执行 |
| 集成测试 | 完整 cascade 链路验证通过 |

---

## Phase 4: 架构完善（Week 4）

### 问题清单

| ID | 问题 | 类型 | 严重程度 |
|----|------|------|----------|
| **D-HEAT-01** | QuestDB 热层未实现 | 设计 | 中 |
| **D-HEAT-02** | Kvrocks 状态存储未实现 | 设计 | 中 |
| **D-HEAT-03** | `RuntimeMode` 空解析模式 | 设计 | 低 |
| **D-HEAT-04** | artifact-first 缺少迁移计划 | 设计 | 低 |
| **D-ADR-01** | ADR 过度碎片化（43+ 文档） | 设计 | 低 |
| **D-ADR-02** | 部分状态漂移（暂缓无重启条件） | 设计 | 低 |
| **D-ADR-03** | ADR 交叉引用复杂 | 设计 | 低 |
| **Q-ERR-01** | 异常类型混用 | 工程 | 中 |
| **Q-NAME-01** | 命名不一致（Service vs Orchestrator） | 工程 | 低 |
| **Q-NAME-02** | 测试文件名实不符 | 工程 | 低 |
| **I-EXPR-01** | DAG/CSE 优化未实现 | 实现 | 低（标记为 Phase 5+） |

### 全局约束

> **所有修改不需要考虑向后兼容，直接迁移重构。**

---

### 4.1 D-HEAT-01/02/03: 热层接口预留

**当前状态**：
- QuestDB 热层和 Kvrocks 状态存储设计完整（ADR-028/040），实现为 Phase 5+
- `RuntimeMode` 解析后未消费（`query_facade.py:85`）
- artifact-first 功能未使用，D-HEAT-04 移除

**修复方案**：定义接口预留 + RuntimeMode 消费

```python
# packages/datahub/src/ditto_datahub/services/hot_layer/__init__.py

class HotLayerReader(Protocol):
    """热层读取协议（QuestDB）"""

    def is_available(self) -> bool:
        """检查热层是否可用"""
        ...

    def read_latest(
        self,
        *,
        derived_id: str,
        instrument_ids: tuple[int, ...] | None,
        as_of: str | None,
    ) -> pl.DataFrame:
        """从热层读取最新值"""
        ...


class HotLayerWriter(Protocol):
    """热层写入协议（QuestDB）"""

    def write_frame(
        self,
        *,
        derived_id: str,
        version: int,
        frame: pl.DataFrame,
    ) -> int:
        """写入热层，返回写入行数"""
        ...


class StateStore(Protocol):
    """状态存储协议（Kvrocks）"""

    def get(self, key: str) -> bytes | None:
        """获取状态"""
        ...

    def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> None:
        """设置状态"""
        ...


# Phase 5+ 前的占位实现
class UnavailableHotLayerReader:
    """不可用的热层读取器"""

    def is_available(self) -> bool:
        return False

    def read_latest(self, **kwargs: object) -> pl.DataFrame:
        raise NotImplementedError("Hot layer not implemented yet")


class UnavailableStateStore:
    """不可用的状态存储"""

    def get(self, key: str) -> bytes | None:
        raise NotImplementedError("State store not implemented yet")

    def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> None:
        raise NotImplementedError("State store not implemented yet")
```

**RuntimeMode 消费**：

```python
# query_facade.py - 修复后

class DerivedQueryFacade:
    """Use-case facade for unified derived query entrypoints."""

    def __init__(
        self,
        service: DerivedQueryService,
        hot_layer: HotLayerReader,  # 新增
        mode_resolver: RuntimeModeResolver,
    ) -> None:
        self._service = service
        self._hot_layer = hot_layer
        self._mode_resolver = mode_resolver

    def get_latest(self, request: LatestDerivedRequest) -> DerivedLatestResult:
        mode = self._mode_resolver.resolve()

        # 尝试热层
        if mode == RuntimeMode.ONLINE and self._hot_layer.is_available():
            try:
                data = self._hot_layer.read_latest(
                    derived_ids=request.derived_ids,
                    instrument_ids=request.instrument_ids,
                    as_of=_temporal_to_iso(request.as_of),
                )
                if not data.is_empty():
                    return DerivedLatestResult(data=data)
            except Exception:
                pass  # 热层失败，降级到冷层

        # 冷层回退
        query = DerivedLatestQuery(...)
        return DerivedLatestResult(data=self._service.find_latest(query))
```

---

### 4.2 Q-ERR-01: 统一异常类型体系

**当前问题**：

```python
# 混用多种异常类型
raise KeyError(f"derived spec not found for derived_id={derived_id}")
raise ValueError(f"shadow baseline not found for derived_id={derived_id}")
raise NotImplementedError(f"Phase 3 input backend not wired")
```

**修复方案**：定义统一异常层次

```python
# packages/core/src/ditto_core/errors.py

class DerivedError(Exception):
    """Base exception for all derived-related errors."""

    def __init__(self, message: str, *, derived_id: str | None = None) -> None:
        self.derived_id = derived_id
        super().__init__(message)


class DerivedNotFoundError(DerivedError):
    """Raised when a derived entity is not found."""

    def __init__(
        self,
        *,
        derived_id: str,
        version: int | None = None,
    ) -> None:
        self.version = version
        msg = f"Derived not found: derived_id={derived_id}"
        if version is not None:
            msg += f" version={version}"
        super().__init__(msg, derived_id=derived_id)


class DerivedVersionError(DerivedError):
    """Raised when version resolution fails."""

    def __init__(
        self,
        *,
        derived_id: str,
        reason: str,
    ) -> None:
        self.reason = reason
        super().__init__(
            f"Version resolution failed for derived_id={derived_id}: {reason}",
            derived_id=derived_id,
        )


class DerivedMaterializationError(DerivedError):
    """Raised when materialization fails."""

    def __init__(
        self,
        *,
        derived_id: str,
        version: int,
        reason: str,
    ) -> None:
        self.version = version
        self.reason = reason
        super().__init__(
            f"Materialization failed for derived_id={derived_id} "
            f"version={version}: {reason}",
            derived_id=derived_id,
        )


class DerivedDependencyError(DerivedError):
    """Raised when a dependency is missing or invalid."""

    def __init__(
        self,
        *,
        derived_id: str,
        missing: list[str],
        available: list[str],
    ) -> None:
        self.missing = missing
        self.available = available
        super().__init__(
            f"Missing dependencies for derived_id={derived_id}: {missing}. "
            f"Available: {available}",
            derived_id=derived_id,
        )


class DerivedNotImplementedError(DerivedError):
    """Raised when a feature is not yet implemented."""

    def __init__(
        self,
        *,
        feature: str,
        derived_id: str | None = None,
    ) -> None:
        self.feature = feature
        super().__init__(
            f"Feature not implemented: {feature}",
            derived_id=derived_id,
        )


class DerivedValidationError(DerivedError):
    """Raised when validation fails."""

    def __init__(
        self,
        *,
        derived_id: str | None = None,
        field: str,
        value: str,
        reason: str,
    ) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(
            f"Validation failed for field={field} value={value}: {reason}",
            derived_id=derived_id,
        )
```

**迁移示例**：

```python
# 修改前
if spec_record is None:
    raise KeyError(f"derived spec not found for derived_id={derived_id}")

# 修改后
if spec_record is None:
    raise DerivedNotFoundError(derived_id=derived_id, version=version)
```

**替换规则**：

| 旧异常 | 新异常 | 条件 |
|--------|--------|------|
| `KeyError("... not found ...")` | `DerivedNotFoundError` | 查询不到实体 |
| `ValueError("... resolution ...")` | `DerivedVersionError` | 版本解析失败 |
| `ValueError("... validation ...")` | `DerivedValidationError` | 校验失败 |
| `NotImplementedError("Phase ...")` | `DerivedNotImplementedError` | 功能未实现 |
| `ValueError("... materialized ...")` | `DerivedMaterializationError` | 物化失败 |
| `ValueError("... dependency ...")` | `DerivedDependencyError` | 依赖缺失 |

---

### 4.3 Q-NAME-01/02: 命名对齐

**Q-NAME-01: Service → Orchestrator**

```python
# 直接替换，不留别名
# 修改前
class DerivedMaterializationService: ...

# 修改后
class DerivedMaterializationOrchestrator: ...
```

**Q-NAME-02: 测试文件命名对齐**

```
# 直接重命名，不留旧文件
test_materialization_facade_unit.py
  → test_materialization_orchestrator_unit.py
```

---

### 4.4 D-ADR-01/02/03: ADR 文档整理

**D-ADR-01: 按主题归组**

```
docs/design/unified-feature-factor-engine/decisions/
├── 00-index.md                    # 导航索引
├── core/
│   ├── adr-032-semantic-model.md
│   ├── adr-024-versioning.md
│   └── adr-034-publication-lifecycle.md
├── computation/
│   ├── adr-002-operator-system.md
│   ├── adr-004-expression-syntax.md
│   ├── adr-006-incremental-computation.md
│   └── adr-012-operator-incremental-impl.md
├── storage/
│   ├── adr-016-catalog-storage.md
│   ├── adr-026-duckdb-positioning.md
│   └── adr-028-questdb-hot-tables.md
├── quality/
│   ├── adr-021-pit-consistency.md
│   ├── adr-022-correction-handling.md
│   └── adr-036-quality-gates.md
└── research/
    ├── adr-041-research-dataset-spine-availability-contract.md
    └── adr-042-shadow-publish-dual-read-diff-protocol.md
```

**D-ADR-02: 暂缓状态处理**

为所有 `⏸️ 暂缓` 状态的 ADR 添加重启条件和预计时间线。

**D-ADR-03: 导航优化**

更新 README 导航结构，提供清晰的阅读路径。

---

### 4.5 I-EXPR-01: DAG/CSE 优化

**标记为 Phase 5+**，不在本次整改范围内。

理由：当前性能已满足需求，复杂度高，应先稳定核心语义。

---

### Phase 4 修复顺序

```
Day 1: 热层接口预留
├── D-HEAT-01/02: 定义接口协议
├── D-HEAT-03: RuntimeMode 消费
└── D-HEAT-04: 移除（功能未使用）

Day 2: 异常体系
├── Q-ERR-01: 定义异常层次
├── 全局替换所有 raise 语句
└── 更新测试

Day 3: 命名对齐
├── Q-NAME-01: Service → Orchestrator
├── Q-NAME-02: 测试文件重命名
└── 更新导入

Day 4-5: ADR 整理
├── D-ADR-01: 归组整理
├── D-ADR-02: 暂缓状态处理
└── D-ADR-03: 导航优化
```

---

### Phase 4 验收标准

| 检查项 | 标准 |
|--------|------|
| 热层接口 | Protocol 定义完整，占位实现可工作 |
| 异常体系 | 全局无裸 `KeyError`/`ValueError`/`NotImplementedError` |
| 命名一致性 | 所有文件/类名对齐 |
| ADR 导航 | 索引文件存在，阅读路径清晰 |
| 完整验证 | `pixi run -e dev check` 通过 |

---

## 全局原则补充

> **所有修改不需要考虑向后兼容。直接迁移重构，不留别名、不保留旧接口。**

---

## 相关文档

- [技术债务审查](../design/unified-feature-factor-engine/technical-debt-review-2026-03-14.md)
- [ADR-032: 统一派生语义模型](../design/unified-feature-factor-engine/decisions/adr-032-unified-derived-semantic-model.md)
- [ADR-035: 失效传播级联协议](../design/unified-feature-factor-engine/decisions/adr-035-invalidation-cascade.md)
- [ADR-041: Research Dataset 契约](../design/unified-feature-factor-engine/decisions/adr-041-research-dataset-spine-availability-contract.md)
