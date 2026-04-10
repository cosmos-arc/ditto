# App 层架构规范

## 定位

App 层是 **Application Layer（应用层）**，负责 Use Case 编排，采用 CQRS 模式组织。

**核心原则**：
- 纯编排层，不包含核心业务逻辑
- 通过 CQRS 模式分离读写职责
- 协调 Engine（领域计算）+ Data（数据服务）

## 依赖

```
ditto_app → ditto_kernel ✅
ditto_app → ditto_data ✅
ditto_app → ditto_engine ✅
ditto_app → ditto_analytics ✅
ditto_app → ditto_infra ✅
ditto_app 禁止 → ditto_interfaces ❌
```

## App→Infra Scope 限制

App 层仅允许使用 `ditto_infra.foundation`（缓存、配置、日志、工具），**禁止**直接使用 `ditto_infra.services`（通知等）。
通知编排应在 Interfaces 层完成。

## CQRS 模块结构

```
ditto_app/
├── query/              # 只读查询（零写入）
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
│   └── _instrument_code_facade.py # 证券代码解析门面
├── command/            # Command DTO + Handler（原子写操作）
│   ├── ingestion.py              # IngestDateCommand + IngestDateHandler
│   ├── quality_check.py          # CheckDataQualityCommand + Handler
│   ├── quality_reconciliation.py # ReconcileSourcesCommand + Handler
│   └── protocols.py              # CommandHandler Protocol
├── process/            # Process Manager（有状态长流程）
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
│   │   └── backtest_serialization.py # 回测序列化
│   └── quality/        # 质量巡检流程
│       ├── __init__.py              # re-export shim
│       └── patrol.py                # QualityPatrolService（原 L3BatchService）
├── builders/           # 运行时装配（DI 构造）
│   ├── runtime_builder.py   # 运行时构建器
│   ├── slice_builder.py     # 切片构建器
│   ├── service_factory.py   # 服务工厂
│   ├── _resolution.py       # 依赖解析工具
│   └── _spec_deserializer.py # 衍生规格反序列化
├── providers.py        # DI Provider 注册（4 个 Provider）
└── config.py           # 数据集配置
```

## DI Provider（4 个）

| Provider | 职责 | 注册的服务 |
|----------|------|-----------|
| `AppCommandProvider` | Command Handler | CheckDataQualityHandler |
| `AppQueryProvider` | 只读查询 | 各 QueryFacade, ForwardReturnService |
| `AppProcessProvider` | 编排/物化/质量 | DerivedMaterializationOrchestrator, InvalidationCascadeOrchestrator, DerivedPublicationFacade, QualityPatrolService, SQLiteCompileCache, RuntimeDerivedInputProvider |
| `AppBuilderFactory` | 策略运行时装配 | StrategyRuntimeBuilder, BacktestRuntimeBuilder, StrategySliceBuilder, StrategyFacade |

## R8 互斥规则（importlinter 强制）

| 方向 | 规则 |
|------|------|
| query → process | r8-query-no-process ❌ |
| query → builders | r8-query-no-builders ❌ |
| query → command | r8-query-no-command ❌ |
| builders → query | r8-builders-no-query ❌ |
| command → query | r8-command-no-query ❌ |
| command → builders | r8-command-no-builders ❌ |
| process → query | ✅ 允许（编排可调用查询） |
| process ↔ builders | ✅ 允许（双向） |
| command → process | ✅ 允许（委托执行） |
| process → command | ✅ 允许（Process Manager 注入 Handler） |

## 测试规范

```
packages/app/
├── src/ditto_app/
└── tests/
    ├── unit/
    └── integration/
```

### 运行测试

```bash
pixi run -e dev pytest packages/app/tests/
```
