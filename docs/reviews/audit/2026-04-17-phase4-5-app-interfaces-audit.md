# Phase 4+5: App + Interfaces 审计报告

> **日期**: 2026-04-17
> **范围**: packages/app (95 文件, 16,456 行) + interfaces (98 文件, 11,911 行)
> **架构检查**: 24 条契约全部通过

---

## App 审计发现

### P1（5 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| AP-P1-1 | CancelRunHandler/RetryRunHandler 未使用 Command DTO | `command/backtest.py:212,245` | 直接接受 `str` 参数，违反 Command DTO 统一模式 |
| AP-P1-2 | ReconcileSourcesHandler 未在 Provider 注册 | `command/quality_reconciliation.py` | DI 容器无法注入 |
| AP-P1-3 | IngestDateHandler 未在 Provider 注册 | `command/ingestion.py:41` | 通过 Protocol 替代但未明确文档 |
| AP-P1-4 | FactorEvaluationFacade 未在 Provider 注册 | `query/evaluation.py:47` | DI 遗漏 |
| AP-P1-5 | DeliveryRouter/SignalSnapshotProcess 未注册 | `process/execution/delivery.py:21`, `signal_snapshot.py:28` | DI 遗漏 |

### P2（4 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| AP-P2-1 | coordinator.py 733 行，app 包最大文件 | `process/ingestion/coordinator.py` | 承担过多职责 |
| AP-P2-2 | helpers.py 503 行 | `process/materialization/helpers.py` | materialization 子域偏大 |
| AP-P2-3 | patrol.py 直接依赖 query Facade 类而非 Protocol | `process/quality/patrol.py:19-20` | 耦合度偏高 |
| AP-P2-4 | command/__init__.py re-export 18 个符号 | `command/__init__.py` | 偏多，Handler 应由 Provider 直接导入 |

### P3（3 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| AP-P3-1 | ForwardReturnService 命名与 query 模块不一致 | `query/forward_return_service.py:22` | Service 后缀暗示 process 层 |
| AP-P3-2 | 4 处 `except Exception:` 裸异常（均有日志） | 多文件 | 全部合理但标记 |
| AP-P3-3 | FactorEvaluationFacade 命名语义模糊 | `query/evaluation.py:47` | 实为评估服务而非纯门面 |

### App 四维评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构** | 9/10 | CQRS 四象限互斥严格，R8 规则全部通过，process 四子域清晰 |
| **抽象** | 8/10 | Command DTO + Handler 模式一致，5 个 Handler 未使用 DTO |
| **依赖** | 10/10 | 零 interfaces 依赖，零 infra.config 依赖，CQRS 依赖方向正确 |
| **实践** | 9/10 | 类型标注 ~100%，DTO 最小化，builder 无业务逻辑泄漏 |

### 积极发现
- **R8 互斥规则 6 条禁止方向全部通过** — 量化框架中无先例
- **Query Facade 23 个全部只读** — 无写入操作
- **process 四子域边界清晰** — ingestion/materialization/execution/quality
- **contracts.py + execution_dto.py 共享 DTO 最小化** — 明确文档说明规避 R8

---

## Interfaces 审计发现

### P1（1 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| IF-P1-1 | e2e 测试直接导入 `ditto_data.storage.*` | `tests/e2e/` 6 个文件 | 绕过 DI 容器，降低测试架构保真度 |

### P2（13 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| IF-P2-1 | trade.py `get_deviation` 包含偏差计算业务逻辑 | `api/routes/trade.py:338-385` | 应下沉到 App 层 |
| IF-P2-2 | backtest.py 辅助函数过多 + Flow 执行逻辑泄漏 | `api/routes/backtest.py:130-191` | 包含进程内执行和序列化 |
| IF-P2-3 | source.py 裸 Exception + 字符串匹配异常类型 | `api/routes/source.py:86-91` | 脆弱，应用 isinstance |
| IF-P2-4 | get_report/get_nav_series 返回 `dict[str,object]` | `api/routes/backtest.py:398,471` | 应返回 Pydantic 模型 |
| IF-P2-5 | source.py 内联定义 Request/Response 模型 | `api/routes/source.py:99-131` | 其他路由模型在 models/ |
| IF-P2-6 | `_KNOWN_DATASETS` 在 3 处重复定义 | api/cli/jobs 多文件 | 应抽取为共享常量 |
| IF-P2-7 | ops.py 表格格式化逻辑应迁移到 utils | `cli/commands/ops.py:51-121` | presentation 层混合 |
| IF-P2-8 | eod_flow.py 硬编码 StrategyRunMode.RESEARCH | `jobs/flows/eod.py:112` | 业务决策应配置化 |
| IF-P2-9 | backtest Flow 包含 CostConfig 反序列化 | `jobs/flows/backtest.py:125-173` | 应在 App 层完成 |
| IF-P2-10 | dq_batch.py 222 行编排逻辑 | `jobs/tasks/dq_batch.py:85-306` | `_DEFAULT_DATASETS` 第三次重复 |
| IF-P2-11 | backtest 模型硬编码成本常量 | `models/backtest.py:17-20` | 应从 Engine 层导入 |
| IF-P2-12 | SignalDeliveryProvider 未在顶层 re-export | `registry/__init__.py` | re-export 遗漏 |
| IF-P2-13 | QueryContext/create_query_context 未在顶层 re-export | `registry/__init__.py` | re-export 遗漏 |

### P3（9 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| IF-P3-1 | 5 个模型文件重复 validate_date_range | models/ 多文件 | 未复用 _date_helpers |
| IF-P3-2 | macro.py 重新定义 DateField | `models/macro.py:49` | 应复用 _date_helpers.DateField |
| IF-P3-3 | materialization/research 重复 _normalize_results | `jobs/flows/` 2 个文件 | 应抽取共享工具 |
| IF-P3-4 | cli/utils/params.py 使用 click 而非 typer | `cli/utils/params.py:7` | 风格不一致 |
| IF-P3-5 | testing.py 直接导入 duckdb | `testing.py:8` | 绕过 DI |
| IF-P3-6 | jobs/context.py 返回类型为 Any | `jobs/context.py:16,26` | 可改为 Container |
| IF-P3-7 | QueryContext 定义位置不一致 | `registry/contexts/query.py` | 应在 bundle.py |
| IF-P3-8 | Flow 返回类型不统一 | 多个 Flow | dict vs Pydantic |
| IF-P3-9 | jobs/tasks 导入 ditto_data.models.Dataset | `jobs/tasks/dq_batch.py:10` 等 | 理想从 kernel 导入 |

### Interfaces 四维评分

| 维度 | 评分 | 说明 |
|------|------|------|
| **架构** | 9/10 | 薄层设计良好，services/ 清理彻底，边界规则 src/ 全部通过 |
| **抽象** | 8/10 | Bundle 模式一致，API 模型无重复，但 3 处常量/函数重复 |
| **依赖** | 9/10 | 禁止方向全部通过，仅 tests/ 有 storage 直接导入 |
| **实践** | 8/10 | 错误处理分层清晰，但有业务逻辑泄漏和类型弱化 |

### 积极发现
- **services/ 清理彻底** — 全项目搜索零活跃引用
- **依赖方向完美遵守** — app/data/kernel/engine/analytics 均未依赖 interfaces
- **Bundle 模式高度一致** — 4 个 Bundle 统一 frozen dataclass + try/finally 容器关闭
- **错误处理分层清晰** — API/CLI/Jobs 三层各有统一错误模式
- **路由与 App 层对应关系清晰** — 15 个路由模块对应 23 个 Query Facade + 8 个 Command Handler

---

## 业界对标

### App CQRS

| 维度 | Ditto | Cosmic Python | 差距 |
|------|-------|---------------|------|
| **四象限互斥** | R8 机器执行 | 手动约定 | **领先** |
| **Command DTO** | 8 个 frozen dataclass | DTO pattern | 对标 |
| **Query 只读** | 23 个 Facade 全只读 | Query side | 对标 |
| **编排层** | process/ 4 子域 | Service layer | 更细粒度 |

### Interfaces

| 维度 | Ditto | OpenBB | Databento | 差距 |
|------|-------|--------|-----------|------|
| **薄层设计** | 良好 | Plugin 扩展 | zero-compute | 基本对标 |
| **DI Composition Root** | Bundle 模式 | - | - | **领先** |
| **CLI 覆盖** | 28 命令 | Typer CLI | - | 充分 |
| **Jobs 编排** | Prefect Flow | - | - | 对标 |
