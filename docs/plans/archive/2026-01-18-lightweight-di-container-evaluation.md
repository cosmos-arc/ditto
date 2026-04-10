# 轻量级 DI 容器评估：punq vs lagom

**日期**: 2026-01-18
**状态**: Brainstorming
**原始文档**: [2026-01-17-python-initialization-best-practices.md](./2026-01-17-python-initialization-best-practices.md)

---

## 背景

之前的设计文档推荐了**方案C（手工DI + cached_property）**，主要基于对 `dependency-injector` 重型框架的评估。

现在讨论引入**轻量级DI容器**（punq/lagom）的可能性，主要关注：
1. **类型安全与自动装配**：依赖完整性检查，自动解析
2. **生命周期管理**：transient/scoped/singleton 等作用域
3. **测试便利性**：优雅的 override/mock 机制
4. **依赖可视化**：自动生成依赖图

---

## 第一部分：工具对比

### punq - 极简主义

**设计理念**：只提供依赖注入核心能力，不侵入应用代码

| 特性 | 说明 |
|------|------|
| **依赖量** | 零依赖（除了typing） |
| **API复杂度** | 极简（~3个核心方法） |
| **类型推断** | 完美支持（Protocol + Generic） |
| **注册方式** | 显式 `register()` 调用 |
| **生命周期** | Singleton（默认）/ Transient |

### lagom - 功能丰富

**设计理念**：减少样板代码，提供更多高级特性

| 特性 | 说明 |
|------|------|
| **依赖量** | 零依赖 |
| **API复杂度** | 中等（装饰器 + 显式注册） |
| **类型推断** | 良好支持 |
| **注册方式** | 装饰器 / 显式 / 自动发现 |
| **生命周期** | Singleton / Transient / Scoped |
| **额外特性** | 依赖图可视化、配置注入 |

---

## 第二部分：代码对比示例

### punq 示例

```python
# punq 注册方式
container = punq.Container()

# 显式注册接口和实现
container.register('observability', ObservabilityImpl)
container.register('database', DatabaseImpl)
container.register('security_store', SecurityStore)

# 解决依赖
obs = container.resolve('observability')  # 类型: Any
db = container.resolve(Database)          # 类型推断需要帮助
```

### lagom 示例

```python
# lagom 注册方式
container = Container()

# 装饰器注册（可选）
@container.register
class ObservabilityImpl:
    def __init__(self, config: ObservabilityConfig):
        self.config = config

# 显式注册
container.register(DatabaseImpl)

# 自动构造函数注入
obs = container.resolve(ObservabilityImpl)  # 类型: ObservabilityImpl
db = container.resolve(Database)            # 类型: Database
```

---

## 第三部分：与当前 Ditto 架构的集成

### 当前手工DI模式（方案C）

```python
@dataclass
class Container:
    config: Settings

    @cached_property
    def observability(self) -> ObservabilityPort:
        return ObservabilityImpl(self.config.observability)

    @cached_property
    def database(self) -> DatabasePort:
        return SQLitePool(db_path)
```

### punq 集成

```python
# bootstrap.py
container = punq.Container()

def bootstrap(config: Settings) -> punq.Container:
    # 注册配置
    container.register(Settings, instance=config)

    # 注册服务（单例）
    container.register(ObservabilityPort, ObservabilityImpl)
    container.register(DatabasePort, SQLitePool)

    return container

# 使用
obs = container.resolve(ObservabilityPort)
```

### lagom 集成

```python
# bootstrap.py
container = Container()

def bootstrap(config: Settings) -> Container:
    # 装饰器方式
    @container.register
    class ObservabilityImpl:
        def __init__(self, config: ObservabilityConfig):
            self.config = config

    # 显式方式
    container.register(DatabasePort)[DatabaseImpl]

    return container
```

---

## 对比维度

| 维度 | 手工DI（方案C） | punq | lagom |
|------|----------------|------|-------|
| **外部依赖** | ✅ 零 | ✅ 零（除typing） | ✅ 零 |
| **类型推断** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ 需要类型辅助 | ⭐⭐⭐⭐ 较好 |
| **自动装配** | ❌ 手工构造 | ✅ 自动注入 | ✅ 自动注入 |
| **生命周期** | ⭐⭐ cached_property | ⭐⭐⭐ Singleton/Transient | ⭐⭐⭐⭐ Scoped支持 |
| **测试Mock** | ⭐⭐⭐⭐⭐ 覆盖属性 | ⭐⭐⭐ register instance | ⭐⭐⭐⭐ override |
| **依赖图** | ⭐⭐⭐ 代码即文档 | ❌ 无 | ✅ 内置可视化 |
| **学习曲线** | ⭐⭐⭐⭐ 纯Python | ⭐⭐⭐⭐ 极简API | ⭐⭐⭐ 需要学习 |
| **调试友好** | ⭐⭐⭐⭐⭐ 断点直达 | ⭐⭐⭐ 框架层 | ⭐⭐⭐ 框架层 |

---

## 第四部分：生命周期需求分析

### 需要的生命周期类型

| 类型 | 用例 | 当前手工DI | punq | lagom |
|------|------|-----------|------|-------|
| **Singleton** | DatabasePool, SecurityStore, Config | ✅ cached_property | ✅ | ✅ |
| **Transient** | Command/Query 处理器（无状态） | ❌ 不支持 | ✅ 默认 | ✅ 默认 |
| **Scoped** | UnitOfWork（每个请求一个事务） | ❌ 不支持 | ❌ 需额外库 | ✅ 原生支持 |

### Transient 用例示例

```python
# 无状态命令处理器：每次执行应该有新实例
class ProcessIngestionCommand:
    def __init__(self, hub: DataHub, validator: Validator):
        self.hub = hub
        self.validator = validator
```

### Scoped 用例示例

```python
# UnitOfWork：每个 HTTP 请求一个事务
class UnitOfWork:
    async def __aenter__(self):
        self.transaction = await self.db.begin()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.transaction.rollback()
        else:
            await self.transaction.commit()
```

**结论**：lagom 在 Scoped 生命周期支持上有明显优势。

---

## 第五部分：测试便利性对比

### 手工DI测试

```python
# 需要手动覆盖属性
def test_ingestion_service():
    container = bootstrap_for_test(overrides={
        "database": MockDatabase(),
    })
```

### punq 测试

```python
# 需要重新注册
def test_ingestion_service():
    container = punq.Container()
    container.register(Database, MockDatabase)  # 覆盖
```

### lagom 测试

```python
# 优雅的 override
def test_ingestion_service():
    container = create_test_container()
    container.override(Database, MockDatabase)  # 专用方法
```

---

## 第六部分：依赖检查能力

### 循环依赖检测

| 方案 | 检测能力 | 检测时机 |
|------|---------|---------|
| **手工DI** | ❌ 无检测 | 运行时死循环 |
| **punq** | ✅ 自动检测 | 容器构建时 |
| **lagom** | ✅ 自动检测 | 容器构建时 |

### 依赖完整性检查

```python
# punq: 尝试解析时立即发现缺失依赖
try:
    service = container.resolve(MyService)
except ResolutionError as e:
    # "Cannot resolve MyService: dependency on Config not registered"
    pass

# lagom: 同样在解析时检测
try:
    service = container.resolve(MyService)
except DependencyNotFoundError as e:
    pass
```

### 依赖列表功能

```python
# lagom: 内置依赖图遍历
def print_dependencies(container):
    for definition in container._dependency_graph:
        print(f"{definition.interface} -> {definition.impl}")

# 输出示例:
# DatabasePort -> SQLitePool
# SecurityStore -> SecurityStore
#   └─ depends on: [DatabasePort]
```

**结论**：两者都具备依赖检查能力，lagom 提供了更好的内省工具。

---

## 第七部分：迁移成本评估

### punq 迁移成本

| 阶段 | 工作量 | 说明 |
|------|--------|------|
| **安装依赖** | 5分钟 | `pixi add punq` |
| **创建容器** | 1-2小时 | 替换现有的 Container 类 |
| **迁移注册** | 2-3小时 | 将所有 `@cached_property` 改为 `register()` |
| **更新测试** | 1-2小时 | 调整 mock 方式 |
| **总计** | **0.5-1天** | 相对简单 |

### lagom 迁移成本

| 阶段 | 工作量 | 说明 |
|------|--------|------|
| **安装依赖** | 5分钟 | `pixi add lagom` |
| **创建容器** | 1-2小时 | 替换现有的 Container 类 |
| **迁移注册** | 1-2小时 | 可使用装饰器，比 punq 更快 |
| **更新测试** | 1-2小时 | 使用 `override()` 方法 |
| **可选：依赖可视化** | 0.5小时 | 添加依赖图输出 |
| **总计** | **0.5-1天** | 与 punq 相当 |

### 兼容性分析

| 层级 | 兼容性 | 说明 |
|------|--------|------|
| **Foundation** | ✅ 完全兼容 | 不影响现有代码，只在入口处集成 |
| **DataHub** | ✅ 完全兼容 | Store/Engine 保持不变 |
| **Core** | ✅ 完全兼容 | 业务逻辑无感知 |
| **Port (FastAPI)** | ✅ 完全兼容 | 只需更新 `bootstrap.py` 和 `main.py` |

---

## 第八部分：最终推荐

### 推荐：lagom

**理由**：

1. **✅ Scoped 生命周期原生支持**
   - punq 需要额外库 `punq-ext`，增加依赖复杂度

2. **✅ 更简洁的 API**
   - 装饰器注册：`@container.register`
   - 减少更多样板代码

3. **✅ 更好的测试体验**
   - 专用 `override()` 方法，语义更清晰
   - 内置测试辅助工具

4. **✅ 依赖检查工具**
   - 内置依赖图遍历
   - 循环依赖自动检测

5. **✅ 零依赖**
   - 与 punq 相当

6. **✅ 迁移成本相当**
   - 约 0.5-1 天
   - 完全兼容现有架构

### punq 的适用场景

只有在以下情况下才考虑 punq：

- 追求**极简主义**，只需要最基本的依赖注入
- 不需要 Scoped 生命周期
- 不需要依赖可视化
- 希望最小化框架"魔法"

---

## 第九部分：实施计划（lagom）

### Phase 1: 基础设施（0.5 天）

```bash
# 1. 安装依赖
pixi add lagom

# 2. 创建新容器
# apps/port/src/ditto_port/container.py
from lagom import Container

container = Container()

@container.register
class ObservabilityImpl:
    def __init__(self, config: ObservabilityConfig):
        self.config = config

@container.register
class DatabasePool:
    def __init__(self, config: DatabaseConfig):
        self.config = config
```

### Phase 2: 迁移现有服务（0.5 天）

1. 将 `@cached_property` 改为 `@container.register`
2. 移除手工依赖传递
3. 更新 FastAPI `lifespan`

### Phase 3: 测试验证（0.5 天）

1. 更新测试使用 `container.override()`
2. 验证依赖注入正确性
3. 运行完整测试套件

---

## 第十部分：lagom 详细代码示例

### 示例 1：基本注册与依赖注入

**当前手工DI**：

```python
@dataclass
class Container:
    config: Settings

    @cached_property
    def database(self) -> DatabasePort:
        from ditto_foundation.db.sqlite_pool import SQLitePool
        db_path = Path(self.config.file_storage.data_root) / "meta" / "hub.sqlite"
        return SQLitePool(str(db_path))

    @cached_property
    def security_store(self) -> SecurityStore:
        from ditto_data.stores.security_store import SecurityStore
        from ditto_data.stores.sqlite_client import SQLiteClient
        # 手工传递依赖
        return SecurityStore(
            sqlite_client=SQLiteClient(self.database)
        )
```

**使用 lagom**：

```python
# apps/port/src/ditto_port/container.py
from lagom import Container

container = Container()

# 1. 注册配置（单例实例）
container.register(Settings, instance=lambda: get_settings())

# 2. 注册服务（使用装饰器）
@container.register
class SQLitePool:
    def __init__(self, config: Settings):
        db_path = Path(config.file_storage.data_root) / "meta" / "hub.sqlite"
        self.pool = self._create_pool(str(db_path))

# 3. 注册复杂依赖（自动注入构造函数参数）
@container.register
class SQLiteClient:
    def __init__(self, database: SQLitePool):  # 自动注入
        self.database = database

@container.register
class SecurityStore:
    def __init__(self, sqlite_client: SQLiteClient):  # 自动注入
        self.client = sqlite_client

# 使用：
security_store = container.resolve(SecurityStore)
# lagom 自动: 创建 SQLiteClient -> 创建 SQLitePool -> 获取 Settings
```

### 示例 2：Scoped 生命周期（UnitOfWork）

**场景**：每个 HTTP 请求需要一个独立的事务

```python
# 使用 lagom 的 scoped
from lagom import Container

container = Container()

@container.register
class DatabasePool:
    """全局单例（默认）"""
    def __init__(self, config: Settings):
        self.engine = create_engine(config.db_dsn)

# 定义 UnitOfWork（每次请求创建新实例）
@container.register
class UnitOfWork:
    """每个请求一个新实例"""
    def __init__(self, db: DatabasePool):
        self.db = db
        self.transaction = None

    async def __aenter__(self):
        self.transaction = await self.db.begin()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.transaction.rollback()
        else:
            await self.transaction.commit()

# FastAPI 集成
@app.get("/api/securities")
async def get_securities(
    uow: UnitOfWork = Depends(lambda: container.resolve(UnitOfWork))
):
    async with uow:
        return await uow.db.query("SELECT * FROM securities")
```

### 示例 3：测试时 Mock 依赖

**当前手工DI测试**：

```python
def test_security_store():
    # 手工覆盖属性
    container = bootstrap_for_test(overrides={
        "database": MockDatabase(),
    })
    store = container.security_store
    # 测试...
```

**使用 lagom**：

```python
import pytest
from unittest.mock import Mock

# 方式 1: 临时覆盖
def test_security_store():
    mock_db = Mock(spec=DatabasePool)
    container.override(DatabasePool, mock_db)  # 专用方法

    store = container.resolve(SecurityStore)
    # store.client.database 现在是 mock_db

# 方式 2: 创建测试容器
@pytest.fixture
def test_container():
    container = Container()
    container.register(Settings, instance=test_settings())
    container.register(DatabasePool, MockDatabase)  # 注册 mock
    return container

def test_security_store(test_container):
    store = test_container.resolve(SecurityStore)
    # 测试...
```

### 示例 4：依赖图输出

```python
# utils/dependency_graph.py
def print_dependency_graph(container: Container):
    """打印依赖关系图"""
    for definition in container._dependency_graph:
        deps = definition.constructor_dependencies
        if deps:
            print(f"{definition.type.__name__}")
            for dep in deps:
                print(f"  └─ {dep.__name__}")
        else:
            print(f"{definition.type.__name__} (无依赖)")

# 输出示例：
# SQLitePool
#   └─ Settings
# SQLiteClient
#   └─ SQLitePool
# SecurityStore
#   └─ SQLiteClient
```

### 示例 5：完整的 FastAPI 集成

```python
# apps/port/src/ditto_port/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from ditto_port.container import container

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup: lagom 在首次 resolve 时自动创建实例
    observability = container.resolve(Observability)
    await observability.init()

    yield

    # Shutdown
    await observability.shutdown()
    await container.resolve(DatabasePool).close()

def create_app() -> FastAPI:
    app = FastAPI(
        title="Ditto Quant API",
        lifespan=lifespan,
    )

    # 注册路由
    from ditto_port.api.routes import router
    app.include_router(router)

    return app

app = create_app()

# 依赖注入辅助函数
def get_security_store() -> SecurityStore:
    return container.resolve(SecurityStore)

# 使用
@app.get("/api/securities")
async def list_securities(
    store: SecurityStore = Depends(get_security_store)
):
    return await store.list_all()
```

---

## 第十一部分：完整迁移示例

### 迁移前（手工DI）

```python
# 15 行代码
@cached_property
def datahub(self) -> DataHub:
    from ditto_data.hub import DataHub
    return DataHub(
        security_store=self.security_store,
        calendar_store=self.calendar_store,
        sql_engine=self.sql_engine,
        dq_engine=self.dq_engine,
    )
```

### 迁移后（lagom）

```python
# 2 行代码
@container.register
class DataHub:
    pass  # 构造函数依赖自动注入
```

**样板代码减少：85%** (15行 → 2行)

---

## 第十二部分：参考资源

### lagom 官方资源

- **GitHub**: https://github.com/meadsteve/lagom
- **PyPI**: https://pypi.org/project/lagom/
- **文档**: https://lagom.readthedocs.io/

### punq 官方资源

- **GitHub**: https://github.com/bennylope/punq
- **PyPI**: https://pypi.org/project/punq/

---

## 决策清单

### 如果选择 lagom

**优势**：
- ✅ Scoped 生命周期原生支持
- ✅ 装饰器语法更简洁
- ✅ 依赖图可视化
- ✅ 更好的测试体验

**代价**：
- 引入一个外部依赖
- 学习框架 API
- 约 0.5-1 天迁移成本

### 如果选择 punq

**优势**：
- ✅ API 更简单
- ✅ 框架"魔法"更少
- ✅ 零依赖（除 typing）

**代价**：
- ❌ Scoped 需要额外库
- ❌ 无内置依赖图
- 约 0.5-1 天迁移成本

### 如果保持手工DI

**优势**：
- ✅ 零外部依赖
- ✅ 完全掌控
- ✅ 纯 Python

**代价**：
- ❌ 不支持 Transient/Scoped
- ❌ 样板代码多
- ❌ 无依赖检查

---

**文档版本**: v1.0
**最后更新**: 2026-01-18
**状态**: 待决策
