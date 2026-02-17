# Port 层架构规范

## 定位

Port 层是 **Application Layer（应用层）**，负责：
- 用例编排和事务边界
- FastAPI HTTP API
- Prefect 任务调度
- CLI 命令入口

**核心原则**：
- 协调 Core 和 DataHub，不包含核心业务逻辑
- 通过 DI 容器获取依赖
- 统一的错误处理和日志记录

## 模块结构

```
ditto_port/
├── cli/               # CLI 命令
│   ├── commands/      # 命令实现
│   │   ├── ingest/    # 数据摄入命令
│   │   ├── backfill/  # 回填命令
│   │   └── query/     # 查询命令
│   └── utils/         # CLI 工具
├── jobs/              # Prefect 任务
│   ├── flows/         # Flow 定义
│   └── tasks/         # Task 实现
├── services/          # 应用服务（待实现）
└── registry/          # DI 容器配置
```

## 依赖规则

```
┌─────────────────────────────────────┐
│  Port 可依赖                        │
│  port → core ✅                     │
│  port → datahub ✅                  │
│  port → infra ✅                    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Port 禁止被依赖                    │
│  core → port ❌                     │
│  datahub → port ❌                  │
└─────────────────────────────────────┘
```

### 层级访问规则

| 访问类型 | ✅ 允许 | ❌ 禁止 |
|---------|--------|--------|
| **通过 Domain Service** | `MetadataService`, `MarketService` | - |
| **直接导入 Sources** | `from ditto_datahub.sources.*` | - |
| **直接导入 Stores** | - | `from ditto_datahub.stores.*` |

```python
# ✅ 正确：通过 DI 容器注入 Service
from ditto_datahub.services import MetadataService
service: MetadataService = container.get(MetadataService)

# ✅ 正确：通过 Service 获取数据
bars = service.get_bars(query)

# ❌ 错误：直接访问 Store
from ditto_datahub.stores import BarsReader  # ❌
reader = BarsReader(...)  # ❌
```

## FastAPI 规范

| 要求 | 说明 |
|------|------|
| 路由函数必须类型注解 | 100% 覆盖 |
| 请求/响应用 Pydantic | 类型安全 |
| 异步优先 | `async def` |
| 错误用自定义异常 | `DataHubError` 等 |

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
| 在 Flow 中写业务逻辑 | 抽取到 Task 或 Core |
| 隐式依赖 | 显式 `wait_for` |
| 无限重试 | `max_attempts=3` |

## 数据摄入 T0/T1/T2/T3

| 层级 | 职责 | 调度时机 |
|------|------|----------|
| T0 | 元数据（calendar, basic） | 每日 8:00-9:00 |
| T1 | 增量数据（daily bars） | 交易日 18:00 |
| T2 | 空洞扫描 + 回填 | 每日凌晨 2:00 |
| T3 | 质量检查 | T1 完成后 |

### 游标管理

| 操作 | 说明 |
|------|------|
| 检查 `last_attempted` | 失败重试前 |
| 更新 `last_success` | 成功写入后 |

## CLI 规范

### 命令结构

```bash
# 数据摄入
pixi run ingest daily --date 2024-01-15
pixi run ingest backfill --start 2024-01-01 --end 2024-01-31

# 查询
pixi run query bars --instrument 000001.SZ --start 2024-01-01
```

### 命令实现规范

```python
# ✅ 正确：命令只负责参数解析和调用服务
@click.command()
@click.option("--date", required=True)
def daily(date: str):
    service = get_ingestion_service()
    service.ingest_daily(date)

# ❌ 错误：命令包含业务逻辑
@click.command()
def daily(date: str):
    # 不应在 CLI 中写业务逻辑
    data = fetch_data(date)
    transformed = transform(data)
    save(transformed)
```

## 测试规范

### 测试文件位置

```
apps/port/
├── src/ditto_port/
└── tests/
    ├── unit/           # 单元测试
    └── integration/    # 集成测试
```

### 运行测试

```bash
pixi run -e dev pytest apps/port/tests/
```

## 判断决策树

```
问题：这个组件应该放在 Port 层吗？

1. 是否是 HTTP API？
   YES → Port 层 ✅

2. 是否是 CLI 命令？
   YES → Port 层 ✅

3. 是否是 Prefect Flow/Task？
   YES → Port 层 ✅

4. 是否是流程编排（协调多个服务）？
   YES → Port 层 ✅

5. 是否是核心业务逻辑？
   YES → Core 层 ❌

6. 是否是数据存储？
   YES → DataHub 层 ❌
```
