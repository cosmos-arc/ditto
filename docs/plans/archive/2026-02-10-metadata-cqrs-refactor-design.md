# DataHub Metadata 域 CQRS 重构设计文档

**日期**: 2026-02-10
**阶段**: 阶段 7 - DI 容器更新（含未拆分 Store 的 CQRS 实现）
**状态**: 设计完成

---

## 1. 概述

### 1.1 重构目标

将 Metadata 域的 Store 层完全迁移到 CQRS 模式，并更新 Port 层的 DI 容器配置。

### 1.2 关键发现

**IdentityStore 是冗余代码**：
- 使用不存在的 `identity_mapping` 表（schema 中只有 `instrument_mapping`）
- 功能完全被 InstrumentStore 覆盖
- 需要完全删除

**已完成 CQRS 拆分的 Store**：
- CalendarStore, IndustryBasicStore, InstrumentStore（已有 Reader/Writer，Store 已 DEPRECATED）
- EtfNavStore, EtfAdjFactorStore, IndexBarsStore, IndexConstituentStore（Facade 模式）

**需要处理的 Store**：
- IdentityStore - 删除（冗余）
- UniverseStore - 创建 Reader/Writer，删除旧 Store
- IndustryMappingStore - 创建 Reader/Writer，删除旧 Store

---

## 2. 文件变更清单

### 2.1 需要删除的文件

| 文件 | 原因 |
|------|------|
| `stores/metadata/identity/identity_store.py` | 冗余，功能被 InstrumentStore 覆盖 |
| `stores/metadata/identity/identity_reader.py` | 配套删除 |
| `stores/metadata/identity/identity_writer.py` | 配套删除 |
| `stores/metadata/universe/universe_store.py` | 将被 UniverseReader/Writer 替代 |
| `stores/metadata/industry/industry_mapping_store.py` | 将被 IndustryMappingReader/Writer 替代 |

### 2.2 需要创建的文件

| 文件 | 说明 |
|------|------|
| `stores/metadata/universe/universe_reader.py` | Universe 读取操作 |
| `stores/metadata/universe/universe_writer.py` | Universe 写入操作 |
| `stores/metadata/industry/industry_mapping_reader.py` | 行业映射读取操作 |
| `stores/metadata/industry/industry_mapping_writer.py` | 行业映射写入操作 |

### 2.3 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `stores/metadata/identity/__init__.py` | 移除 IdentityStore/Reader/Writer 导出 |
| `stores/metadata/universe/__init__.py` | 导出 Reader/Writer，移除 Store |
| `stores/metadata/industry/__init__.py` | 更新导出，添加 Reader/Writer |
| `services/metadata/metadata_service.py` | 使用 Reader/Writer 替代 Store |
| `apps/port/src/ditto_port/registry/datahub.py` | 更新 DI 容器 provider |
| `apps/port/src/ditto_port/registry/domain.py` | 更新 domain registry |

---

## 3. Reader/Writer 接口设计

### 3.1 UniverseReader

```python
class UniverseReader:
    """标的池读取接口。"""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_universe(self, universe_id: str) -> dict[str, Any] | None:
        """获取标的池定义。"""

    def list_universes(self, universe_type: str | None = None) -> pl.DataFrame:
        """列出所有标的池。"""

    def get_constituents(self, universe_id: str, asof: str | None = None) -> pl.DataFrame:
        """获取标的池成分股（支持 PIT）。"""

    def get_constituent_instrument_ids(self, universe_id: str, asof: str | None = None) -> list[int]:
        """获取成分股 instrument_id 列表。"""
```

### 3.2 UniverseWriter

```python
class UniverseWriter:
    """标的池写入接口。"""

    def __init__(self, client: Any) -> None:
        self._client = client

    def create_universe(
        self,
        universe_id: str,
        name: str,
        description: str | None = None,
        universe_type: str = "custom",
        source_ref: str | None = None,
    ) -> None:
        """创建新标的池。"""

    def add_constituents(self, universe_id: str, records: list) -> int:
        """添加成分股到标的池。"""

    def remove_constituent(self, universe_id: str, instrument_id: int, effective_date: str) -> None:
        """移除成分股（设置 effective_to）。"""
```

### 3.3 IndustryMappingReader

```python
class IndustryMappingReader:
    """行业映射读取接口。"""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_stocks(self, industry_id: str, asof: str | None = None) -> list[int]:
        """获取行业的所有成分股。"""

    def get_stock_industry(self, instrument_id: int, asof: str | None = None) -> dict | None:
        """获取股票所属行业。"""
```

### 3.4 IndustryMappingWriter

```python
class IndustryMappingWriter:
    """行业映射写入接口。"""

    def __init__(self, client: Any) -> None:
        self._client = client

    def update_mapping(
        self,
        instrument_id: int,
        industry_id: str,
        effective_from: str,
        entry_reason: str | None = None,
    ) -> None:
        """更新股票的行业映射。"""
```

---

## 4. MetadataService 更新

### 4.1 构造函数变更

**之前**：
```python
def __init__(
    self,
    instrument_store: InstrumentStore,
    identity_store: IdentityStore,
    calendar_store: CalendarStore,
    industry_basic_store: IndustryBasicStore,
    industry_mapping_store: IndustryMappingStore,
    universe_store: UniverseStore,
    instrument_id_allocator: InstrumentIdAllocator,
) -> None:
```

**之后**：
```python
def __init__(
    self,
    instrument_reader: InstrumentReader,
    instrument_writer: InstrumentWriter,
    calendar_reader: CalendarReader,
    calendar_writer: CalendarWriter,
    industry_reader: IndustryReader,
    industry_writer: IndustryWriter,
    industry_mapping_reader: IndustryMappingReader,
    industry_mapping_writer: IndustryMappingWriter,
    universe_reader: UniverseReader,
    universe_writer: UniverseWriter,
    instrument_id_allocator: InstrumentIdAllocator,
) -> None:
```

### 4.2 方法调用更新

| 之前 | 之后 |
|------|------|
| `self._identity_store.resolve_instrument_id()` | `self._instrument_reader.resolve_instrument_id()` |
| `self._identity_store.resolve_instrument_ids_batch()` | `self._instrument_reader.resolve_instrument_ids_batch()` |
| `self._identity_store.get_source_ticker()` | `self._instrument_reader.get_source_ticker()` |
| `self._universe_store.get_constituents()` | `self._universe_reader.get_constituents()` |
| `self._universe_store.list_universes()` | `self._universe_reader.list_universes()` |
| `self._industry_mapping_store.get_stocks()` | `self._industry_mapping_reader.get_stocks()` |
| `self._industry_mapping_store.get_stock_industry()` | `self._industry_mapping_reader.get_stock_industry()` |

### 4.3 写入操作更新

| 之前 | 之后 |
|------|------|
| `self._universe_store.create_universe()` | `self._universe_writer.create_universe()` |
| `self._universe_store.add_constituents()` | `self._universe_writer.add_constituents()` |
| `self._universe_store.remove_constituent()` | `self._universe_writer.remove_constituent()` |
| `self._industry_mapping_store.update_mapping()` | `self._industry_mapping_writer.update_mapping()` |

---

## 5. DI 容器更新

### 5.1 新增 Provider

```python
# Universe Reader/Writer
@provider
def provide_universe_reader(config: DataRootConfig) -> UniverseReader:
    pool = SQLitePool(str(config.metadata_db_path))
    client = SQLiteClient(pool)
    return UniverseReader(client)

@provider
def provide_universe_writer(config: DataRootConfig) -> UniverseWriter:
    pool = SQLitePool(str(config.metadata_db_path))
    client = SQLiteClient(pool)
    return UniverseWriter(client)

# IndustryMapping Reader/Writer
@provider
def provide_industry_mapping_reader(config: DataRootConfig) -> IndustryMappingReader:
    pool = SQLitePool(str(config.metadata_db_path))
    client = SQLiteClient(pool)
    return IndustryMappingReader(client)

@provider
def provide_industry_mapping_writer(config: DataRootConfig) -> IndustryMappingWriter:
    pool = SQLitePool(str(config.metadata_db_path))
    client = SQLiteClient(pool)
    return IndustryMappingWriter(client)
```

### 5.2 删除 Provider

- `provide_identity_store()`
- `provide_universe_store()`
- `provide_industry_mapping_store()`

### 5.3 更新 MetadataService Provider

```python
@provider
def provide_metadata_service(
    instrument_reader: InstrumentReader = Depends(provide_instrument_reader),
    instrument_writer: InstrumentWriter = Depends(provide_instrument_writer),
    calendar_reader: CalendarReader = Depends(provide_calendar_reader),
    calendar_writer: CalendarWriter = Depends(provide_calendar_writer),
    industry_reader: IndustryReader = Depends(provide_industry_reader),
    industry_writer: IndustryWriter = Depends(provide_industry_writer),
    industry_mapping_reader: IndustryMappingReader = Depends(provide_industry_mapping_reader),
    industry_mapping_writer: IndustryMappingWriter = Depends(provide_industry_mapping_writer),
    universe_reader: UniverseReader = Depends(provide_universe_reader),
    universe_writer: UniverseWriter = Depends(provide_universe_writer),
    instrument_id_allocator: InstrumentIdAllocator = Depends(provide_instrument_id_allocator),
) -> MetadataService:
    return MetadataService(
        instrument_reader=instrument_reader,
        instrument_writer=instrument_writer,
        calendar_reader=calendar_reader,
        calendar_writer=calendar_writer,
        industry_reader=industry_reader,
        industry_writer=industry_writer,
        industry_mapping_reader=industry_mapping_reader,
        industry_mapping_writer=industry_mapping_writer,
        universe_reader=universe_reader,
        universe_writer=universe_writer,
        instrument_id_allocator=instrument_id_allocator,
    )
```

---

## 6. 执行顺序

### 步骤 1：创建新的 Reader/Writer
1. 创建 `UniverseReader`
2. 创建 `UniverseWriter`
3. 创建 `IndustryMappingReader`
4. 创建 `IndustryMappingWriter`

### 步骤 2：更新 __init__.py 文件
1. 更新 `stores/metadata/universe/__init__.py`
2. 更新 `stores/metadata/industry/__init__.py`
3. 更新 `stores/metadata/identity/__init__.py`

### 步骤 3：更新 MetadataService
1. 更新构造函数
2. 更新方法调用（所有 `_xxx_store` → `_xxx_reader` 或 `_xxx_writer`）
3. 更新导入语句

### 步骤 4：更新 DI 容器
1. 添加新的 Provider（UniverseReader/Writer, IndustryMappingReader/Writer）
2. 更新 MetadataService Provider
3. 删除旧的 Provider（IdentityStore, UniverseStore, IndustryMappingStore）
4. 更新 domain.py

### 步骤 5：删除旧文件
1. 删除 `identity_store.py`, `identity_reader.py`, `identity_writer.py`
2. 删除 `universe_store.py`
3. 删除 `industry_mapping_store.py`

### 步骤 6：运行测试验证
```bash
pixi run -e dev check  # lint + fmt + type + test
```

---

## 7. 测试策略

### 7.1 单元测试

为新的 Reader/Writer 编写单元测试：
- `test_universe_reader_unit.py`
- `test_universe_writer_unit.py`
- `test_industry_mapping_reader_unit.py`
- `test_industry_mapping_writer_unit.py`

测试重点：
- PIT 查询逻辑
- 边界条件（空结果、无效参数等）
- 事务回滚（Writer）

### 7.2 集成测试

更新 `test_metadata_service_integration.py`：
- 测试完整的 Reader/Writer 流程
- 测试 DI 容器依赖注入
- 测试端到端的数据流

### 7.3 验证命令

```bash
# 类型检查
pixi run -e dev type

# 代码格式
pixi run -e dev fmt

# Lint
pixi run -e dev lint

# 测试
pixi run -e dev test

# 完整检查
pixi run -e dev check
```

---

## 8. 风险和缓解措施

| 风险 | 缓解措施 |
|------|----------|
| MetadataService 更新遗漏某些方法 | 仔细检查所有 `_identity_store`、`_universe_store`、`_industry_mapping_store` 的调用 |
| DI 容器配置错误 | 运行时检查依赖注入是否正常 |
| 测试覆盖不足 | 为新的 Reader/Writer 编写完整单元测试 |
| PIT 查询逻辑错误 | 单独测试 PIT 查询，确保 effective_from/to 逻辑正确 |

---

## 9. 总结

**核心变更**：
1. 删除 IdentityStore（冗余代码，使用不存在的表）
2. 为 UniverseStore 创建 Reader/Writer
3. 为 IndustryMappingStore 创建 Reader/Writer
4. 更新 MetadataService 使用 Reader/Writer
5. 更新 DI 容器配置

**文件统计**：
- 删除：5 个文件
- 创建：4 个文件
- 修改：6 个文件

**预期收益**：
- 完全一致的 CQRS 架构
- 消除冗余代码（IdentityStore）
- 更清晰的职责分离（Reader/Writer）
- 简化的 DI 容器配置
