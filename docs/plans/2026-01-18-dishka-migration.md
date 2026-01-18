# 开发计划: 使用 dishka 重构 Ditto 依赖注入

## 概述
- **创建时间**: 2026-01-18
- **Sprint**: 待定
- **状态**: 待审批

## 背景与目标

### 当前问题
1. DataHub 和 SourcesProvider 使用 `@cached_property` + 手工 DI，依赖传递冗长
2. 资源生命周期管理分散（`atexit`、`close()`、`shutdown()`）
3. 无循环依赖检测
4. 测试时需要手工 `mocker.patch`，容易遗漏

### 目标
引入 **dishka** DI 容器，实现：
- 自动依赖解析，减少样板代码
- 统一资源生命周期管理（init/destroy 钩子）
- 优雅的测试覆盖（容器隔离）
- 自动循环依赖检测

---

## 技术方案

### 框架选择：dishka

| 特性 | 理由 |
|------|------|
| **原生生命周期管理** | 通过 `yield` 自动管理 init/destroy |
| **完整 Scope 层级** | APP → REQUEST → ACTION → STEP |
| **原生 Async 支持** | `make_async_container` |
| **类型推断最佳** | 完美支持 Protocol 和 Generic |
| **测试便利** | Component 隔离 + override() |

### Scope 配置评估

基于 Ditto 的实际场景，推荐配置：

| Scope | 用途 | 示例组件 | 理由 |
|-------|------|----------|------|
| **APP** | 应用级单例 | DataHub, SQLitePool, Observability | 所有资源都是应用级单例 |
| **REQUEST** | HTTP 请求级 | 未来：UnitOfWork | 暂不需要，预留给事务管理 |
| **ACTION** | 单次操作 | 未来：Cache | 暂不需要，预留给缓存 |

**结论**：当前阶段只需 **APP scope**，未来可扩展。

### FastAPI 集成方式（Composition Root 模式）

**核心原则**：容器只在 **port 端（装配入口）** 出现，core/datahub 包保持纯粹，不依赖 dishka。

```python
# apps/port/src/ditto_port/main.py（Composition Root）
from dishka.integrations.fastapi import setup_dishka, FromDishka
from dishka import make_async_container, Provider, provide, Scope

# Provider 定义在 port 端
class DittoProvider(Provider):
    @provide(scope=Scope.APP)
    def datahub(self) -> DataHub:
        return DataHub(...)

# 创建容器
container = make_async_container(DittoProvider())

# FastAPI 集成
app = FastAPI()
setup_dishka(container=container, app=app)

# 路由中使用
@router.get("/api/securities")
async def list_securities(
    hub: FromDishka[DataHub]  # 自动注入
) -> Response:
    ...
```

**架构分层**：
```
apps/port/          ← 容器在这里（Composition Root）
  ├── providers/    ← Provider 定义
  └── main.py       ← 容器初始化

packages/datahub/   ← 纯粹领域逻辑，不依赖 dishka
packages/core/      ← 纯粹领域逻辑，不依赖 dishka
packages/foundation/ ← 基础设施，不依赖 dishka
```

### 测试策略

业界最佳实践：**使用 Component 隔离 + Fixture Provider**

```python
# tests/conftest.py
import pytest
from dishka import make_container, Provider

class TestProvider(Provider):
    @provide
    def mock_database(self) -> Database:
        return MemoryDatabase()

@pytest.fixture
def test_container():
    return make_container(TestProvider())

def test_security_store(test_container):
    store = test_container.get(SecurityStore)
    # 测试...
```

---

## 任务清单

### Phase 1: 基础设施（1 天）

#### Task 1.1: 安装和配置 dishka `[S]`
- **描述**: 添加 dishka 依赖，在 port 端创建基础 Provider 结构
- **验收**:
  - `pixi.toml` 包含 `dishka` 和 `dishka[fastapi]`
  - 创建 `apps/port/src/ditto_port/providers/__init__.py`
  - 创建 `AppProvider` 基类
- **文件**:
  - `pixi.toml`
  - `apps/port/src/ditto_port/providers/__init__.py`
  - `apps/port/src/ditto_port/providers/app.py`

#### Task 1.2: 迁移 Observability 到 Provider `[M]`
- **描述**: 将全局 Observability 改为单例组件（在 port 端注册）
- **验收**:
  - `AppProvider.observability()` 返回 Observability 实例
  - 移除 `_ObservabilityRegistry` 全局状态
  - 生命周期通过 `yield` 管理
- **文件**:
  - `packages/foundation/src/ditto_foundation/observability/__init__.py`
  - `apps/port/src/ditto_port/providers/app.py`
- **风险**: Observability 是全局单例，需确保幂等性

#### Task 1.3: 迁移 SQLitePool 到 Provider `[M]`
- **描述**: 将 SQLitePool 改为 APP 级单例（在 port 端注册）
- **验收**:
  - `AppProvider.sqlite_pool()` 返回 SQLitePool 实例
  - 自动管理 init/close 生命周期
  - 保持线程本地连接特性
- **文件**:
  - `packages/foundation/src/ditto_foundation/db/sqlite_pool.py`
  - `apps/port/src/ditto_port/providers/app.py`

#### Task 1.4: 创建 DataHub Provider（root 注入）`[L]`
- **描述**: 在 port 端 Provider 中集中注册所有 DataHub 组件，Store/Repository 层不修改
- **验收**:
  - 所有 Runtime 层组件在 Provider 中注册为 `@provide`
  - 所有 Store 层组件在 Provider 中注册（通过类型注解自动注入）
  - 所有 Repository 层组件在 Provider 中注册（通过类型注解自动注入）
  - Store/Repository 类保持不变，不添加 `@provide` 装饰器
  - 依赖自动解析（通过构造函数类型注解）
- **文件**:
  - `apps/port/src/ditto_port/providers/datahub.py`（新建）
  - Store/Repository 层文件**不修改**（~20 个文件）
- **风险**: 依赖关系复杂，需确保类型注解完整

---

### Phase 2: SourcesProvider 迁移（0.5 天）

#### Task 2.1: 创建 SourcesProvider（root 注入）`[M]`
- **描述**: 在 port 端 Provider 中集中注册外部数据源组件
- **验收**:
  - `SourcesProvider` 继承 `Provider`
  - TushareSource 在 Provider 中注册为 `@provide`
  - 与 DataHub Provider 可组合使用
  - 数据源类保持不变，不添加 `@provide` 装饰器
- **文件**:
  - `apps/port/src/ditto_port/providers/sources.py`（新建）

---

### Phase 3: FastAPI 集成（0.5 天）

#### Task 3.1: 更新 FastAPI lifespan `[M]`
- **描述**: 使用 dishka 容器管理应用生命周期
- **验收**:
  - `lifespan` 中初始化 `make_async_container`
  - 使用 `setup_dishka()` 集成
  - 容器关闭时自动清理所有资源
- **文件**:
  - `apps/port/src/ditto_port/main.py`

#### Task 3.2: 更新路由使用 FromDishka `[S]`
- **描述**: 可选：路由使用 `FromDishka[]` 自动注入
- **验收**:
  - 示例路由使用 `FromDishka[DataHub]`
  - 移除 `Depends()` 手工依赖
- **文件**:
  - `apps/port/src/ditto_port/api/routes/`

---

### Phase 4: 测试迁移（1 天）

#### Task 4.1: 创建测试 Provider 基类 `[M]`
- **描述**: 建立测试用 Provider 模式
- **验收**:
  - `tests/conftest.py` 定义 `TestProvider`
  - 使用内存数据库 mock
  - 使用 MockObservability
- **文件**:
  - `packages/datahub/tests/conftest.py`
  - `packages/datahub/tests/unit/conftest.py`

#### Task 4.2: 迁移单元测试 `[L]`
- **描述**: 更新现有单元测试使用 TestContainer
- **验收**:
  - 所有单元测试使用 `test_container` fixture
  - 移除 `mocker.patch`（大部分）
  - 测试覆盖率保持 >= 80%
- **文件**:
  - `packages/datahub/tests/unit/test_*.py`
  - 涉及 ~50 个测试文件

#### Task 4.3: 迁移集成测试 `[M]`
- **描述**: 更新集成测试使用真实容器
- **验收**:
  - 集成测试使用真实 DataHub Provider
  - 测试数据库独立隔离
- **文件**:
  - `packages/datahub/tests/integration/`

---

### Phase 5: 文档和规范更新（0.5 天）

#### Task 5.1: 更新开发规范 `[M]`
- **描述**: 在 `.claude/rules/core.md` 中添加 dishka 使用规范
- **验收**:
  - DI 容器使用章节（Provider 定义规范、Scope 配置）
  - Root 注入模式说明（容器逻辑集中管理）
  - 测试最佳实践（TestProvider、mock 策略）
  - 常见问题解答
- **文件**:
  - `.claude/rules/core.md`

#### Task 5.2: 更新设计文档 `[S]`
- **描述**: 记录 DI 架构变更
- **验收**:
  - `docs/design/04_deployment_topology.md` 更新容器管理章节
  - `docs/design/05_data_lifecycle.md` 添加生命周期管理说明
- **文件**:
  - `docs/design/04_deployment_topology.md`
  - `docs/design/05_data_lifecycle.md`

#### Task 5.3: 更新 API 规范 `[S]`
- **描述**: 更新 FastAPI 集成文档
- **验收**:
  - `docs/api/README.md` 更新依赖注入说明
- **文件**:
  - `docs/api/README.md`

---

## 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **依赖关系复杂** | 迁移失败，回滚 | 中 | 分阶段迁移，每阶段验证 |
| **测试覆盖不足** | 生产问题 | 中 | 先迁移测试，保持覆盖率 |
| **性能回归** | 启动变慢 | 低 | dishka 懒加载，性能相当 |
| **学习曲线** | 开发效率 | 低 | 提供指南和示例 |
| **dishka 不成熟** | 长期维护 | 低 | 569 stars，活跃维护 |

---

## 验收标准

### 功能验收
- [ ] 所有 `@cached_property` 改为 `@provide`
- [ ] 资源生命周期自动管理（init/destroy）
- [ ] FastAPI 集成正常工作
- [ ] 测试覆盖率 >= 80%
- [ ] 所有测试通过

### 质量验收
- [ ] pyright 检查通过（strict）
- [ ] ruff 检查通过
- [ ] pre-commit hooks 通过
- [ ] 无循环依赖警告

### 文档验收
- [ ] 设计文档已更新
- [ ] 开发规范已更新（core.md 包含 DI 容器使用章节）
- [ ] API 文档已更新

---

## 执行顺序

```
Phase 1: 基础设施 (1 天)
  ├─ Task 1.1: 安装配置
  ├─ Task 1.2: Observability
  ├─ Task 1.3: SQLitePool
  └─ Task 1.4: DataHub Provider（root 注入）

Phase 2: SourcesProvider (0.5 天)
  └─ Task 2.1: 创建 SourcesProvider（root 注入）

Phase 3: FastAPI 集成 (0.5 天)
  ├─ Task 3.1: 更新 lifespan
  └─ Task 3.2: 更新路由

Phase 4: 测试迁移 (1 天)
  ├─ Task 4.1: 测试 Provider
  ├─ Task 4.2: 单元测试
  └─ Task 4.3: 集成测试

Phase 5: 文档规范 (0.5 天)
  ├─ Task 5.1: 更新开发规范（core.md）
  ├─ Task 5.2: 设计文档
  └─ Task 5.3: API 文档

总工作量: 3.5 天
```

---

## 关键文件清单

### 需要修改的文件

| 类型 | 文件路径 | 修改类型 |
|------|----------|----------|
| **依赖配置** | `pixi.toml` | 编辑 |
| **基础设施** | `packages/foundation/src/ditto_foundation/observability/__init__.py` | 重构 |
| **基础设施** | `packages/foundation/src/ditto_foundation/db/sqlite_pool.py` | 重构 |
| **应用（port 端）** | `apps/port/src/ditto_port/providers/__init__.py` | 新建 |
| **应用（port 端）** | `apps/port/src/ditto_port/providers/app.py` | 新建 |
| **应用（port 端）** | `apps/port/src/ditto_port/providers/datahub.py` | 新建 |
| **应用（port 端）** | `apps/port/src/ditto_port/providers/sources.py` | 新建 |
| **应用（port 端）** | `apps/port/src/ditto_port/main.py` | 重构 |
| **应用（port 端）** | `apps/port/src/ditto_port/api/routes/*.py` | 重构 |
| **数据层** | `packages/datahub/src/ditto_datahub/hub.py` | 重构 |
| **测试** | `packages/datahub/tests/conftest.py` | 重构 |
| **测试** | `packages/datahub/tests/unit/conftest.py` | 重构 |
| **文档** | `.claude/rules/core.md` | 编辑 |
| **文档** | `.claude/rules/python-test.md` | 编辑 |
| **文档** | `docs/design/04_deployment_topology.md` | 编辑 |
| **文档** | `docs/design/05_data_lifecycle.md` | 编辑 |
| **文档** | `docs/api/README.md` | 编辑 |

### Store/Repository/数据源层文件（**不修改**，Composition Root 注入）

以下文件通过 port 端 Provider 中的类型注解自动注入，无需修改：

**Store 层（~10 个）**：
- `packages/datahub/src/ditto_datahub/stores/security_store.py`
- `packages/datahub/src/ditto_datahub/stores/calendar_store.py`
- `packages/datahub/src/ditto_datahub/stores/bars_store.py`
- `packages/datahub/src/ditto_datahub/stores/adj_factor_store.py`
- `packages/datahub/src/ditto_datahub/stores/universe_store.py`
- `packages/datahub/src/ditto_datahub/stores/index_weight_store.py`
- `packages/datahub/src/ditto_datahub/stores/ingestion_log.py`
- `packages/datahub/src/ditto_datahub/stores/quarantine_store.py`
- `packages/datahub/src/ditto_datahub/stores/stock_status_store.py`
- `packages/datahub/src/ditto_datahub/stores/parquet_store_base.py`

**Repository 层（~6 个）**：
- `packages/datahub/src/ditto_datahub/repositories/security.py`
- `packages/datahub/src/ditto_datahub/repositories/calendar.py`
- `packages/datahub/src/ditto_datahub/repositories/bars/repository.py`
- `packages/datahub/src/ditto_datahub/repositories/adj_factor.py`
- `packages/datahub/src/ditto_datahub/repositories/universe.py`
- `packages/datahub/src/ditto_datahub/repositories/index.py`

**数据源层（~2 个）**：
- `packages/datahub/src/ditto_datahub/sources/provider.py`
- `packages/datahub/src/ditto_datahub/sources/tushare.py`

**核心原则**：
- ✅ **apps/port/** - Composition Root，容器在这里
- ✅ **packages/** - 纯粹领域逻辑，不依赖 dishka

---

## 回滚计划

如果迁移遇到不可解决的问题：

1. **Git 分支策略**：在独立分支 `feature/dishka-migration` 开发
2. **分阶段提交**：每个 Phase 独立 commit，便于回滚
3. **保留旧代码**：迁移期间注释旧代码，不直接删除
4. **回滚触发条件**：
   - 性能回归 > 20%
   - 测试覆盖率 < 75%
   - 核心功能失败

---

## 后续优化

迁移完成后的可选优化：

1. **依赖图可视化**：使用 graphviz 生成依赖图
2. **REQUEST scope**：为 UnitOfWork 添加请求级事务
3. **Component 隔离**：按模块拆分 Provider
4. **性能监控**：监控容器解析耗时

---

**文档版本**: v1.0
**最后更新**: 2026-01-18
**状态**: 待审批
