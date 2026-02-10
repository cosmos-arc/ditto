# Metadata 域 CQRS 重构设计文档

**日期**: 2026-02-09
**作者**: Claude (Brainstorming Session)
**状态**: 设计完成，待实施

---

## 1. 概述

本文档描述 DataHub Metadata 域 Store 层的 CQRS 拆分设计，将 6 个读写混合的 `*_store.py` 拆分为独立的 Reader/Writer 组件。

## 2. 架构设计

### 2.1 核心组件

| 组件 | 职责 |
|------|------|
| **Reader** | 所有查询操作 (SELECT) |
| **Writer** | 所有写操作 (INSERT/UPDATE/DELETE) + 缓存失效 |
| **CacheManager** | 集中管理所有缓存，线程安全 |
| **Service** | 依赖注入协调 Reader/Writer |

### 2.2 依赖注入模式

```python
# Service 层负责创建和注入依赖
client = SQLiteClient(db_path)
cache_manager = CacheManager()

service = MetadataService(
    instrument_reader=InstrumentReader(client, cache_manager),
    instrument_writer=InstrumentWriter(client, cache_manager),
)
```

### 2.3 CacheManager 接口

```python
class CacheManager:
    """集中缓存管理器，支持多种缓存策略。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, Any] = {}

    # 基础操作
    def get(self, key: str) -> Any | None
    def set(self, key: str, value: Any) -> None
    def invalidate(self, key: str) -> None

    # 模式匹配失效（用于 CalendarStore reload）
    def invalidate_pattern(self, pattern: str) -> None

    # 批量操作
    def invalidate_many(self, keys: list[str]) -> None
    def clear(self) -> None
```

### 2.4 缓存键规范

```
instrument_id:{source_ticker}:{source}:{asof}          # instrument_id 解析
instrument_id_symbol_map:{sorted_ids}                  # symbol 映射
trading_days:{start}:{end}                             # 交易日范围
calendar:day:{date}                                    # 单日数据
identity:{source_ticker}:{source}:{asof}               # identity 解析
industry:all:active={bool}                             # 行业列表
```

## 3. 执行计划

### 3.1 执行顺序（从简到繁）

| 阶段 | Store | 预计工作量 | 特殊处理 |
|------|-------|-----------|----------|
| 2.1 | IndustryBasicStore | 2h | 基础 CRUD |
| 2.2 | IndustryMappingStore | 3h | PIT 查询 |
| 2.3 | IdentityStore | 3h | PIT 查询 |
| 2.4 | UniverseStore | 4h | 成分股管理 |
| 2.5 | CalendarStore | 6h | 内存缓存 + CacheManager |
| 2.6 | InstrumentStore | 8h | DataCache + 批量查询优化 |

### 3.2 每个 Store 的任务清单

1. 创建 `*_reader.py` - 迁移所有读方法
2. 创建 `*_writer.py` - 迁移所有写方法 + 缓存失效逻辑
3. 创建 `test_*_reader.py` - Reader 单元测试
4. 创建 `test_*_writer.py` - Writer 单元测试
5. 创建 `test_*_integration.py` - Reader+Writer 集成测试
6. 更新 `__init__.py` - 导出 Reader/Writer
7. 删除 `*_store.py` - 旧代码
8. 更新 Service 层 - 注入 Reader/Writer

### 3.3 Commit 策略

每个 Store 完成后立即提交，便于回滚。

## 4. 实现示例

### 4.1 IndustryBasicReader（最简单示例）

```python
class IndustryReader:
    """申万行业主数据读取器。"""

    def __init__(self, db_path: Path, cache_manager: CacheManager) -> None:
        self._store = SQLiteStore(db_path)
        self._cache = cache_manager

    def get_all(self, is_active: bool = True) -> pl.DataFrame:
        cache_key = f"industry:all:active={is_active}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        sql = "SELECT * FROM industry_basic WHERE 1=1"
        params: list[object] = []

        if is_active:
            sql += " AND is_active = ?"
            params.append(1)

        rows = self._store.fetchall(sql, params)
        result = pl.DataFrame([dict(row) for row in rows])

        self._cache.set(cache_key, result)
        return result

    def get_by_id(self, industry_id: str) -> dict[str, Any] | None:
        return self._store.fetchone(
            "SELECT * FROM industry_basic WHERE industry_id = ?",
            [industry_id],
        )
```

### 4.2 IndustryBasicWriter

```python
class IndustryWriter:
    """申万行业主数据写入器。"""

    def __init__(self, db_path: Path, cache_manager: CacheManager) -> None:
        self._store = SQLiteStore(db_path)
        self._cache = cache_manager

    def register(self, industry: IndustryBasic) -> None:
        self._store.execute(
            """INSERT OR REPLACE INTO industry_basic
            (industry_id, industry_name, industry_level, parent_id, is_active)
            VALUES (?, ?, ?, ?, ?)""",
            [
                industry.industry_id,
                industry.industry_name,
                industry.industry_level,
                industry.parent_id,
                1 if industry.is_active else 0,
            ],
        )
        self._store.commit()

        # 失效相关缓存
        self._cache.invalidate_pattern("industry:*")
```

## 5. 测试策略

### 5.1 测试文件结构

```
tests/unit/stores/metadata/industry/
├── test_industry_reader.py      # Reader 单元测试
├── test_industry_writer.py      # Writer 单元测试
└── test_industry_integration.py # Reader+Writer 集成测试
```

### 5.2 测试覆盖范围

| 测试类型 | 覆盖内容 |
|----------|----------|
| **Reader 单元测试** | 空数据集、过滤条件、缓存命中、边界条件 |
| **Writer 单元测试** | 插入、更新、删除、缓存失效调用、事务回滚 |
| **集成测试** | 写入后可读取、缓存正确失效、并发安全 |
| **PIT 专项测试** | asof=None vs asof=历史日期、边界条件 |
| **性能测试** | CalendarStore O(1) 查询验证 |
| **CacheManager 测试** | 线程安全、模式匹配失效 |

## 6. 风险缓解

| 风险 | 缓解措施 |
|------|----------|
| 缓存失效遗漏 | 代码审查 + 集成测试验证 |
| SQLite 连接泄漏 | 使用 context manager + 单元测试 |
| 并发安全问题 | CacheManager 使用 RLock + 并发测试 |
| Service 层破坏性变更 | 逐个更新 Service，保持向后兼容 |

## 7. 验收标准

```bash
# 完整测试
pixi run -e dev test

# 代码质量
pixi run -e dev check
pixi run -e dev type
pixi run -e dev lint
```

## 8. 文件结构（重构后）

```
stores/metadata/
├── instrument/
│   ├── instrument_reader.py
│   ├── instrument_writer.py
│   └── __init__.py
├── calendar/
│   ├── calendar_reader.py
│   ├── calendar_writer.py
│   └── __init__.py
├── identity/
│   ├── identity_reader.py
│   ├── identity_writer.py
│   └── __init__.py
├── industry/
│   ├── industry_reader.py
│   ├── industry_writer.py
│   ├── mapping_reader.py
│   ├── mapping_writer.py
│   └── __init__.py
└── universe/
    ├── universe_reader.py
    ├── universe_writer.py
    └── __init__.py
```
