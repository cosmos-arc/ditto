# ditto-app

**版本**: v0.4.0
**最后更新**: 2026-04-16
**状态**: 应用编排层（CQRS）

## 概要

应用编排层 -- 采用 CQRS 模式组织 Use Case，协调 Engine（领域计算）与 Data（数据服务）。

## 模块结构

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
├── command/            # Command DTO + Handler（原子写操作）
│   ├── ingestion.py              # IngestDateCommand + IngestDateHandler
│   ├── quality_check.py          # CheckDataQualityCommand + Handler
│   ├── quality_reconciliation.py # ReconcileSourcesCommand + Handler
│   ├── protocols.py              # CommandHandler Protocol
│   ├── backtest.py               # 回测触发/取消/重试 Command
│   ├── strategy.py               # 策略 Spec CRUD（创建/更新/发布）
│   ├── trade.py                  # 成交录入 + 意图状态更新
│   └── universe.py               # 自定义 Universe CRUD
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
│   │   ├── fetch_handlers.py        # 获取处理器构建
│   │   └── ports.py                 # 摄取流程 Handler Protocol（解耦 command 依赖）
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
├── providers.py            # DI Provider 聚合入口（6 个 Provider）
├── providers_market.py     # 市场数据查询 Provider（13 个 @provide）
├── providers_strategy.py   # 策略/回测查询 Provider（7 个 @provide）
├── providers_portfolio.py  # 组合/交易查询 Provider（3 个 @provide）
├── config.py           # 数据集配置
├── contracts.py        # 跨 CQRS 子模块共享契约（Command DTO + ReadModel）
└── execution_dto.py    # 执行层 DTO + 跨层映射（TradeIntent/Fill/Snapshot）
```

## 架构定位

```
interfaces → app → engine → data → infra
                → analytics
                → kernel
```

**允许的依赖**:

| 依赖 | 用途 |
|------|------|
| `ditto_kernel` | 共享类型 |
| `ditto_data` | 数据服务 |
| `ditto_engine` | 领域计算 |
| `ditto_features` | 表达式编译 / 物化 |
| `ditto_platform` | 基础设施（仅 foundation） |

**禁止依赖**: interfaces

## CQRS 模式

App 层采用 CQRS 模式分离读写职责：

| 模块 | 职责 | 规则 |
|------|------|------|
| `query/` | 只读查询 | 禁止写入、禁止调用 process/builders/command |
| `process/` | 编排流程 | 可调用 query，可双向访问 builders |
| `command/` | 纯写入 | 禁止调用 query/builders |
| `builders/` | 运行时装配 | 禁止调用 query |

## 使用示例

### DI 注册

```python
from ditto_app.providers import get_app_providers

providers = get_app_providers()  # [AppMarketQueryProvider, AppStrategyQueryProvider, AppPortfolioQueryProvider, ...]
```

### 查询服务

```python
from ditto_app.query.market import MarketQueryFacade

facade = container.get(MarketQueryFacade)
bars = facade.list_bars(code="159915.SZ", start="2024-01-01", end="2024-12-31")
```

## 相关文档

- [App 层规范](CLAUDE.md)
- [架构规则](../../.claude/rules/architecture.md)
