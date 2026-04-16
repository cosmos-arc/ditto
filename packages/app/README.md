# ditto-app

**版本**: v0.4.0
**最后更新**: 2026-04-07
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
│   └── _utils.py      # 查询工具
├── process/            # 编排流程（可调用 query）
│   ├── auto_init.py                # 自动初始化
│   ├── ingestion_config.py         # 摄取配置 dataclass
│   ├── metadata_manager.py         # 元数据管理器
│   ├── data_writer.py              # 数据写入器
│   ├── list_date_inference.py      # 上市日期推断服务
│   ├── result_handler.py           # 摄取结果处理器
│   ├── backfill_handler.py         # 回填处理器
│   ├── _coordinator_constants.py   # 共享常量 + 指数工具函数
│   ├── coordinator_factory.py      # create_coordinator 工厂
│   ├── ingestion_coordinator.py    # IngestionCoordinator 主类
│   ├── backfill_manager.py         # BackfillManager
│   ├── retry_manager.py            # RetryManager
│   ├── materialization_types.py    # 物化类型定义
│   ├── materialization_dependencies.py # 物化依赖
│   ├── materialization_helpers.py  # 物化辅助函数
│   ├── publication_facade.py       # 发布门面
│   ├── _publication_helpers.py     # 发布辅助函数
│   ├── cascade_orchestrator.py     # 级联编排器
│   ├── materialization_orchestrator.py # 物化主编排器
│   ├── certification_rules.py      # 认证规则
│   ├── factor_orthogonalization.py # 因子正交化
│   ├── runtime_input_provider.py   # 运行时输入提供器
│   ├── quality.py                  # 质量校验流程
│   ├── backtest_serialization.py   # 回测序列化
│   ├── strategy_types.py           # 策略类型定义
│   ├── backtest_service.py         # 回测服务
│   └── strategy_run_service.py     # 策略运行服务
├── command/            # CQRS Command（纯写入）
│   ├── ingestion.py   # 摄取命令
│   └── strategy.py    # 策略命令
├── builders/           # 运行时装配（DI 构造）
│   ├── runtime_builder.py   # 运行时构建器
│   ├── slice_builder.py     # 切片构建器
│   └── service_factory.py   # 服务工厂
├── providers.py        # DI Provider 注册
├── config.py           # 数据集配置
└── types.py            # 共享类型定义
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
| `ditto_analytics` | 表达式编译 / 物化 |
| `ditto_infra` | 基础设施（仅 foundation） |

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
