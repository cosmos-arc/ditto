# Application 层架构规范

## 定位

Application 层是 **Application Layer（应用层）**，负责 Use Case 编排，采用 CQRS 模式组织。

**核心原则**：
- 纯编排层，不包含核心业务逻辑
- 通过 CQRS 模式分离读写职责
- 协调 capability packages（领域计算）+ Data（数据服务）
- 回测 checkpoint 只能在 Application 层转换为运行控制面记录并通过端口写入；Backtest 引擎保持 storage-free；Application 可以持久化并透传 account-state、settlement-state 与 runtime-state（pending OMS orders + delayed signal queue）JSON/hash，但 `ResumeRunHandler` 仍只能创建 checkpoint-backed child run，恢复器消费 account/settlement/runtime state 的完整状态恢复与 replay proof 不得伪装成已完成能力

## 允许依赖

```
ditto_application → ditto_kernel ✅
ditto_application → ditto_data ✅
ditto_application → ditto_strategy ✅
ditto_application → ditto_portfolio ✅
ditto_application → ditto_risk ✅
ditto_application → ditto_execution ✅
ditto_application → ditto_backtest ✅
ditto_application → ditto_features ✅
ditto_application → ditto_platform ✅
```

Application 层允许使用 `ditto_platform.foundation` 和 `ditto_platform.services`（通知、告警等），**禁止**直接使用 `ditto_platform.config`。
配置加载由 Apps 层负责。

## 禁止依赖

```
ditto_application → ditto_apps ❌
```

## 内部目录职责

```
ditto_application/
├── queries/             # 只读查询（零写入）
│   ├── metadata.py    # 元数据查询
│   ├── market.py      # 行情查询
│   ├── capital.py     # 资金查询
│   ├── fundamental.py # 基本面查询
│   ├── macro.py       # 宏观查询
│   ├── fx.py          # 外汇查询
│   ├── commodity.py   # 商品查询
│   ├── source.py      # 数据源查询
│   ├── derived.py     # 衍生数据查询
│   ├── evaluation.py  # 评估查询
│   ├── research.py    # 研究数据集查询
│   ├── forward_return_service.py  # 前向收益率服务
│   ├── _instrument_code_facade.py # 证券代码解析门面
│   ├── _artifact_utils.py        # 共享 artifact 查找 + 回测指标计算
│   ├── backtest.py     # 回测统一查询门面（结果/成交/审计）
│   ├── backtest_trade.py # 回测成交明细查询
│   ├── comparison.py   # 回测 vs 实际对比查询门面
│   ├── comparison_math.py # 回测 vs 实际对比纯计算函数
│   ├── ingestion_status.py # 摄取状态查询
│   ├── lineage.py      # 运行血统查询
│   ├── remediation.py  # Catalog/source/maturity/lineage remediation backlog/detail 查询
│   ├── remediation_approval.py # Catalog remediation approval state/audit-event 查询
│   ├── source_fallback_policy_state.py # Catalog source fallback policy state/audit-event 查询
│   ├── portfolio_actual.py # 实际组合查询（持仓/成交/P&L）
│   ├── run.py          # 回测运行统一查询（列表/过滤）
│   ├── signal.py       # 信号查询（交易意图）
│   ├── strategy.py     # 策略只读查询
│   ├── trade.py        # 交易意图查询
│   └── universe.py     # Universe 只读查询
├── commands/            # Command DTO + Handler（原子写操作）
│   ├── ingestion.py              # IngestDateCommand + IngestDateHandler
│   ├── catalog_remediation.py    # Catalog remediation approval request/decision/execution command
│   ├── source_fallback_policy.py # Catalog source fallback policy draft command
│   ├── quality_check.py          # CheckDataQualityCommand + Handler
│   ├── quality_reconciliation.py # ReconcileSourcesCommand + Handler
│   ├── protocols.py              # CommandHandler Protocol
│   ├── backtest.py               # 回测触发/取消/重试 Command
│   ├── strategy.py               # 策略 Spec CRUD（创建/更新/发布）
│   ├── trade.py                  # 成交录入 + 意图状态更新
│   └── universe.py               # 自定义 Universe CRUD
├── processes/           # Process Manager（有状态长流程）
│   ├── ingestion/      # 数据摄取流程
│   │   ├── coordinator.py           # IngestionCoordinator 主类
│   │   ├── coordinator_factory.py   # create_coordinator 工厂
│   │   ├── config.py                # 摄取配置
│   │   ├── data_writer.py           # 数据写入器
│   │   ├── result_handler.py        # 摄取结果处理器
│   │   ├── metadata_manager.py      # 元数据管理器
│   │   ├── list_date_inference.py   # 上市日期推断
│   │   ├── auto_init.py             # 自动初始化
│   │   ├── backfill_handler.py      # 回填处理器
│   │   ├── backfill_manager.py      # BackfillManager
│   │   ├── retry_manager.py         # RetryManager
│   │   ├── range_process.py         # IngestRangeProcess + BackfillRangeProcess
│   │   ├── source_selection.py      # source=auto selection + fail-closed delegation
│   │   ├── commodity_fetcher.py     # 商品数据获取
│   │   ├── coordinator_constants.py # 共享常量
│   │   ├── dataset_registry.py     # Dataset 摄取路由注册表
│   │   └── fetch_handlers.py        # 获取处理器构建
│   ├── materialization/ # 因子物化流程
│   │   ├── orchestrator.py          # DerivedMaterializationOrchestrator
│   │   ├── cascade_orchestrator.py  # InvalidationCascadeOrchestrator
│   │   ├── publication_facade.py    # 发布门面
│   │   ├── types.py                 # 物化类型定义
│   │   ├── dependencies.py          # 物化依赖
│   │   ├── dependency_refs.py       # 依赖引用解析
│   │   ├── manifest_builder.py      # 物化清单构建器
│   │   ├── minimal_dq.py            # 最小数据质量检查
│   │   ├── helpers.py               # 物化辅助函数
│   │   ├── certification_rules.py   # 认证规则
│   │   ├── factor_orthogonalization.py # 因子正交化
│   │   ├── runtime_input_provider.py   # 运行时输入提供器
│   │   └── publication_helpers.py   # 发布辅助函数
│   ├── execution/      # 策略执行流程
│   │   ├── backtest_process.py      # BacktestService
│   │   ├── strategy_run_process.py  # StrategyRunService + StrategyFacade
│   │   ├── strategy_types.py        # Protocol + Trigger DTO
│   │   ├── strategy_input.py        # StrategyInputAssembler
│   │   ├── backtest_serialization.py # 回测序列化
│   │   ├── comparison.py            # 回测 vs 实际对比计算
│   │   ├── delivery.py              # 信号推送路由器
│   │   ├── factor_bridge.py         # 因子桥接（表达式→编译→信号）
│   │   ├── fee_override.py          # CostConfig 费率覆盖工厂
│   │   ├── manual_tracker.py        # 人工持仓聚合追踪器（T+1 交收）
│   │   ├── replay_process.py        # 回测重放编排
│   │   ├── signal_snapshot.py       # 信号快照 + 交易意图推导
│   │   └── ports.py                 # 人工执行闭环 Port 定义
│   └── quality/        # 质量巡检流程
│       ├── __init__.py              # public API facade
│       └── patrol.py                # QualityPatrolService（原 L3BatchService）
├── builders/           # 运行时装配（DI 构造）
│   ├── runtime_builder.py   # 运行时构建器
│   ├── slice_builder.py     # 切片构建器
│   ├── service_factory.py   # 服务工厂
│   ├── _resolution.py       # 依赖解析工具
│   └── _spec_deserializer.py # 衍生规格反序列化
├── runtime/             # 运行时工具（预留）
├── providers.py            # DI Provider 聚合入口
├── providers_market.py     # 市场数据查询 Provider（13 个 @provide）
├── providers_strategy.py   # 策略/回测查询 Provider（7 个 @provide）
├── providers_portfolio.py  # 组合/交易查询 Provider（3 个 @provide）
├── providers_command.py    # Command Handler DI Provider
├── providers_process.py    # Process 层 DI Provider（编排/物化/质量）
├── providers_builder.py    # Builder 层 DI Provider（策略运行时装配）
├── settings.py             # 应用层设置
├── config/               # 数据集配置（__init__.py + helpers.py + queries.py + specs.py）
├── contracts.py        # 跨 CQRS 子模块共享契约（Command DTO + ReadModel）
├── execution_dto.py    # 执行层 DTO + 跨层映射（TradeIntent/Fill/Snapshot）
└── exceptions.py       # 应用层自定义异常
```

## DI Provider（9 个）

| Provider | 职责 | 注册的服务 |
|----------|------|-----------|
| `AppCommandProvider` | Command Handler | CheckDataQualityHandler, ReviewDatasetPromotionEvidenceHandler, CreateStrategyHandler, UpdateStrategyHandler, PublishStrategyHandler, RecordFillHandler, UpdateIntentStatusHandler, BacktestRunHandler, CancelRunHandler, RetryRunHandler, RunLifecycleService, CreateCustomUniverseHandler, UpdateCustomUniverseHandler, DeleteCustomUniverseHandler |
| `AppMarketQueryProvider` | 市场数据查询 | ForwardReturnService, DerivedQueryFacade, CatalogQueryFacade, MarketQueryFacade, SourceQueryFacade, ResearchDatasetFacade, MetadataQueryFacade, CapitalQueryFacade, FundamentalQueryFacade, MacroQueryFacade, FXQueryFacade, CommodityQueryFacade, UniverseQueryFacade, IngestionStatusQueryFacade |
| `AppStrategyQueryProvider` | 策略/回测查询 | BacktestTradeQueryFacade, BacktestArtifactReader, RunReadModel, StrategyQueryFacade, BacktestQueryFacade, LineageQueryFacade, CatalogRemediationQueryFacade, CatalogRemediationApprovalQueryFacade, ComparisonQueryFacade |
| `AppPortfolioQueryProvider` | 组合/交易查询 | TradeQueryFacade, PortfolioActualQueryFacade, SignalQueryFacade |
| `AppProcessProvider` | 编排/物化/质量/执行 | SQLiteCompileCache, RuntimeDerivedInputProvider, DerivedMaterializationOrchestrator（注入 DataLineageRecorder）, InvalidationCascadeOrchestrator, DerivedPublicationFacade, QualityPatrolService, ManualTracker, ReplayProcess, FactorBridge |
| `AppBuilderFactory` | 策略运行时装配 | StrategyRuntimeBuilder, ServiceBackedDataProvider, BacktestRuntimeBuilder, StrategySliceBuilder, StrategyServiceFactory, StrategyFacade |

## DatasetRegistry 摄取路由规则

- `ditto_application.processes.ingestion.dataset_registry` 是 application ingestion 的唯一数据集运行时路由表。
- 新增数据集时，先在 `ditto_data.models.Dataset` 增加稳定 ID，再在 `ditto_data.catalog.default_dataset_metadata()` 声明 domain/maturity/schedule/source/granularity/freshness SLA，然后在 `default_dataset_registry()` 增加 `DatasetRegistration`。
- `fetch_handlers.py`、`data_writer.py`、`coordinator_constants.py` 不允许新增独立的 `Dataset -> handler` 映射。
- 如果数据源 Protocol 没有按标的方法，不要把该数据集加入 instrument fetch route。
- `Dataset` enum 只保留稳定 ID；source capability、auxiliary source、date/instrument granularity、freshness SLA 由 data-owned catalog metadata 表达，application registry 只保留 fetch/write callback wiring 并在默认 registry 构建时校验 route capability 一致。
- Date-level 和 instrument-level ingestion 必须通过 `source_capability.ensure_source_supported(...)` 在 fetch/identifier resolution 前校验 `source_name`；不得产生 `source=<X>` 但实际走未声明 fetcher 的审计记录。
- `create_coordinator(...)` 通过 registry-like Protocol 按 `source_name + Fetcher Protocol` 组装 `SourceFetchers`；`source=fred` 对 `macro_indicators` 的 macro fetcher 是显式动态路由；`source=auto` 会构建 source-consistent concrete coordinators，再按 catalog freshness/SLA 进行 date/range/instrument delegation；range 必须复用普通 ingestion 的 date schedule helper。Instrument-level `source=auto` 在 `start_date/end_date` 跨多日且存在 date schedule helper 时必须按 date schedule 逐日 source selection、逐日委托 source-consistent concrete coordinator 并聚合 `IngestionResult`；单日或日期不完整的 instrument 请求保留请求 `end_date` / `start_date` 选源语义。选源后、委托 concrete coordinator 前必须复用 data-owned dataset source-capability guard；unsupported selected source 应以结构化 `AppProcessError` fail closed，逐日/按请求选择携带 `operation` 与 `selection_date`，无日期枚举器的 range fallback 携带 `operation`、`start_date` 与 `end_date`，不得调用 concrete coordinator，也不得让 apps/API/frontend 复制 policy。非 macro fetchers 保持 Tushare 默认路径并依赖 catalog guard 阻止误用。
- Date-level、instrument-level 与 adj-factor backfill ingestion 成功写入后通过 `DataLineageRecorder` 记录 source asset/range → data-domain asset/range 的 lineage；该依赖必须由 `IngestionCoordinatorConfig` / composition root 注入，不允许在流程内直接构造具体 store。
- Date-level 与 instrument-level ingestion 成功写入后通过 `DataCatalogWriter` upsert 输出资产 catalog entry（storage URI、schema fingerprint、row count、source、freshness）；该依赖同样必须由 `IngestionCoordinatorConfig` / composition root 注入，不允许在流程内直接构造具体 store。Catalog 尚未成为 routing/freshness source-of-truth 前，不得删除 registry 兼容路径。
- Backtest 成功运行并完成后处理后通过 `DataLineageRecorder` 记录 strategy/version + manifest input refs → `backtest_report` 的 lineage；该 recorder 必须由 `StrategyServiceFactory` / composition root 注入。
- Catalog-backed `BacktestRuntimeBuilder` 与 `StrategySliceBuilder` 必须在解析 universe/benchmark/provider 数据前调用 application-owned `catalog_maturity` gate，并以 data-owned `DatasetMetadata.maturity` 加 persisted `DatasetMaturityPromotionReader` override 为真相源；experimental 数据集默认 fail-closed，只能通过显式 `allow_experimental_data=True` 进入研究路径，或通过 data-owned maturity promotion override 进入默认 runtime。Backtest command/service config JSON 必须持久化 research opt-in，保证 retry/audit 可见。
- Backtest service、artifact writer 与 report serialization 必须把 manifest 中的 PIT policy/time column/unsafe policy/knowledge lag 写入 config/report/artifact metadata；materialization manifest builder 必须把 request `source_snapshot_id` 写入 publication-safety manifest。
- Factor-aware backtest input bundle 的历史窗口必须使用 `ctx.time_context.knowledge_date.isoformat()` 调用 `DataFeed.get_history(...)`，不得使用 `trade_date` 作为历史 as-of；当前交易日 bar 只能来自当前 `StepContext` / `Slice`。
- `MarketQueryFacade.find_bars(...)` / `MarketQueryFacade.list_bars(...)`、`SourceQueryFacade.fetch_source_data(...)`、`FundamentalQueryFacade`、`CapitalQueryFacade` 与 `MacroQueryFacade` 在调用 data service/source service 前，必须对显式 `asset_class`、可识别 `instrument_id` 范围或方法已知的 `dataset` 使用同一 `catalog_maturity` gate；`stock`/`fx`/`commodity`/`stock_daily`/`balance_sheet`/`valuation_metrics`/`macro_indicators` 等 experimental dataset 默认 fail-closed，只能通过显式 `allow_experimental_data=True` 或 persisted maturity promotion override 放行。`instrument_id` 推断必须复用 data-owned `InstrumentIdRange.detect_asset_class(...)` 和 shared maturity helper，不得在 application 复制 maturity policy 或 ID range。
- `LineageQueryFacade` 通过 `DataLineageReader` 暴露 asset-level lineage events、run-level lineage summary 与 upstream/downstream asset graph，并通过 `DataCatalogReader` 暴露 run-level lineage catalog-report；catalog-report 必须保留 exact catalog metadata、固定顺序 catalog status counts、固定顺序 freshness/SLA status counts、带稳定 reason codes 的 input/output attention assets、attention reason counts 和固定顺序 attention severity counts；当调用方提供 `trade_dates` 与 `available_sources` 时，catalog-report 必须通过既有 source-health summary port 对 run input datasets 聚合 `source_fallback_policy_effect_counts`，不得在 lineage facade 复制 fallback policy 决策；所有 lineage read model 只返回 application DTO，API 层不得直接消费 data-layer lineage/catalog DTO 或复制 catalog freshness/triage/source-selection policy。
- `CatalogQueryFacade` 通过 `DataCatalogReader` 暴露 catalog freshness/storage/schema 和 source-health 读模型；source-health report 必须顶层暴露 selected source、其 freshness status 以及稳定 attention reason codes，summary 必须聚合 attention reason counts、`source_selection_status_counts` 和固定顺序 attention severity counts，且 attention item 必须同时保留 `namespace`、`default_source`、`selected_source`、`selected_source_health`、`source_selection_status`、`source_selection_blockers`、`source_fallback_policy_effect` 与 `attention_severity` 以解释 catalog 资产身份、failover/fallback、active policy effect、selected source freshness/storage/schema 证据、blocked readiness 证据和后端 triage 优先级；attention reason 必须组合 freshness reason 与 governance reason，不得因为 selected source 为 fresh 而隐藏 unsupported source 或 latest maturity-promotion revocation；通过 `DatasetMaturityPromotionHistoryReader` 暴露 promotion governance history；只返回 application DTO，API 层不得直接消费 data-layer catalog/promotion DTO 或具体 runtime store。
- 单条 source-health report、summary aggregate 与 summary attention item 必须共享 selected-source readiness 合同：`selected_source_health`、`source_selection_status`、`source_selection_blockers` 与 `source_selection_status_counts`。当 `source=auto` 只能选到不受当前 dataset metadata 支持的来源时，Application 必须返回 blocked DTO 证据，而不是要求 apps/API/frontend 扫描 `sources` 或复制 source-selection policy。
- active fallback policy effect 解析必须保留在 application 共享 helper，供 `AutoSourceIngestionCoordinator` 和 `CatalogQueryFacade` 复用；读侧只暴露 `policy_id`、`policy_status`、catalog-selected source、effective selected source、reason codes 和 recommended actions，不得让 query 层 import ingestion process 或让 apps/API/frontend 自行推断 effect。
- `CatalogQueryFacade.get_source_fallback_policy_preview(...)` / `get_source_fallback_policy_summary(...)` 只能复用 source-health read model 生成 dry-run fallback policy preview/summary，输出 `policy_status`、`recommended_source`、`recommended_actions`、`approval_required`、`execution_allowed`、status/action counts 与 reason/blocker evidence；它不得写入 default source/fallback policy、触发 ingestion、绕过 remediation approval、接触真实 source/broker adapter 或把 policy decision 留给 apps/API/frontend。
- `DraftCatalogSourceFallbackPolicyHandler` 只能把已审阅的 dry-run fallback decision 持久化为 `draft` current-state + append-only audit event；`ApproveCatalogSourceFallbackPolicyHandler` / `ActivateCatalogSourceFallbackPolicyHandler` / `RetireCatalogSourceFallbackPolicyHandler` 只能推进 `draft -> approved -> active -> retired` 的 policy resource lifecycle 并追加 audit event；`active` policy 只能由 `AutoSourceIngestionCoordinator` 作为 exact dataset/date 的 request-scoped `source=auto` selection effect 消费，并且必须经过既有 source capability fail-closed guard。不得改写 DatasetMetadata default source、后台触发 ingestion、注册真实 source/broker adapter、实现产品 UI，或把更广 policy effect/execution 伪装成已完成能力。
- `IngestionStatusQueryFacade` 通过 `DataCatalogReader` 在现有摄取状态读模型中叠加 catalog freshness/storage/schema 字段，并通过 `DatasetMaturityPromotionReader` 应用 persisted metadata maturity override，再通过 `DatasetPromotionEvidenceReader` 读取持久 promotion evidence，从 data-owned `DatasetMetadata.maturity` / `promotion_criteria` 与 `ditto_data.catalog.promotion.assess_dataset_promotion(...)` 暴露 `dataset_maturity`、`dataset_maturity_warning`、`dataset_promotion_criteria`、promotion status 与 missing/satisfied/rejected criteria，同时基于 data-owned `freshness_sla_hours` 输出 `fresh` / `stale` / `missing` / `not_applicable`；maturity governance report 必须从 promotion readiness 复用 status counts、missing/rejected criterion counts 以及 dataset-level required/satisfied/missing/rejected criteria，并顶层暴露带稳定 reason codes 的 `attention_required`、`attention_reason_counts` 与固定顺序 `attention_severity_counts`；当调用方提供 `trade_dates` 与 `available_sources` 时，promotion readiness 和 maturity governance report 必须通过既有 source-health summary port 聚合 `source_fallback_policy_effect_counts`，不得在 ingestion status facade 复制 fallback policy 决策；`summarize_status_by_maturity(...)` 只负责把这些 read-model rows 聚合成 maturity-aware 运维报告摘要、warning count 与 promotion ready/blocked count，不得在此处重新实现 dataset routing、source capability、promotion criteria、promotion evidence policy 或 maturity gating policy。
- `CatalogRemediationQueryFacade` 只组合 `CatalogQueryFacade`、`IngestionStatusQueryFacade` 与可选 `LineageQueryFacade` 已有 read model，输出 backend-owned remediation backlog/detail DTO；它可以把 source-health、maturity-governance 与可选 run-level lineage catalog attention 收敛为稳定 `item_id`、`source`、`severity`、`reasons`、`suggested_actions`、source/reason/severity counts、`source_fallback_policy_effect_counts`、evidence requirements 与 approval intents；source-health remediation item 必须保留 `source_selection_status` / `source_selection_blockers`、候选 `fallback_sources` 与 `source_fallback_policy_effect`，backlog 顶层必须按 policy ID/status/catalog-selected/effective source 聚合同一 active effect 的 item 数量，detail evidence requirements 必须用 dataset/date/selected/default/fallback/blocker context 生成可读可追踪的后端证据项，不得只暴露裸 reason code；相关 manual intent payload 也必须携带这些后端证据和 active policy effect snapshot，blocked selected source 不得生成 `repair_catalog_source_coverage` write intent，只能暴露配置/复核类 manual intent；approval intent 只能指向既有后端合同（例如 promotion evidence review），不得执行自动修复、直接写 store、接触真实券商 adapter 或把修复优先级/审批路由逻辑留给 apps/API/frontend。
- `CatalogRemediationQueryFacade` 在组合 maturity-governance report 与可选 run-level lineage catalog-report 时必须透传归一化后的 `trade_dates` 与 `available_sources`，让已有 source-context policy-effect 诊断在 remediation backlog/detail 组合层保持一致；不得在 remediation facade 复制 fallback policy 决策或由 apps/frontend 补推断。
- `RequestCatalogRemediationApprovalHandler` / `DecideCatalogRemediationApprovalHandler` / `CatalogRemediationApprovalQueryFacade` 只通过 data-owned `CatalogRemediationApprovalReader` / `CatalogRemediationApprovalWriter` 持久化和读取 approval current-state 与 append-only audit events，并映射为 application-owned DTO；approval audit-event 读取面必须经由 query facade 暴露给 FastAPI，不得让 apps/API 直接消费 data-layer remediation DTO。它们不得调用 target intent、执行自动修复、直接触碰 promotion evidence handler、接触真实券商 adapter，或实现产品 UI。若 `repair_catalog_source_coverage` approval request payload 已携带 `source_selection_status="blocked"` 证据，request handler 必须 fail closed，且不得写入 current-state 或 audit event。
- `ExecuteCatalogRemediationApprovalHandler` 只能执行已经处于 `approved` 状态的 remediation approval，并且只能通过 application-owned `CatalogRemediationActionExecutorRegistry` 分发到已注册 action executor；当前 executor 覆盖 `submit_or_fix_promotion_evidence`（复用 `ReviewDatasetPromotionEvidenceHandler`）、`repair_catalog_source_coverage`、`repair_catalog_freshness` 和 `repair_lineage_catalog_asset`（后三者均通过 `CatalogRemediationIngestDatePort` 委派到既有 ingest-date path，`repair_catalog_freshness` 的 approval payload 必须已包含 operator 指定的 `trade_date`）。`review_*`、`configure_*`、`approve_*` 等治理动作只能作为 remediation detail 的 `manual` intent 暴露，`method/path` 必须为空，不得注册成 executor。Unsupported action 必须 fail closed；已存在的 approved `repair_catalog_source_coverage` payload 若携带 blocked source-selection context，也必须在调用 `CatalogRemediationIngestDatePort` 前失败并追加 `execution_failed` audit event；成功后必须通过 approval writer 标记 `completed` 并追加 audit event；不得在 apps/API 层按 path 调 HTTP、自行写 store、触碰真实券商 adapter 或实现产品 UI。
- `IngestDateHandler` 把 process-layer error 映射为 `AppCommandError` 时必须保留底层结构化 `details`，再补充 command/dataset/trade_date/force 上下文；`ExecuteCatalogRemediationApprovalHandler` 捕获任意已注册 executable action 抛出的 typed `AppCommandError` 时必须返回 `status="failed"` execution DTO、保留 error details，并补充 approval_id/item_id/action execution context，追加 `execution_failed` audit event，同时保持 approval 为 `approved` 以便修正后重试；invalid approved payload 必须在 dispatch 下游 handler 前失败并保留同样 execution context；失败 audit notes 必须优先保留后端失败原因，operator notes 只能作为补充上下文，不能覆盖错误证据。
- `ReviewDatasetPromotionEvidenceHandler` 是 reviewer evidence 的唯一 application command 写路径：它必须用 data-owned metadata 校验 dataset/criterion，通过 `DatasetPromotionEvidenceWriter` 持久化，再用 `DatasetPromotionEvidenceReader` 重新 assessment；当 assessment ready 时，必须通过 `DatasetMaturityPromotionWriter` 写入 data-owned metadata promotion override，并返回 `metadata_promoted` / maturity before-after 字段；不得在 apps 层直接写 store 或自行判定 promotion ready。
- `RevokeDatasetMaturityPromotionHandler` 是 maturity promotion reversal 的唯一 application command 写路径：它必须先用 `DatasetMaturityPromotionReader` 验证 current override，再通过 `DatasetMaturityPromotionRevoker` 撤销并记录 data-owned governance event；不得在 apps 层直接删除 override 或写 history。
- `MetadataManager.should_skip()` 可通过 `DataCatalogReader` 在无 log 历史时使用 exact-date catalog entry 作为 fallback skip signal；`force=True`、历史失败重试、source mismatch 必须优先于 catalog skip；stale catalog asset 不得跳过，应进入修复/重摄取路径。
- `RetryManager` 可通过 `DataCatalogReader` 对失败日期进行 repair 优先级排序：missing exact-date catalog asset 优先，其次 stale，fresh 最后；不得绕过 ingestion log 的 source/max_attempts/limit 筛选。
- `AutoSourceIngestionCoordinator` 只做 source selection + delegation；不得在已有 `IngestionCoordinator` 上动态替换 fetchers/source_name/result_handler/data_writer，否则会破坏审计和 catalog lineage 一致性。

## R8 互斥规则（importlinter 强制）

| 方向 | 规则 |
|------|------|
| queries → processes | r8-queries-no-processes ❌ |
| queries → builders | r8-queries-no-builders ❌ |
| queries → commands | r8-queries-no-commands ❌ |
| builders → queries | r8-builders-no-queries ❌ |
| commands → queries | r8-commands-no-queries ❌ |
| commands → builders | r8-commands-no-builders ❌ |
| processes → queries | ✅ 允许（编排可调用查询） |
| processes ↔ builders | ✅ 允许（双向） |
| commands → processes | ✅ 允许（委托执行） |
| processes → commands | ✅ 允许（Process Manager 注入 Handler） |

## 测试位置

```
packages/application/
├── src/ditto_application/
└── tests/
    ├── unit/
    └── integration/
```

## 典型导入示例

```python
from ditto_application.processes.ingestion.coordinator import IngestionCoordinator
from ditto_application.processes.materialization.orchestrator import DerivedMaterializationOrchestrator
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.commands.ingestion import IngestDateCommand, IngestDateHandler
from ditto_application.builders.runtime_builder import StrategyRuntimeBuilder
```

## 常用验证命令

```bash
pixi run -e dev pytest packages/application/tests/ -q
pixi run -e dev type
pixi run -e dev arch-check
```
