# Dishka 依赖注入架构设计

> **创建时间**: 2026-01-20
> **基于计划**: [2026-01-19-dishka-migration-refined.md](./2026-01-19-dishka-migration-refined.md)
> **状态**: 已批准，待实现

---

## 执行摘要

本文档描述了使用 **dishka** 框架重构 Ditto 依赖注入的详细设计方案。

### 核心决策

| 方面 | 决策 | 理由 |
|------|------|------|
| **DI 框架** | dishka | 原生 async 支持、完整 Scope 层级、类型推断最佳 |
| **测试策略** | 保持 pytest-mock | Mark Seemann 原则：单元测试不应使用 IoC 容器 |
| **SQLite 连接池** | 轻量改造 | 添加 ping() 和连接数告警，不添加连接上限 |
| **入口集成** | Host 模式 | 借鉴 .NET Generic Host，统一生命周期管理 |
| **文件夹命名** | `registry/` | 语义：组件注册表 |

---

## 架构设计

### Composition Root 模式

遵循 Mark Seemann 的 Composition Root 原则：

```
apps/port/          ← Composition Root（容器在这里）
  ├── registry/     ← Provider 定义（registry = 注册表）
  └── main.py       ← 容器初始化

packages/data/   ← 纯粹领域逻辑，不依赖 dishka
packages/core/      ← 纯粹领域逻辑，不依赖 dishka
packages/foundation/ ← 基础设施，不依赖 dishka
```

### Scope 配置

| Scope | 用途 | 示例组件 |
|-------|------|----------|
| **APP** | 应用级单例 | DataHub, Observability, SQLitePool |
| **REQUEST** | HTTP 请求级 | 未来：UnitOfWork |
| **ACTION** | 单次操作 | 未来：Cache |

**当前阶段**：所有组件使用 `Scope.APP`

---

## 目录结构

```
apps/port/src/ditto_port/registry/
  ├── __init__.py
  ├── app.py          ← AppProvider（Observability、SQLitePool、XDGPaths）
  ├── datahub.py      ← DataHubProvider（所有 DataHub 组件）
  └── sources.py      ← DataSourcesProvider（TushareSource 等）
```

---

## Phase 1: 基础设施（1 天）

### Task 1.1: 安装和配置 dishka

**文件**: `pixi.toml`

```toml
[dependencies]
dishka = ">=0.5.0"
```

**新建文件**:
- `apps/port/src/ditto_port/registry/__init__.py`
- `apps/port/src/ditto_port/registry/app.py`

### Task 1.2: Observability 迁移

**问题**: `_ObservabilityRegistry` 是类级全局单例

**改造**:

```python
# registry/app.py
from dishka import Provider, provide, Scope
from ditto_foundation.observability import init, shutdown
import os

class AppProvider(Provider):
    @provide(scope=Scope.APP)
    def observability(self) -> None:
        """初始化 Observability，应用级单例"""
        env = os.getenv("DITTO_ENV", "development")
        init(
            service_name="ditto-server",
            environment=env,
            log_level="DEBUG" if env == "development" else "INFO",
            log_dir=str(get_paths().logs),
            pytest_running=False,
            assertions_enabled=False,
            verbose_logging=(env == "development"),
        )
        yield
        shutdown()
```

**foundation 层变更**:
- 移除 `_ObservabilityRegistry` 类

### Task 1.3: SQLitePool 轻量改造

**轻量改造内容**:

| 改造项 | 方案 |
|--------|------|
| **健康检查** | 添加 `ping()` 方法 |
| **连接监控** | 连接数 >= 50 时记录警告日志 |
| **超时管理** | 保持已有 `timeout=30` |
| **不添加** | 连接上限、复杂泄漏检测 |

```python
# packages/foundation/src/ditto_foundation/db/sqlite_pool.py

class SQLitePool:
    WARN_CONNECTION_COUNT = 50

    def __init__(self, ...):
        self._connection_count = 0
        self._count_lock = threading.Lock()

    def ping(self) -> bool:
        """健康检查"""
        try:
            self.execute("SELECT 1")
            return True
        except Exception:
            return False

    def get_connection(self) -> sqlite3.Connection:
        # ... 原有逻辑 ...
        with self._count_lock:
            self._connection_count += 1
            if self._connection_count >= self.WARN_CONNECTION_COUNT:
                logger.warning("connection_count_warning", ...)

    def close(self) -> None:
        # ... 原有逻辑 ...
        with self._count_lock:
            self._connection_count -= 1
```

**Provider 注册**:

```python
@provide(scope=Scope.APP)
def sqlite_pool(self) -> Iterator[SQLitePool]:
    pool = SQLitePool(...)
    pool.init_schema()
    yield pool
    pool.close()
```

### Task 1.4: XDGPaths 修复

**问题**: `@cached_property` 在单例模式下无法重置

**改造**: 移除 `@cached_property`，改为普通属性

### Task 1.5: DataHub Registry（Root 注入）

**核心原则**: Store/Repository 层代码不修改

```python
# registry/datahub.py
from dishka import Provider, provide, Scope

class DataHubProvider(Provider):
    scope = Scope.APP

    @provide
    def datahub(
        self,
        security_store: SecurityStore,
        calendar_store: CalendarStore,
        ...
    ) -> DataHub:
        return DataHub(...)

    @provide
    def security_store(self, sqlite_client: SQLiteClient) -> SecurityStore:
        return SecurityStore(sqlite_client)

    # ... 其他 Store
```

---

## Phase 2: DataSources Registry（0.5 天）

```python
# registry/sources.py
from dishka import Provider, provide, Scope

class DataSourcesProvider(Provider):
    scope = Scope.APP

    @provide
    def tushare_source(
        self,
        http_client: HttpClient,
    ) -> TushareSource:
        return TushareSource(
            token=get_config().tushare_token,
            http_client=http_client,
        )
```

---

## Phase 3: 入口集成（借鉴 .NET Generic Host）

### 3.1 FastAPI 入口

**文件**: `apps/port/src/ditto_port/main.py`

```python
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from ditto_port.registry.app import AppProvider
from ditto_port.registry.datahub import DataHubProvider
from ditto_port.registry.sources import DataSourcesProvider

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 创建容器
    container = make_async_container(
        AppProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )

    # 集成到 FastAPI
    setup_dishka(container=container, app=app)

    yield

    # 关闭容器
    await container.close()
```

**路由使用**:

```python
from dishka.integrations.fastapi import FromDishka
from ditto_data import DataHub

@router.get("/api/securities")
async def list_securities(
    hub: FromDishka[DataHub],
) -> Response:
    return hub.list_securities()
```

### 3.2 CLI 入口（Generic Host 模式）

**文件**: `apps/port/src/ditto_port/cli/context.py`

```python
@asynccontextmanager
async def create_cli_host(data_root: str):
    """CLI Host - 仿照 .NET Generic Host 模式"""
    container = make_async_container(
        AppProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
    try:
        yield container
    finally:
        await container.close()

@asynccontextmanager
async def create_executor(data_root: str):
    async with create_cli_host(data_root) as container:
        hub = await container.get(DataHub)
        app_ctx = _AppContext(hub=hub, source=hub.sources)
        executor = CLIExecutor(app_ctx)
        yield executor
```

### 3.3 Prefect 入口（Task 级容器）

**文件**: `apps/port/src/ditto_port/jobs/flows/helpers.py`

```python
@asynccontextmanager
async def create_prefect_task_container(data_root: str):
    """Prefect Task 容器 - 每个 task 独立实例"""
    container = make_async_container(
        AppProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
    try:
        yield container
    finally:
        await container.close()

@asynccontextmanager
async def create_ingestion_context(data_root: str):
    async with create_prefect_task_container(data_root) as container:
        hub = await container.get(DataHub)
        source = await container.get(TushareSource)
        yield hub, source
```

---

## Phase 4: 测试优化（0.5 天）

**核心原则**: 保持 pytest-mock，不迁移到 dishka.TestContainer

**优化内容**:
- 确保 fixtures 使用正确（autouse, scope）
- 添加 fixtures 文档字符串
- 检查 mock 使用是否规范
- 运行 `pytest --cov` 检查覆盖率 >= 80%

**不迁移原因**（记录在文档）:
- Mark Seemann 原则：单元测试不应使用 IoC 容器
- Pytest fixtures 本身就是 DI 框架
- 业界共识：80-90% 单元测试用 mock

---

## Phase 5: 文档和规范更新（0.5 天）

### 5.1 更新开发规范

**文件**: `.claude/rules/core.md`

**新增章节**:
```markdown
## 依赖注入 (Dishka)

### 使用原则

1. **Composition Root 模式**
   - 容器只在 `apps/port/` 层初始化
   - 核心包不依赖 dishka

2. **Registry 结构**
   - `registry/app.py` - 基础设施组件
   - `registry/datahub.py` - DataHub 组件
   - `registry/sources.py` - 外部数据源

3. **Scope 使用**
   - 当前：所有组件使用 `Scope.APP`
```

### 5.2 添加测试规范约束

**文件**: `.claude/rules/python-test.md`

**新增章节**:
```markdown
## 单元测试规范

**重要**: 单元测试不使用 dishka.TestContainer

**理由**:
- Mark Seemann 原则：单元测试不应使用 IoC 容器
- Pytest fixtures 本身就是 DI 框架
```

### 5.3 更新设计文档

**文件**: `docs/design/04_deployment_topology.md`

---

## 验收标准

### 功能验收
- [ ] 所有全局状态改为 DI 组件
- [ ] 资源生命周期自动管理（init/destroy）
- [ ] FastAPI/CLI/Prefect 三个入口正常工作
- [ ] 测试覆盖率 >= 80%

### 质量验收
- [ ] pyright 检查通过（strict）
- [ ] ruff 检查通过
- [ ] pre-commit hooks 通过

### 文档验收
- [ ] 设计文档已更新
- [ ] 开发规范已更新
- [ ] 测试规范已更新

---

## 参考资料

**权威资料**:
- [Composition Root - ploeh blog](https://blog.ploeh.dk/2011/07/28/CompositionRoot/)
- [Dishka 文档](https://dishka.readthedocs.io/en/stable/)
- [.NET Generic Host](https://learn.microsoft.com/en-us/dotnet/core/extensions/generic-host)

---

**文档版本**: v1.0
**最后更新**: 2026-01-20
