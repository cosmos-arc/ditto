# Apps 层架构规范

## 定位

Apps 层是 **Application Boundary Layer（应用边界层）**，负责：
- HTTP API（FastAPI）
- CLI 命令入口
- Prefect 任务调度（Flow/Task）
- DI 容器组装（Composition Root）

产品 UI、前端页面和交互工作流不属于本仓库范围；`ditto-app` 独立前端项目负责 UI。本包只暴露后端 FastAPI、CLI/jobs 编排、OpenAPI metadata、DTO 和 JSON/CLI report surfaces。

**核心原则**：
- 纯编排层，不包含业务逻辑
- 通过 DI 容器获取依赖
- 业务逻辑已迁入 `ditto_application` 包
- 不实现产品 UI 或前端状态管理；只提供后端接口和可供前端消费的状态/证据 DTO
- 回测 `/resume` API 只能提交 Application 已创建的 checkpoint-backed child run；不得在 Apps 层自行解释 checkpoint、account-state/settlement-state/runtime-state evidence 或恢复账户/订单/信号队列状态

## 内部目录职责

```
ditto_apps/
├── api/               # API 路由
│   └── utils/         # API 工具（identifier）
├── cli/               # CLI 命令
│   ├── main.py        # CLI 入口
│   ├── context.py     # CLI 上下文
│   ├── executor.py    # 命令执行器
│   ├── commands/      # 命令实现
│   │   ├── factory.py # 命令工厂
│   │   ├── init.py    # 初始化命令
│   │   ├── ops.py     # 运维命令
│   │   ├── strategy.py # 策略命令
│   │   ├── ingest/    # 数据摄入命令（capital/fundamental/macro/market/metadata）
│   │   ├── backfill/  # 回填命令（capital/fundamental/macro/market/metadata）
│   │   └── query/     # 查询命令（capital/fundamental/macro/market/metadata）
│   └── utils/         # CLI 工具（identifier/output/params/validation）
├── jobs/              # Prefect 任务
│   ├── context.py     # 任务上下文
│   ├── flows/         # Flow 定义（backfill/backtest/daily/deploy/eod/materialization/repair/research）
│   └── tasks/         # Task 实现（aliases/dq_batch/monitoring/t0_meta）
├── models/            # API 数据模型（Pydantic）（backtest/capital/commodity/fundamental/fx/ingestion/lineage/macro/market/metadata/strategy/trade/universe）
├── services/          # 已清空（业务逻辑已迁入 ditto_application）
├── registry/          # DI 容器（Dishka Composition Root）
│   ├── container.py   # 容器定义
│   ├── init_providers.py  # Provider 初始化
│   ├── contexts/      # DI 上下文（bundle/ingestion/materialization/query/strategy）
│   └── infra/         # 基础设施配置（config/notification/observability/signal_delivery）
│       ├── _factory.py                # Provider 工厂
│       ├── config.py                  # 基础设施配置
│       ├── init_providers.py          # Provider 初始化
│       ├── notification.py            # 通知模块
│       ├── observability.py           # 可观测性模块
│       ├── protocol_adapters.py       # Protocol 适配器（SourceAccessor → DataPort）
│       ├── signal_delivery.py         # 信号推送
│       └── notification_templates/    # 通知模板（dq_failure/signal_trading × email/telegram/webhook）
├── config/            # 配置加载
│   └── loader.py      # 环境配置加载器
├── middleware.py       # ASGI 中间件
├── testing.py         # 测试工具
├── exceptions.py      # 自定义异常
└── main.py            # 启动入口
```

## 允许依赖

```
apps → application ✅
apps → platform ✅
apps.registry → data/features/strategy/portfolio/risk/execution/backtest/analysis ✅
apps.jobs.context → ditto_data.quality ✅ (narrow DQ engine lookup)
apps.jobs.tasks.{dq_batch,monitoring} → ditto_data.quality.quality_types ✅ (DQ type annotations for task signatures)
```

## 禁止依赖

```
application → apps ❌
strategy → apps ❌
data → apps ❌
features → apps ❌
```

### 层级访问规则

| 访问类型 | ✅ 允许 | ❌ 禁止 |
|---------|--------|--------|
| **Application 层服务** | `from ditto_application.processes.*` | - |
| **Application 层查询** | `from ditto_application.queries.*` | - |
| **Application 层配置** | `from ditto_application.config` | - |
| **Capability 实现** | registry 内仅限 DI 注册 | 非 registry 代码直接导入 |
| **Data Service / Sources** | registry 内 DI 注册；普通入口走 application facade | 非 registry 代码直接访问 |
| **Data Stores / Runtime** | registry 内仅限 DI 注册 | 非 registry 代码 |

### Registry 豁免边界

`registry/**` 是 Composition Root，允许直接导入 Data 层 services/quality/config 和各能力包实现以完成 DI 装配。
**这是明确的 host composition 边界**，不把 route、CLI、job 入口也变成业务对象装配点。

豁免范围（importlinter `port-service-isolation` 合约已显式配置）：

| 文件 | 依赖 | 用途 |
|------|------|------|
| `registry/container.py` | `ditto_data.di` | DI 容器组装 |
| `registry/contexts/ingestion.py` | Data services + runtime lineage recorder + runtime catalog writer/reader + source fallback policy reader + SourceRegistry | 构建 IngestionBundle |
| `registry/contexts/bundle.py` | `ditto_data.sources` | ExchangeTransformers |
| `registry/infra/config.py` | `ditto_data.config`, `quality.config` | 环境配置加载 |

Registry/container wiring provides the data runtime lineage recorder/reader protocols consumed by application providers for materialization, ingestion, backtest services and lineage query facade, the runtime catalog writer/reader plus source fallback policy reader plus promotion evidence/maturity/history/revoker plus remediation approval reader/writer ports consumed by ingestion, catalog query facade, ingestion status facade, exact-date skip policy, retry repair prioritization and date/range-level plus instrument request-date `source=auto` selection, and the SourceRegistry consumed by ingestion coordinator construction for macro-only dynamic FRED routing. API routes consume application DTOs for asset-level lineage event, run-level lineage summary, asset graph, run-level lineage catalog-report status counts, freshness/SLA status counts, attention reason codes, reason counts, backend-owned attention severity counts and source-fallback-policy-effect-count DTOs, catalog freshness/storage/schema reads, source-health selected-source freshness status, source-selection status counts, active `source_fallback_policy_effect` evidence, namespace/default-source-aware attention items with selected-source evidence and blocker context, attention reason codes, summary-level reason counts and backend-owned attention severity counts, promotion history/reversal, promotion readiness source-fallback-policy-effect-count DTOs, status catalog freshness/SLA/maturity/warning/criteria/assessment overlay, maturity-governance criterion counts plus required/satisfied/missing/rejected drill-down, attention reason codes, reason counts, backend-owned attention severity counts and source-fallback-policy-effect-count DTOs, and catalog remediation backlog/detail item/source/reason/severity/action/source-selection blocker/source-fallback-policy-effect/source-fallback-policy-effect-count/evidence-requirement/approval-intent DTOs plus remediation approval-state request/decision/get/list/event-read/execution DTOs, not data-layer lineage/catalog/promotion/remediation DTOs.

Source-health FastAPI response models must faithfully expose application-level `selected_source_health`, `source_selection_status` and `source_selection_blockers` for single reports, summary report details and summary attention items, plus summary-level `source_selection_status_counts`. Apps routes must not infer blocked/ready state by rescanning source arrays, duplicate source-selection policy, implement product UI behavior, or create real source/broker adapters.

Catalog remediation FastAPI response models must faithfully expose application-level `source_selection_status`, `source_selection_blockers` and `source_fallback_policy_effect` on backlog/detail items, plus report-level `source_fallback_policy_effect_counts` on backlog responses. Apps routes must not re-add executable remediation actions for blocked selected sources, infer fallback policy, implement product UI behavior, or create real source/broker adapters.

Catalog source-health, promotion readiness, maturity governance, lineage catalog-report and remediation API mapping must pass through application-owned `source_fallback_policy_effect` DTOs/counts without inferring active policy effects in apps. Catalog source-fallback policy routes may expose backend draft/lifecycle/current-state/audit-event contracts only. Apps composition may wire `CatalogSourceFallbackPolicyReader` into ingestion coordinator construction and catalog query facade construction so application-owned `source=auto`, source-health reports, source-context promotion readiness, maturity governance and lineage catalog reports can consume active exact-date policy effects. Apps routes must not duplicate source-selection policy, mutate default source metadata, trigger ingestion from policy lifecycle endpoints, implement product UI behavior, or create real source/broker adapters.

OpenAPI schema generation is maturity-aware through `ditto_apps.api.maturity`.
Every documented path operation must include `x-ditto-maturity` and a visible
`Capability maturity: ...` description note. New route prefixes must be added
to `ROUTE_MATURITY_BY_PREFIX` and the route maturity table in
`docs/architecture/capability-maturity.md` together; the apps architecture
test suite parses the manifest table and fails on drift.

`/ingestion/status` and `ditto ops status --json` expose a
`maturity_summary` report grouped by data-owned dataset maturity, plus
per-dataset maturity warning, promotion criteria, promotion assessment and
rejected promotion criteria fields. Apps may map the application summary/status
DTOs to API/CLI response shapes, but must not duplicate freshness, maturity,
promotion criteria or promotion evidence policy.

`POST /ingestion/catalog/promotion/evidence` and
`ditto ops promotion-review` are the public reviewer evidence write paths.
They must delegate to `ReviewDatasetPromotionEvidenceHandler`; apps must not
write `DatasetPromotionEvidenceWriter` directly or decide whether a dataset is
promotion-ready. Apps may expose `metadata_promoted` and maturity before/after
fields returned by the handler, but must not write or interpret
`DatasetMaturityPromotionWriter` directly.

`GET /ingestion/catalog/promotion/history`,
`POST /ingestion/catalog/promotion/revoke`, `ditto ops promotion-history` and
`ditto ops promotion-revoke` are the public promotion governance history and
reversal paths. They must delegate to `CatalogQueryFacade` or
`RevokeDatasetMaturityPromotionHandler`; apps must not directly read promotion
event stores, delete active overrides, or synthesize revoke history.

Backtest API, strategy CLI, and market/source/fundamental/capital/macro query APIs may expose
experimental data use only through explicit default-off controls named
`allow_experimental_data` or `--allow-experimental-data`. These controls must
pass through application options/commands/facades and must not bypass the
catalog-backed maturity gate.

`/market/bars` may expose `asset_class`, `instrument_ids` and default-off
`allow_experimental_data`, but apps must only pass these values to
`MarketQueryFacade`; dataset maturity, instrument-ID inference, promotion
overrides and fail-closed policy belong in application/data-owned catalog
helpers, not route handlers.

`/source/{source}/{dataset}` may expose default-off `allow_experimental_data`,
but apps must only pass it to `SourceQueryFacade`; supported raw-data dataset
maturity and promotion policy belong in the same application/data-owned catalog
helpers.

`/fundamental`, `/capital`, and `/macro` routes and matching `ditto query`
commands may expose default-off experimental data controls, but apps must only
pass them to the relevant query facade; explicit dataset maturity and promotion
policy stay in application/data-owned catalog helpers.

**非 registry 代码禁止直接访问 Data services/models**。

此外，非 registry 代码也禁止直接导入 strategy/portfolio/risk/execution/backtest/features/analysis/data 等能力包实现；普通入口应通过 `ditto_application` 的 commands、queries、processes 或显式 facade 访问。当前仅 `jobs/context.py` 保留 Data Quality 引擎查找的窄豁免，架构 smell guard 会检查这条规则。
该豁免以 `APPS_HOST_COMPOSITION_ALLOWANCES` 作为唯一 enforcement source，必须带 owner/reason。

### 业务逻辑去向

业务逻辑已迁移到 `ditto_application` 包中：

| 原位置 | 新位置 | 内容 |
|--------|--------|------|
| `services/ingestion/` | `ditto_application.processes.ingestion` | 数据摄取服务 |
| `services/ingestion/quality/` | `ditto_application.processes.quality` | 质量校验服务 |
| `services/strategy/` | `ditto_application.processes.execution` | 策略运行服务 |
| `services/strategy/*.builder` | `ditto_application.builders.strategy` | 策略构建器 |
| `services/derived/materialization*` | `ditto_application.processes.materialization` | 衍生物化服务 |
| `services/derived/query_facade*` | `ditto_application.queries.derived` | 衍生查询服务 |
| `services/derived/research*` | `ditto_application.queries.research` | 研究数据集服务 |
| `models/config` | `ditto_application.config` | 数据集配置 |
| `models/ingestion` | `ditto_data.models.ingestion` | 摄取结果类型 |

## FastAPI 规范

| 要求 | 说明 |
|------|------|
| 路由函数必须类型注解 | 100% 覆盖 |
| 请求/响应用 Pydantic | 类型安全 |
| 异步优先 | `async def` |
| 错误用自定义异常 | `DataError` 层级异常 |

| 禁止 | 替代 |
|------|------|
| 全局 State | `Depends(get_hub)` |
| 直接返回 dict | Pydantic Model |
| 裸 try/except | 自定义异常处理 |

### API 路由分组

| Prefix | Tag | 模块 | 说明 | 成熟度 |
|--------|-----|------|------|--------|
| `/backtests` | backtests | `api/routes/backtest.py` | 回测运行/报告/重放 | initial-focus |
| `/capital` | capital | `api/routes/capital.py` | Capital 域查询；显式 experimental dataset 必须透传 application maturity gate | experimental |
| `/commodity` | commodity | `api/routes/commodity.py` | 商品数据查询（POST 复用 `shared_bars.py`） | experimental |
| `/fundamental` | fundamental | `api/routes/fundamental.py` | 基本面数据查询；显式 experimental dataset 必须透传 application maturity gate | experimental |
| `/fx` | fx | `api/routes/fx.py` | 外汇数据查询（POST 复用 `shared_bars.py`） | experimental |
| `/ingestion` | ingestion | `api/routes/ingestion.py` | 数据摄取状态 + catalog freshness/storage/schema/maturity/warning/criteria/assessment 查询/status overlay | infrastructure |
| `/macro` | macro | `api/routes/macro.py` | 宏观经济数据查询；显式 experimental dataset 必须透传 application maturity gate | experimental |
| `/market` | market | `api/routes/market.py` | 行情数据查询；显式 experimental asset_class 和可识别 instrument_id 必须透传 application maturity gate | initial-focus |
| `/metadata` | metadata | `api/routes/metadata.py` | 元数据查询 | initial-focus |
| `/source` | source | `api/routes/source.py` | Source 数据查询；显式 experimental dataset 必须透传 application maturity gate | infrastructure |
| `/strategies` | strategies | `api/routes/strategy.py` | 策略 CRUD + 发布 | initial-focus |
| `/trade` | trade | `api/routes/trade.py` | 交易闭环（意图/成交/持仓/盈亏/对比） | experimental |
| `/universes` | universes | `api/routes/universe.py` | Universe 管理 | initial-focus |
| `/api/v1/logs` | debug | `api/routes/debug.py` | 调试端点（仅非生产环境） | debug |

成熟度定义见 `docs/architecture/capability-maturity.md`。非 initial-focus 路由的模块 docstring 必须包含 `maturity:` 标注。

## Prefect 规范

| 要求 | 说明 |
|------|------|
| Flow 必须有 `@flow` 装饰器 | 声明式编排 |
| Task 必须有 `@task` 装饰器 | 可追踪执行 |
| 任务依赖用 | `wait_for`/`upstream` |
| 重试用 | `retry()` 装饰器 |

| 禁止 | 替代 |
|------|------|
| 在 Flow 中写业务逻辑 | 抽取到 Task 或 `ditto_application` |
| 隐式依赖 | 显式 `wait_for` |
| 无限重试 | `max_attempts=3` |

## 数据摄入

Apps 层通过 CLI/Jobs 编排数据摄取流程，业务逻辑在 `ditto_application.processes.ingestion` 中。
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

## 测试位置

```
apps/
├── src/ditto_apps/
└── tests/
    ├── unit/           # 单元测试
    └── integration/    # 集成测试
```

## 典型导入示例

```python
from ditto_apps.cli.main import create_cli
from ditto_apps.api.main import create_app
from ditto_apps.jobs.flows.daily import daily_flow
from ditto_apps.registry.container import AppContainer
from ditto_apps.config.loader import load_config
```

## 常用验证命令

```bash
pixi run -e dev test              # 单元测试（并行）
pixi run -e dev test --unit       # 只运行单元测试
pixi run -e dev test --integration # 只运行集成测试
pixi run -e dev type
pixi run -e dev arch-check
```

## 判断决策树

```
问题：这个组件应该放在 Apps 层吗？

1. 是否是 HTTP API？
   YES → Apps 层 ✅

2. 是否是 CLI 命令？
   YES → Apps 层 ✅

3. 是否是 Prefect Flow/Task？
   YES → Apps 层 ✅

4. 是否是流程编排（协调多个服务）？
   YES → Apps 层 ✅

5. 是否是业务逻辑（数据处理、策略计算）？
   YES → Application 层 (ditto_application) ❌

6. 是否是 DI 注册（Composition Root）？
   YES → Apps 层 (registry/) ✅
```
