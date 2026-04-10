# App 层 CQRS 重构设计

> 日期：2026-04-10
> 状态：设计中（brainstorming 阶段持续进行中）

## 1. 动机

当前 `packages/app/` 层存在以下问题：

1. **process/ 平铺爆炸**：30+ 文件在同一目录，ingestion / materialization / quality / strategy / backtest 全部混在一起
2. **command/ 空壳**：5 个 Command DTO 存在，但 `CommandHandler` Protocol 标注"当前无生产代码使用"，所有写操作编排直接在 process/ 里完成
3. **职责偏移**：process/ 原定位是 "long-running process"，实际承担了全部写侧编排（相当于 Application Service 层），Command 和 Process Manager 的边界未区分

## 2. 设计原则（业界最佳实践）

### 2.1 Command Handler vs Process Manager

| 维度 | Command Handler | Process Manager |
|------|----------------|-----------------|
| **本质** | 无状态、单请求、单聚合 | 有状态、跨聚合、多步骤 |
| **生命周期** | 接收→验证→执行→完成 | 触发→持久化状态→等待→路由决策→完成 |
| **通信** | 接收 Command | 接收 Trigger / 响应 Event / 发出 Command |
| **失败处理** | 事务回滚 | 补偿链/状态机回退 |
| **判断标准** | 单次请求内可完成 | 需要等待、记住进度、处理不确定性 |

> 关键洞察（Bernd Ruecker, Temporal.io）：
> "Long running doesn't mean there is real action all the time. It means you **potentially have to wait**."
> 判断标准不是绝对时间长短，而是**是否需要持久化中间状态并等待**。

### 2.2 三层选择（Oskar Dudycz, Event-Driven.io）

```
简单（单聚合操作）      --> Command Handler
中等（跨聚合但逻辑线性） --> 无状态 Saga
复杂（条件分支/状态机）  --> Process Manager
```

### 2.3 质量检查的定位

QualityService（check + quarantine write）是**带副作用的写操作 = Command**。

- 纯计算（QualityEngine）→ ditto_data 领域服务，任何人可调用
- check + 副作用（quarantine write）→ Command，谁需要就发 Command
- 不存在"共享 service"概念，通过 Command 解耦

### 2.4 Process Manager 交互模型

```
interfaces/ (API/CLI/Jobs)
  │
  ├─ 简单写操作 ──→ Command Handler ──→ 完成
  │                  (原子、无状态)
  │
  └─ 长流程 ──→ Process Manager
                  │
                  ├─ 接收 Trigger（触发）
                  ├─ 响应 Event（推进流程）
                  ├─ 发出 Command ──→ Command Handler（原子操作）
                  └─ 持久化状态、处理中断恢复
```

**Process Manager 不通过 Command Handler 桥接启动，而是直接接收 Trigger DTO。**

## 3. 最终目录结构

```
app/
  command/                              # Command DTO + Handler（原子写操作）
    __init__.py
    ingestion.py                        # IngestDateCommand + IngestDateHandler
    backfill.py                         # BackfillGapCommand + BackfillGapHandler
    quality_check.py                    # CheckDataQualityCommand + Handler
    quality_l3.py                       # L3BatchCheckCommand + Handler
    quality_reconciliation.py           # ReconcileSourcesCommand + Handler
    protocols.py                        # CommandHandler[C] Protocol（激活）

  process/                              # Process Manager（有状态长流程）
    ingestion/
      __init__.py
      range_process.py                  # 接受 IngestRangeTrigger → 发 IngestDateCommand
      backfill_process.py               # 接受 BackfillRangeTrigger → 发 BackfillGapCommand
      retry_process.py                  # 响应失败 Event → 重发 Command
      auto_init.py
      fetch_handlers.py
      commodity_fetcher.py
      coordinator_constants.py
      types.py                          # BackfillContext 等 + Trigger DTO
    materialization/
      __init__.py
      orchestrator.py                   # DerivedMaterializationOrchestrator
      cascade_orchestrator.py           # InvalidationCascadeOrchestrator（状态机）
      publication_facade.py             # DerivedPublicationFacade
      publication_helpers.py            # shadow diff/trace/certification 纯函数
      dependencies.py                   # CS amplification, dependency classification
      helpers.py                        # DQ summary, manifest building
      certification_rules.py            # 认证检查规则构建器
      runtime_input_provider.py         # 生产环境输入加载
      types.py                          # InputContext, CoordinatorServices + Trigger DTO
      protocols.py                      # DerivedInputProvider
    execution/
      __init__.py
      backtest_process.py               # 接受 BacktestTrigger → 执行循环 + 持久化
      strategy_run_process.py           # 接受 StrategySliceTrigger → 多日切片运行
      backtest_serialization.py         # 序列化（Process 内部委托）
      strategy_input.py                 # StrategyInputAssembler + artifact writers
      types.py                          # config dataclasses + Trigger DTO

  query/                                # 不变
  builders/                             # 不变
  config.py                             # 不变
  providers.py                          # 4 个 dishka Provider：
                                        #   AppQueryProvider（不变）
                                        #   AppCommandProvider（新增，注册 Command Handler）
                                        #   AppProcessProvider（更新，注册 Process Manager）
                                        #   AppBuilderFactory（不变）
```

## 4. 当前文件 → 新位置映射

### → command/（原子写操作，DTO + Handler）

| 当前位置 | 新位置 | 说明 |
|---------|--------|------|
| `command/ingestion.py` | `command/ingestion.py` | 加 IngestDateHandler |
| `command/strategy.py` | `command/strategy.py` | 只保留 RunBacktestCommand → 重命名为触发器，移至 process/execution/types.py |
| `process/data_writer.py` | `command/ingestion.py` 内委托 | DataWriter 是写入逻辑 |
| `process/metadata_manager.py` | `command/ingestion.py` 内委托 | checksum skip |
| `process/result_handler.py` | `command/ingestion.py` 内委托 | 结果处理 |
| `process/quality_check.py` | `command/quality_check.py` | CheckDataQualityCommand + Handler |
| `process/quality_l3.py` | `command/quality_l3.py` | L3BatchCheckCommand + Handler |
| `process/quality_reconciliation.py` | `command/quality_reconciliation.py` | ReconcileSourcesCommand + Handler |
| `process/backfill_handler.py` | `command/backfill.py` | BackfillGapCommand + Handler（单次 gap 填充） |

### → process/ingestion/（数据摄取长流程）

| 当前位置 | 新位置 |
|---------|--------|
| `process/ingestion_coordinator.py` (range 部分) | `process/ingestion/range_process.py` |
| `process/backfill_manager.py` | `process/ingestion/backfill_process.py` |
| `process/retry_manager.py` | `process/ingestion/retry_process.py` |
| `process/auto_init.py` | `process/ingestion/auto_init.py` |
| `process/_fetch_handlers.py` | `process/ingestion/fetch_handlers.py` |
| `process/_commodity_fetcher.py` | `process/ingestion/commodity_fetcher.py` |
| `process/_coordinator_constants.py` | `process/ingestion/coordinator_constants.py` |
| `process/ingestion_config.py` | `process/ingestion/types.py` |
| `process/coordinator_factory.py` | `process/ingestion/types.py`（CoordinatorServices 归入） |

### → process/materialization/（因子物化长流程）

| 当前位置 | 新位置 |
|---------|--------|
| `process/materialization_orchestrator.py` | `process/materialization/orchestrator.py` |
| `process/cascade_orchestrator.py` | `process/materialization/cascade_orchestrator.py` |
| `process/publication_facade.py` | `process/materialization/publication_facade.py` |
| `process/_publication_helpers.py` | `process/materialization/publication_helpers.py` |
| `process/materialization_dependencies.py` | `process/materialization/dependencies.py` |
| `process/materialization_helpers.py` | `process/materialization/helpers.py` |
| `process/certification_rules.py` | `process/materialization/certification_rules.py` |
| `process/runtime_input_provider.py` | `process/materialization/runtime_input_provider.py` |
| `process/materialization_types.py` | 拆入 `materialization/types.py` + `materialization/protocols.py` |

### → process/execution/（策略执行长流程）

| 当前位置 | 新位置 |
|---------|--------|
| `process/backtest_service.py` | `process/execution/backtest_process.py` |
| `process/strategy_run_service.py` | `process/execution/strategy_run_process.py` |
| `process/backtest_serialization.py` | `process/execution/backtest_serialization.py` |
| `process/strategy_types.py` | 拆分：types → `execution/types.py`，logic → `execution/strategy_input.py` |

### → 消失/合并

| 当前文件 | 处理 |
|---------|------|
| `process/quality.py` | 删除（纯 re-export shim） |
| `process/quality_protocols.py` | 协议归入 ditto_data 或 command/ 对应 Handler 的依赖 |
| `process/ingestion_coordinator.py` (单日部分) | 合并入 `command/ingestion.py` Handler |
| `command/protocols.py` | 激活 CommandHandler Protocol，删除"未使用"注释 |

## 5. Trigger DTO 命名

Process Manager 的输入 DTO 命名为 `*Trigger`，放在对应 process 子包的 `types.py` 中：

| Trigger | Process Manager | 说明 |
|---------|----------------|------|
| `IngestRangeTrigger` | IngestRangeProcess | 跨日期范围摄取 |
| `BackfillRangeTrigger` | BackfillProcess | 缺口检测 + 并行回填 |
| `BacktestTrigger` | BacktestProcess | 回测执行循环 |
| `StrategySliceTrigger` | StrategyRunProcess | 多日切片策略运行 |

## 6. 关键决策记录

| # | 决策 | 理由 |
|---|------|------|
| 1 | 经典 CQRS 风格 | Command Handler 处理原子写，Process Manager 处理长流程 |
| 2 | 按能力域拆子包（ingestion/materialization/execution） | 变更同频度高的放一起，backtest + strategy 都是"策略执行" |
| 3 | publication 归入 materialization/ | 主要服务 materialization 流程 |
| 4 | Handler 住在 command/ 包内 | Milan Jovanovic 风格，DTO + Handler 放一起方便导航 |
| 5 | types.py 收归各子包 | 每个子包统一 types.py + 可选 protocols.py |
| 6 | 质量检查 = Command（非共享 service） | check + quarantine write 是带副作用的写操作 |
| 7 | Process Manager 直接接收 Trigger（不经 Command Handler 桥接） | Command Handler 和 Process Manager 是平行关系 |
| 8 | Trigger DTO 放 process 子包（非 command 包） | 避免与原子 Command DTO 混淆 |
| 9 | BacktestService 是 Process（非 Command） | 有执行循环、持久化、中断恢复，是典型长流程 |

## 7. 事件驱动设计（对标业界量化系统）

### 7.1 业界参考：QuantConnect LEAN

LEAN 通过 **5 个可插拔接口** 统一回测/实盘模式，策略代码完全不变：

| 接口 | 回测实现 | 实盘实现 |
|------|---------|---------|
| `IDataFeed` | 从磁盘读历史文件 | WebSocket 实时流 |
| `ITransactionHandler` | 填充模型模拟 | 真实券商下单 |
| `IResultHandler` | 本地存储 | 实时推送 |
| `IRealTimeHandler` | 虚拟时钟快进 | 真实时钟 |
| `ISetupHandler` | 配置参数 | 加载持仓/未结订单 |

### 7.2 事件类型体系（量化系统标准）

```
市场数据事件     Tick / Bar / Depth / Slice
订单生命周期事件  Submitted → Accepted → PartialFill → Filled / Cancelled / Rejected
组合事件        PositionChanged / CashChanged
风险事件        LimitBreach / MarginCall
系统事件        SessionStart / SessionEnd / ConnectionLost
```

### 7.3 Ditto 的渐进策略

**当前阶段（回测）**：不需要 Event Bus，Process Manager 内部直接调用 Command Handler。

```python
class IngestRangeProcess:
    def __init__(self, handler: IngestDateHandler) -> None:
        self._handler = handler

    def run(self, trigger: IngestRangeTrigger) -> None:
        for date in trigger.date_range:
            cmd = IngestDateCommand(trigger.dataset, date)
            self._handler(cmd)  # 进程内直接调用
            self._state.progress = date  # 持久化进度
```

**未来阶段（实盘）**：同一 Process Manager 被注册为 Event Consumer，由外部事件驱动推进。

```python
class BacktestProcess:
    # 回测模式：便捷入口，内部循环 + 直接调用
    def run(self, trigger: BacktestTrigger) -> None:
        for slice in engine_loop:
            self._handle_slice(slice)
            self._persist_state(slice.time)

    # 实盘模式：事件接口，由外部 Event Bus 分发
    def on_data(self, event: SliceEvent) -> None:     # 行情推送
        ...
    def on_order(self, event: OrderEvent) -> None:    # 券商回报
        ...
    def on_fill(self, event: FillEvent) -> None:      # 成交回报
        ...
```

**核心原则：接口预留，实现渐进。** 不在现在引入 Event Bus 基础设施，但 Process Manager 的结构天然支持"接收外部 Event 推进流程"——未来加 `on_event` 方法 + 消息分发即可。

### 7.4 回测/实盘统一的可插拔接口（未来）

参考 LEAN 的 5 接口模式，Ditto 未来需要的关键抽象：

| Protocol | 回测实现 | 实盘实现 |
|----------|---------|---------|
| `MarketDataSource` | 从 Parquet 文件读取 | WebSocket / API 实时流 |
| `ExecutionHandler` | 填充模型模拟 | 券商下单 + 成交回报 |
| `TimeProvider` | 虚拟时钟快进 | 真实时钟 |
| `StateStore` | 内存 / SQLite | 持久化存储（Redis/DB） |

Process Manager 依赖这些 Protocol，不依赖具体实现，实现回测/实盘的插拔切换。

## 8. 辅助模块归属分析

### `factor_orthogonalization.py`（~123 行）

**本质**：数据准备 + 纯计算，**无写入副作用**。

- 从 `DerivedArtifactReader` 加载因子数据（读）
- 调用 `analytics.orthogonalize()` 纯函数计算正交化结果（计算）
- 返回 DataFrame，写入由调用方（materialization orchestrator）负责

**归属**：`process/materialization/` 的辅助模块，作为 materialization orchestrator 的数据准备步骤。不需要独立存在。

### `list_date_inference.py`（~285 行）

**本质**：纯推断逻辑 + metadata 更新，是 ingestion 流程的一个环节。

- 纯推断逻辑（`_infer_list_date_for_instrument`、`_find_earliest_trade_date`）是无副作用计算
- 调用 `metadata_service.update_list_date()` 写入是 ingestion Command 的一个步骤

**归属**：
- 纯推断逻辑下沉到 ditto_data 或作为独立纯函数
- 调用推断 + 更新 metadata 归入 ingestion Command Handler 的执行步骤

**结论**：这两个文件的独立存在是因为之前分层没有把它们放到正确的调用链中。正确归属后不需要特殊架构决策。

## 9. 状态持久化设计

### 9.1 成熟度模型（业界最佳实践）

| Level | 方案 | 适用场景 | 代表 |
|-------|------|---------|------|
| **L0** | 纯内存 | 原型、秒级流程 | pytransitions |
| **L1** | 可选 Checkpoint 文件 | 分钟~小时级单进程流程 | Substantial |
| **L2** | DB 状态表 | 多进程、需监控 | NServiceBus Saga、Prefect |
| **L3** | 完整工作流引擎 | 分布式、需补偿 | Temporal、DBOS |
| **L4** | 事件溯源 | 合规审计、需时间旅行 | EventStoreDB |

### 9.2 核心原则

**从一开始就把状态设计为可序列化的对象，即使现在不持久化。** 这样未来加持久化只是配置变更，不是架构重写。

> NServiceBus/MassTransit 的 Saga Instance 模式：
> 每个 Process 实例 = 一行记录（id, type, state JSON, version, created_at, updated_at）

### 9.3 不推荐事件溯源

回测结果本身是"真相"，中间状态没有独立审计价值。事件溯源的复杂度远超收益。

### 9.4 各 Process Manager 的持久化策略

| Process Manager | 当前阶段 | 实盘阶段演进 |
|----------------|---------|------------|
| IngestRangeProcess | L0（内存，重跑成本低） | L1（checkpoint，支持中断恢复） |
| BackfillProcess | L1（范围大，中断后不想从头跑） | L2（DB 状态表，多 worker 并行） |
| CascadeOrchestrator | L1（状态机已有，加序列化即可） | L2 |
| BacktestProcess | L1（长时间回测 checkpoint） | L2（实盘必须持久化持仓/订单） |
| StrategyRunProcess | L0 | L2 |

### 9.5 实现方式

每个 Process Manager 内部维护一个 `state: ProcessState` dataclass，在自然边界（交易日结束、每 N 个 bar）时调用 `state.save_checkpoint(path)`。存储格式用 SQLite 或 Parquet（已在技术栈内）。

实盘时切换为 DB 状态表，接口不变。

## 10. DI Provider 策略

从 3 个 dishka Provider 扩展为 4 个：

| Provider | 职责 | 变更 |
|----------|------|------|
| `AppQueryProvider` | 注册 query facades | 不变 |
| `AppCommandProvider` | 注册 Command Handler | 新增 |
| `AppProcessProvider` | 注册 Process Manager | 更新（拆分为子包注册） |
| `AppBuilderFactory` | 注册 builders | 不变 |

**依赖注入方向**：
- `AppCommandProvider`：Handler 依赖 data 层服务（MetadataService、MarketService 等）
- `AppProcessProvider`：Process Manager 依赖 Command Handler（通过注入）

## 11. 迁移分阶段策略

### Phase 1：结构搬迁（纯文件移动，不改行为）

- 创建子包目录（`ingestion/`、`materialization/`、`execution/`）
- 移动文件到新位置，保持类/函数签名不变
- 更新所有 import 路径 + `__init__.py` re-export
- 确保测试通过，行为零变更

### Phase 2：职责拆分（行为变更）

- 拆 IngestionCoordinator → IngestDateHandler（Command）+ IngestRangeProcess（Process）
- 新增 Command Handler（quality_check、quality_l3、quality_reconciliation、backfill）
- 消化 quality.py re-export shim、quality_protocols.py
- factor_orthogonalization 归入 materialization 辅助
- list_date_inference 纯推断下沉到 ditto_data

### Phase 3：收尾

- 激活 CommandHandler Protocol
- 更新 DI providers（新增 AppCommandProvider）
- 更新 app/CLAUDE.md + importlinter 规则
- 清理废弃代码
