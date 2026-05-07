# ditto-application

**版本**: v0.4.0
**最后更新**: 2026-05-01
**状态**: 应用编排层（CQRS）

## 概要

应用编排层 -- 采用 CQRS 模式组织 Use Case，协调 capability packages（领域计算）与 Data（数据服务）。

## 模块结构

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
│   ├── artifact_utils.py         # 共享 artifact 查找 + 回测指标计算
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
│   ├── materialization/ # 因子物化流程
│   ├── execution/      # 策略执行流程
│   └── quality/        # 质量巡检流程
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
├── settings.py             # 应用层设置
├── config.py           # 数据集配置
├── contracts.py        # 跨 CQRS 子模块共享契约（Command DTO + ReadModel）
├── execution_dto.py    # 执行层 DTO + 跨层映射（TradeIntent/Fill/Snapshot）
└── exceptions.py       # 应用层自定义异常
```

## 架构定位

```
apps → application → strategy/portfolio/risk/execution/backtest → data → platform
                   → features
                   → kernel
```

**允许的依赖**:

| 依赖 | 用途 |
|------|------|
| `ditto_kernel` | 共享类型 |
| `ditto_data` | 数据服务 |
| `ditto_strategy` | 策略定义与信号生成 |
| `ditto_portfolio` | 组合构建与管理 |
| `ditto_risk` | 风险管理 |
| `ditto_execution` | 交易执行 |
| `ditto_backtest` | 回测引擎 |
| `ditto_features` | 表达式编译 / 物化 |
| `ditto_platform` | 基础设施（仅 foundation） |

**禁止依赖**: ditto_apps

## CQRS 模式

Application 层采用 CQRS 模式分离读写职责：

| 模块 | 职责 | 规则 |
|------|------|------|
| `queries/` | 只读查询 | 禁止写入、禁止调用 processes/builders/commands |
| `processes/` | 编排流程 | 可调用 queries，可双向访问 builders |
| `commands/` | 纯写入 | 禁止调用 queries/builders |
| `builders/` | 运行时装配 | 禁止调用 queries |

## 使用示例

### DI 注册

```python
from ditto_application.providers import get_app_providers

providers = get_app_providers()  # [AppMarketQueryProvider, AppStrategyQueryProvider, AppPortfolioQueryProvider, ...]
```

### 查询服务

```python
from ditto_application.queries.market import MarketQueryFacade

facade = container.get(MarketQueryFacade)
bars = facade.list_bars(code="159915.SZ", start="2024-01-01", end="2024-12-31")
```

## 相关文档

- [Application 层规范](CLAUDE.md)
- [架构规则](../../.claude/rules/architecture.md)
