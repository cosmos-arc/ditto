# Interfaces 层架构规范

## 定位

Interfaces 层是 **Application Boundary Layer（应用边界层）**，负责：
- HTTP API（FastAPI）
- CLI 命令入口
- Prefect 任务调度（Flow/Task）
- DI 容器组装（Composition Root）

**核心原则**：
- 纯编排层，不包含业务逻辑
- 通过 DI 容器获取依赖
- 业务逻辑已迁入 `ditto_app` 包

## 模块结构

```
ditto_interfaces/
├── api/               # API 路由
├── cli/               # CLI 命令
│   ├── commands/      # 命令实现
│   │   ├── ingest/    # 数据摄入命令
│   │   ├── backfill/  # 回填命令
│   │   └── query/     # 查询命令
│   └── utils/         # CLI 工具
├── jobs/              # Prefect 任务
│   ├── flows/         # Flow 定义
│   └── tasks/         # Task 实现
├── models/            # API 数据模型（Pydantic）
├── registry/          # DI 容器（Dishka Composition Root）
└── main.py            # 启动入口
```

## 依赖规则

```
┌─────────────────────────────────────┐
│  Interfaces 可依赖                  │
│  interfaces → app ✅               │
│  interfaces → engine ✅            │
│  interfaces → data ✅              │
│  interfaces → analytics ✅         │
│  interfaces → infra ✅             │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Interfaces 禁止被依赖              │
│  app → interfaces ❌               │
│  engine → interfaces ❌            │
│  data → interfaces ❌              │
│  analytics → interfaces ❌         │
└─────────────────────────────────────┘
```

### 层级访问规则

| 访问类型 | ✅ 允许 | ❌ 禁止 |
|---------|--------|--------|
| **App 层服务** | `from ditto_app.process.*` | - |
| **App 层查询** | `from ditto_app.query.*` | - |
| **App 层配置** | `from ditto_app.config` | - |
| **Data Service** | `from ditto_data.services.*` | - |
| **Data Sources** | `from ditto_data.sources.*` | - |
| **Data Stores** | registry 内仅限 DI 注册 | 非 registry 代码 |

### 业务逻辑去向

业务逻辑已迁移到 `ditto_app` 包中：

| 原位置 | 新位置 | 内容 |
|--------|--------|------|
| `services/ingestion/` | `ditto_app.process.ingestion` | 数据摄取服务 |
| `services/ingestion/quality/` | `ditto_app.process.quality` | 质量校验服务 |
| `services/strategy/` | `ditto_app.process.strategy` | 策略运行服务 |
| `services/strategy/*.builder` | `ditto_app.builders.strategy` | 策略构建器 |
| `services/derived/materialization*` | `ditto_app.process.materialization` | 衍生物化服务 |
| `services/derived/query_facade*` | `ditto_app.query.derived` | 衍生查询服务 |
| `services/derived/research*` | `ditto_app.query.research` | 研究数据集服务 |
| `models/config` | `ditto_app.config` | 数据集配置 |
| `models/ingestion` | `ditto_data.models.ingestion` | 摄取结果类型 |

## FastAPI 规范

| 要求 | 说明 |
|------|------|
| 路由函数必须类型注解 | 100% 覆盖 |
| 请求/响应用 Pydantic | 类型安全 |
| 异步优先 | `async def` |
| 错误用自定义异常 | `DittoPortError` 等 |

| 禁止 | 替代 |
|------|------|
| 全局 State | `Depends(get_hub)` |
| 直接返回 dict | Pydantic Model |
| 裸 try/except | 自定义异常处理 |

## Prefect 规范

| 要求 | 说明 |
|------|------|
| Flow 必须有 `@flow` 装饰器 | 声明式编排 |
| Task 必须有 `@task` 装饰器 | 可追踪执行 |
| 任务依赖用 | `wait_for`/`upstream` |
| 重试用 | `retry()` 装饰器 |

| 禁止 | 替代 |
|------|------|
| 在 Flow 中写业务逻辑 | 抽取到 Task 或 `ditto_app` |
| 隐式依赖 | 显式 `wait_for` |
| 无限重试 | `max_attempts=3` |

## 数据摄入

Interfaces 层通过 CLI/Jobs 编排数据摄取流程，业务逻辑在 `ditto_app.process.ingestion` 中。
具体 T0/T1/T2/T3 分层规则和游标管理详见 [Data 层规范](../../packages/data/CLAUDE.md)。

## CLI 规范

### 命令结构

```bash
# 数据摄入
pixi run -e dev ditto ingest metadata --date 2024-01-15
pixi run -e dev ditto ingest market --date 2024-01-15

# 历史回填
pixi run -e dev ditto backfill metadata --start 2024-01-01 --end 2024-01-31

# 查询
pixi run -e dev ditto query market --instrument 510300.SH --start 2024-01-01
```

### 命令实现规范

```python
# ✅ 正确：命令只负责参数解析和调用服务
@app.command()
def daily(date: str):
    service = get_ingestion_service()
    service.ingest_daily(date)

# ❌ 错误：命令包含业务逻辑
@app.command()
def daily(date: str):
    # 不应在 CLI 中写业务逻辑
    data = fetch_data(date)
    transformed = transform(data)
    save(transformed)
```

## 测试规范

### 测试文件位置

```
interfaces/
├── src/ditto_interfaces/
└── tests/
    ├── unit/           # 单元测试
    └── integration/    # 集成测试
```

### 运行测试

```bash
pixi run -e dev test              # 单元测试（并行）
pixi run -e dev test --unit       # 只运行单元测试
pixi run -e dev test --integration # 只运行集成测试
```

## 判断决策树

```
问题：这个组件应该放在 Interfaces 层吗？

1. 是否是 HTTP API？
   YES → Interfaces 层 ✅

2. 是否是 CLI 命令？
   YES → Interfaces 层 ✅

3. 是否是 Prefect Flow/Task？
   YES → Interfaces 层 ✅

4. 是否是流程编排（协调多个服务）？
   YES → Interfaces 层 ✅

5. 是否是业务逻辑（数据处理、策略计算）？
   YES → App 层 (ditto_app) ❌

6. 是否是 DI 注册（Composition Root）？
   YES → Interfaces 层 (registry/) ✅
```
