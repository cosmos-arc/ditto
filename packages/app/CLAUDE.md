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
│   ├── _instrument_code_facade.py # 证券代码解析门面
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
│   ├── coordinator_factory.py      # create_coordinator 工厂 + re-export
│   ├── ingestion_coordinator.py    # IngestionCoordinator 主类
│   ├── backfill_manager.py         # BackfillManager
│   ├── retry_manager.py            # RetryManager
│   ├── materialization_types.py        # 物化类型定义
│   ├── materialization_dependencies.py # 物化依赖
│   ├── materialization_helpers.py      # 物化辅助函数
│   ├── publication_facade.py           # 发布门面
│   ├── _publication_helpers.py         # 发布辅助函数
│   ├── cascade_orchestrator.py         # 级联编排器
│   ├── materialization_orchestrator.py  # 物化主编排器
│   ├── certification_rules.py          # 认证规则
│   ├── factor_orthogonalization.py     # 因子正交化
│   ├── runtime_input_provider.py       # 运行时输入提供器
│   ├── quality.py                # 质量校验流程
│   ├── backtest_serialization.py  # 回测序列化
│   ├── strategy_types.py         # 策略类型定义
│   ├── backtest_service.py       # 回测服务
│   └── strategy_run_service.py   # 策略运行服务
├── command/            # CQRS Command（纯写入）
│   ├── ingestion.py   # 摄取命令
│   └── strategy.py    # 策略命令
├── builders/           # 运行时装配（DI 构造）
│   ├── runtime_builder.py   # 运行时构建器
│   ├── slice_builder.py     # 切片构建器
│   ├── service_factory.py   # 服务工厂
│   └── _resolution.py       # 依赖解析工具
├── providers.py        # DI Provider 注册
├── config.py           # 数据集配置
└── types.py            # 共享类型定义
```

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
