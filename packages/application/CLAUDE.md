# Application 层架构规范

## 定位

Application 层是 **Application Layer（应用层）**，负责 Use Case 编排，采用 CQRS 模式组织。

**核心原则**：
- 纯编排层，不包含核心业务逻辑
- 通过 CQRS 模式分离读写职责
- 协调 capability packages（领域计算）+ Data（数据服务）

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
│   ├── portfolio_actual.py # 实际组合查询（持仓/成交/P&L）
│   ├── run.py          # 回测运行统一查询（列表/过滤）
│   ├── signal.py       # 信号查询（交易意图）
│   ├── strategy.py     # 策略只读查询
│   ├── trade.py        # 交易意图查询
│   └── universe.py     # Universe 只读查询
├── commands/            # Command DTO + Handler（原子写操作）
│   ├── ingestion.py              # IngestDateCommand + IngestDateHandler
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
│   │   ├── commodity_fetcher.py     # 商品数据获取
│   │   ├── coordinator_constants.py # 共享常量
│   │   └── fetch_handlers.py        # 获取处理器构建
│   ├── materialization/ # 因子物化流程
│   │   ├── orchestrator.py          # DerivedMaterializationOrchestrator
│   │   ├── cascade_orchestrator.py  # InvalidationCascadeOrchestrator
│   │   ├── publication_facade.py    # 发布门面
│   │   ├── types.py                 # 物化类型定义
│   │   ├── dependencies.py          # 物化依赖
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
│       ├── __init__.py              # re-export shim
│       └── patrol.py                # QualityPatrolService（原 L3BatchService）
├── builders/           # 运行时装配（DI 构造）
│   ├── runtime_builder.py   # 运行时构建器
│   ├── slice_builder.py     # 切片构建器
│   ├── service_factory.py   # 服务工厂
│   ├── _resolution.py       # 依赖解析工具
│   └── _spec_deserializer.py # 衍生规格反序列化
├── runtime/             # 运行时工具（预留）
├── providers.py            # DI Provider 聚合入口（6 个 Provider）
├── providers_market.py     # 市场数据查询 Provider（13 个 @provide）
├── providers_strategy.py   # 策略/回测查询 Provider（7 个 @provide）
├── providers_portfolio.py  # 组合/交易查询 Provider（3 个 @provide）
├── config.py           # 数据集配置
├── contracts.py        # 跨 CQRS 子模块共享契约（Command DTO + ReadModel）
└── execution_dto.py    # 执行层 DTO + 跨层映射（TradeIntent/Fill/Snapshot）
```

## DI Provider（6 个）

| Provider | 职责 | 注册的服务 |
|----------|------|-----------|
| `AppCommandProvider` | Command Handler | CheckDataQualityHandler, CreateStrategyHandler, UpdateStrategyHandler, PublishStrategyHandler, RecordFillHandler, UpdateIntentStatusHandler, BacktestRunHandler, CancelRunHandler, RetryRunHandler, RunLifecycleService, CreateCustomUniverseHandler, UpdateCustomUniverseHandler, DeleteCustomUniverseHandler |
| `AppMarketQueryProvider` | 市场数据查询 | ForwardReturnService, DerivedQueryFacade, MarketQueryFacade, SourceQueryFacade, ResearchDatasetFacade, MetadataQueryFacade, CapitalQueryFacade, FundamentalQueryFacade, MacroQueryFacade, FXQueryFacade, CommodityQueryFacade, UniverseQueryFacade, IngestionStatusQueryFacade |
| `AppStrategyQueryProvider` | 策略/回测查询 | BacktestTradeQueryFacade, BacktestArtifactReader, RunReadModel, StrategyQueryFacade, BacktestQueryFacade, LineageQueryFacade, ComparisonQueryFacade |
| `AppPortfolioQueryProvider` | 组合/交易查询 | TradeQueryFacade, PortfolioActualQueryFacade, SignalQueryFacade |
| `AppProcessProvider` | 编排/物化/质量/执行 | SQLiteCompileCache, RuntimeDerivedInputProvider, DerivedMaterializationOrchestrator, InvalidationCascadeOrchestrator, DerivedPublicationFacade, QualityPatrolService, ManualTracker, ReplayProcess, FactorBridge |
| `AppBuilderFactory` | 策略运行时装配 | StrategyRuntimeBuilder, ServiceBackedDataProvider, BacktestRuntimeBuilder, StrategySliceBuilder, StrategyServiceFactory, StrategyFacade |

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
