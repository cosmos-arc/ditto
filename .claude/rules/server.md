---
paths: apps/server/**/*.py
---

# Server 层规范

## FastAPI 规范

| 要求 | 说明 |
|------|------|
| 路由函数必须类型注解 | 100% 覆盖 |
| 请求/响应用 Pydantic | 类型安全 |
| 异步优先 | @app.get(async=True) |
| 错误用自定义异常 | DataHubError 等 |

| 禁止 | 替代 |
|------|------|
| 全局 State | Depends(get_hub) |
| 直接返回 dict | Pydantic Model |
| 裸 try/except | 自定义异常处理 |

## Prefect 规范

| 要求 | 说明 |
|------|------|
| Flow 必须有 @flow 装饰器 | 声明式编排 |
| Task 必须有 @task 装饰器 | 可追踪执行 |
| 任务依赖用 | wait_for/upstream |
| 重试用 | retry() 装饰器 |

| 禁止 | 替代 |
|------|------|
| 在 Flow 中写业务逻辑 | 抽取到 Task |
| 隐式依赖 | 显式 wait_for |
| 无限重试 | max_attempts=3 |

## 数据摄入任务

| 要求 | 说明 |
|------|------|
| T0 任务优先级最高 | metadata 依赖 |
| T1 任务并行执行 | 无相互依赖 |
| 游标检查 | last_attempted |
| 失败记录 | IngestionLogStore |

| 任务类型 | 触发方式 | 数据集 |
|----------|----------|--------|
| T0 Meta | 每日 8:00 | calendar, basic |
| T1 Incremental | 交易日 18:00 | daily bars |
| T2 Repair | 每日 2:00 | 所有数据集 |
| T3 Quality | T1 完成后 | DQC |

## 导入规范

Server 层导入规则详见 [core.md](.claude/rules/core.md)。
